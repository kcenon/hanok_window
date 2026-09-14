"""Full-package regression, topology, saved geometry and publication failure tests."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import copy
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import ezdxf
from shapely.affinity import rotate, translate
from shapely.geometry import box

from hanok_generator.engine.cad_helpers import entity_polygon, meta, tag
from hanok_generator.engine.numeric_policy import geometry_matches
from hanok_generator.jobs import JobError, run_job
from hanok_generator.model import InputError, resolve
from hanok_generator.package import PNG_FILES, PackageError, digest, source_files, verify

HERE=Path(__file__).parent
LOG=[]


def request(kind="double", bars=(2,4), side=None, **changes):
    value=dict(type=kind,outer_mm=[463,586],lattice_per_leaf=list(bars))
    if side:value["hinge_side"]=side
    value.update(changes)
    return value


class GeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix="hanok-generator-tests-")
        cls.root=Path(cls.temp.name);cls.output=cls.root/"output"
        cls.requests={}
        for kind,side in [("double",None),("single","left"),("single","right")]:
            for v,h in [(2,4),(0,4),(2,0),(0,0)]:
                cls.requests[f"{kind}_{side}_{v}_{h}"]=request(kind,(v,h),side)
        cls.requests["r3"]=request(preset="hanok_A3_portrait_R3")
        cls.requests["resize"]=request(outer_mm=[600,800])
        cls.requests["lattice_3_5"]=request(bars=(3,5))
        cls.requests["picture"]=request(outer_mm=[600,800],picture=dict(size_mm=[297,420],margin_mm=10))
        inner=request(preset="hanok_A3_portrait_R3");inner.pop("outer_mm");inner["inner_mm"]=[383,506]
        cls.requests["inner_r3"]=inner
        def build(item):
            name,data=item;result=run_job(data,cls.output)
            LOG.append(dict(case=name,status="PASS",**{k:result[k] for k in ("checks","parts","pockets","dogbones","package_id")}))
            return name,result
        with ThreadPoolExecutor(max_workers=4) as pool:
            cls.results=dict(pool.map(build,cls.requests.items()))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def path(self,key):return Path(self.results[key]["package"])

    def test_r3_production_geometry_and_originals(self):
        reference=json.loads((HERE/"fixtures/r3_reference.json").read_text(encoding="utf-8"))
        p=self.path("r3")
        spec=json.loads((p/"design_spec.json").read_text(encoding="utf-8"));spec["revision"]=reference["spec"]["revision"]
        self.assertEqual(spec,reference["spec"])
        contours=[]
        for e in ezdxf.readfile(p/"window.dxf").modelspace():
            if e.dxf.layer in ("CUT_THROUGH","DOGBONE") or e.dxf.layer.startswith("POCKET_"):
                contours.append(dict(layer=e.dxf.layer,points=[list(v) for v in e.get_points("xyb")],metadata=meta(e)))
        self.assertEqual(contours,reference["contours"])
        # R1 (from_codex) left the working tree; tags R1-R3 keep it in git history.
        project=HERE.parents[1]
        for row in reference["source_manifest"]["files"]:
            self.assertEqual(digest(project/"r3_reference"/row["path"]),row["sha256"],row["path"])

    def test_inner_size_basis_reproduces_outer_geometry(self):
        inner,outer=self.path("inner_r3"),self.path("r3")
        a,b=(json.loads((p/"design_spec.json").read_text(encoding="utf-8")) for p in (inner,outer))
        self.assertNotEqual(a.pop("revision"),b.pop("revision"))
        self.assertEqual(a,b)
        self.assertEqual(a["derived"]["frame_inner"],[383,506])
        def contours(p):
            return [(e.dxf.layer,[list(v) for v in e.get_points("xyb")],meta(e)) for e in ezdxf.readfile(p/"window.dxf").modelspace()
                    if e.dxf.layer in ("CUT_THROUGH","DOGBONE") or e.dxf.layer.startswith("POCKET_")]
        self.assertEqual(contours(inner),contours(outer))
        for p,basis,want in [(inner,"inner",[383,506]),(outer,"outer",[463,586])]:
            check={c["rule_id"]:c for c in json.loads((p/"validation_report.json").read_text(encoding="utf-8"))["checks"]}["requested_size_matches_measured_frame"]
            self.assertEqual((check["status"],check["expected"],check["targets"]),("PASS",want,[basis+"_mm"]))
        self.assertEqual(json.loads((inner/"design_request.json").read_text(encoding="utf-8"))["inner_mm"],[383,506])
        self.assertEqual(json.loads((inner/"resolved_parameters.json").read_text(encoding="utf-8"))["provenance"]["size_basis"],"fixed-frame inner opening")
        self.assertIn("내경(고정틀 안목) 383 x 506 mm 입력",(inner/"README.txt").read_text(encoding="utf-8"))
        labels={e.dxf.text for e in ezdxf.readfile(inner/"window.dxf").modelspace() if e.dxftype()=="TEXT" and meta(e).get("view")=="assembly"}
        self.assertTrue({"383 FRAME INNER (INPUT)","506 FRAME INNER (INPUT)","463 OVERALL","586 OVERALL"}<=labels)
        LOG.append(dict(case="inner_size_basis_r3",status="PASS",inner=[383,506],equivalent_outer=[463,586],contours_identical=True))

    def test_inner_size_inputs_cli_and_errors(self):
        from hanok_generator import cli
        args=cli.parser().parse_args(["build","--type","double","--size","383.5x506.25","--size-basis","inner","--lattice","2x4"])
        self.assertEqual(cli.read_request(args),dict(type="double",inner_mm=[383.5,506.25],lattice_per_leaf=[2,4]))
        design=resolve(cli.read_request(args))
        self.assertEqual([design.parameters["frame"][k] for k in ("outer_width","outer_height")],[463.5,586.25])
        self.assertEqual(design.parameters["size"],dict(basis="inner",requested_mm=[383.5,506.25]))
        self.assertEqual(resolve(request()).parameters["size"],dict(basis="outer",requested_mm=[463,586]))
        base=dict(type="double",lattice_per_leaf=[2,4])
        for value,rule in [(dict(base,outer_mm=[463,586],inner_mm=[383,506]),"input.size_basis"),(base,"input.size_basis"),
                           (dict(base,inner_mm=[2990,506]),"input.range"),(dict(base,inner_mm=[0,506]),"input.range")]:
            with self.subTest(rule=rule,value=str(value)),self.assertRaises(InputError) as caught:resolve(value)
            self.assertEqual(caught.exception.rule_id,rule)
        result=run_job(dict(type="single",hinge_side="left",inner_mm=[340.3,820.7],lattice_per_leaf=[2,6]),self.output)
        report=json.loads((Path(result["package"])/"validation_report.json").read_text(encoding="utf-8"))
        check={c["rule_id"]:c for c in report["checks"]}["requested_size_matches_measured_frame"]
        self.assertEqual(check["status"],"PASS")
        self.assertTrue(all(abs(a-b)<=1e-7 for a,b in zip(check["actual"],[340.3,820.7])))
        LOG.append(dict(case="inner_size_inputs",status="PASS",cli_basis="inner",decimal_inner=[340.3,820.7],rejections=4))

    def test_all_types_zero_counts_and_real_details(self):
        ids=None
        for name,data in self.requests.items():
            with self.subTest(name=name):
                p=self.path(name);n=1 if data["type"]=="single" else 2;v,h=data["lattice_per_leaf"]
                r=self.results[name]
                self.assertEqual((r["parts"],r["pockets"],r["dogbones"]),
                                 (4+4*n+n*(v+h),8+8*n+2*n*v*h+4*n*(v+h),4*n*(v+h)))
                self.assertEqual(verify(p)["status"],"PASS")
                self.assertTrue(all((p/f).is_file() for f in PNG_FILES))
                report=json.loads((p/"validation_report.json").read_text(encoding="utf-8"))
                current={c["rule_id"] for c in report["checks"]}
                if ids is None:ids=current
                self.assertEqual(current,ids)
                for c in report["checks"]:
                    self.assertTrue({"rule_id","expected","actual","tolerance","targets","status"}.issubset(c))
                checks={c['rule_id']:c for c in report['checks']}
                self.assertEqual(checks['J1_pocket_count']['expected'],8)
                self.assertEqual(checks['J1_pocket_count']['actual'],8)
                self.assertTrue(all(value==[v,h] for value in checks['lattice_bars_per_leaf']['actual'].values()))
                self.assertIsInstance(checks['all_machining_entities_closed_lwpolyline']['actual'],bool)
                self.assertEqual(report["manufacturing_assessment"]["status"],"PENDING")
                doc=ezdxf.readfile(p/"window.dxf")
                details={meta(e).get("detail") for e in doc.modelspace() if meta(e).get("view")=="detail"}
                want={"J1","J2"}|({"J3"} if v*h else set())|({"J4V"} if v else set())|({"J4H"} if h else set())
                self.assertEqual(details,want)
                if not v:
                    self.assertFalse(any("L01" in e.dxf.text for e in doc.modelspace() if e.dxftype()=="TEXT" and meta(e).get("view")=="detail"))
                if not h:
                    self.assertFalse(any("L02" in e.dxf.text for e in doc.modelspace() if e.dxftype()=="TEXT" and meta(e).get("view")=="detail"))
                if not v+h:
                    with (p/"dogbone_manifest.csv").open(encoding="utf-8-sig") as f:
                        rows=csv.DictReader(f);self.assertIn("radius_mm",rows.fieldnames);self.assertEqual(list(rows),[])

    def test_single_hardware_and_measured_swing_direction(self):
        for side in ("left","right"):
            doc=ezdxf.readfile(self.path(f"single_{side}_2_4")/"window.dxf")
            hw=[meta(e) for e in doc.modelspace() if meta(e).get("kind")=="hardware_ref" and meta(e).get("view")=="assembly"]
            hs="S01-1" if side=="left" else "S01-2";handle="S01-2" if side=="left" else "S01-1"
            self.assertEqual({d["part_id"] for d in hw if d["hardware_type"]=="HINGE" and d["part_id"].startswith("S")},{hs})
            self.assertEqual({d["part_id"] for d in hw if d["hardware_type"]=="HANDLE"},{handle})
            self.assertEqual({d["part_id"] for d in hw if d["hardware_type"]=="CATCH" and d["part_id"].startswith("S")},{handle})
            opened=[e for e in doc.modelspace() if meta(e).get("kind")=="opened_leaf_illustration"]
            closed=[e for e in doc.modelspace() if meta(e).get("kind")=="closed_leaf_ghost"]
            self.assertEqual(len(opened),1);self.assertEqual(len(closed),1)
            axis=meta(opened[0])["provisional_axis"]
            want=rotate(entity_polygon(closed[0]),90 if side=="left" else -90,origin=(1350+axis[0],-370+axis[1]))
            self.assertTrue(geometry_matches(want,entity_polygon(opened[0])))
            heading=next(e for e in doc.modelspace() if meta(e).get("view")=="opening" and meta(e).get("kind")=="title")
            self.assertGreater(heading.dxf.insert.y-heading.dxf.height,entity_polygon(opened[0]).bounds[3])

    def test_saved_geometry_rejects_phantom_detail_and_wrong_hinge(self):
        from hanok_generator.engine import builder
        p=self.path("single_right_0_0")
        builder.configure(json.loads((p/"design_parameters.json").read_text(encoding="utf-8")),p)
        doc=ezdxf.readfile(p/"window.dxf")
        e=doc.modelspace().add_text("PHANTOM J3")
        tag(e,view="detail",detail="J3")
        with self.assertRaises(builder.ValidationError) as caught:builder.validate(doc,"INJECTED")
        self.assertIn("reference_details_match_existing_joints",caught.exception.report["failed_checks"])
        doc=ezdxf.readfile(p/"window.dxf")
        for e in doc.modelspace():
            d=meta(e)
            if d.get("kind")=="hardware_ref" and d["hardware_type"]=="HINGE" and d["part_id"]=="S01-2":
                tag(e,**dict(d,part_id="S01-1"))
        with self.assertRaises(builder.ValidationError) as caught:builder.validate(doc,"INJECTED")
        self.assertIn("hardware_attachment_geometry",caught.exception.report["failed_checks"])

    def test_early_errors_and_cut_overlap_keep_previous_package(self):
        latest=(self.output/"latest.json").read_bytes()
        cases=[("scope_free_single",None),
               ("dense",request(bars=(12,4))),
               ("oversize_part",request(outer_mm=[900,1500])),
               ("oversize_layout",request(stock_mm=[1220,150,20])),
               ("picture_too_large",request(picture=dict(size_mm=[500,500]))),
               ("portrait_preset",request(outer_mm=[523,646],preset="hanok_A3_portrait_R3",picture=None)),
               ("invalid_integer",request(bars=(1.5,4)))]
        expected={"dense":"geometry.validation","oversize_part":"nesting.part_fits_stock", "oversize_layout":"nesting.board_width",
                  "picture_too_large":"picture.fits_width","portrait_preset":"leaf.aspect_ratio","invalid_integer":"input.number"}
        for name,data in cases[1:]:
            with self.subTest(name=name),self.assertRaises(JobError) as caught:run_job(data,self.output)
            self.assertEqual(caught.exception.result["rule_id"],expected[name])
            self.assertEqual((self.output/"latest.json").read_bytes(),latest)
            self.assertTrue(Path(caught.exception.result["failure_report"]).is_file())
            LOG.append(dict(case=name,status="REJECTED",rule_id=expected[name]))

    def test_all_failure_stages_preserve_publication(self):
        latest=(self.output/"latest.json").read_bytes()
        package=self.output/json.loads(latest)["path"]
        manifest=(package/"package_manifest.json").read_bytes()
        for stage in ("cad","csv","render","manifest","publish","pointer","terminate:render"):
            with self.subTest(stage=stage),self.assertRaises(JobError):
                run_job(request(bars=(3,5)),self.output,_fault=stage)
            self.assertEqual((self.output/"latest.json").read_bytes(),latest)
            self.assertEqual((package/"package_manifest.json").read_bytes(),manifest)
            self.assertEqual(verify(package)["status"],"PASS")
            self.assertEqual(list((self.output/".staging").iterdir()),[])
            LOG.append(dict(case="failure_"+stage,status="PREVIOUS_PACKAGE_PRESERVED"))

    def test_concurrent_mixed_jobs_and_byte_rebuild(self):
        cases=[request(),request("single",(0,0),"left"),request("single",(0,4),"right"),request(bars=(3,5)),request(bars=(12,4))]*2
        def run(data):
            try:return run_job(data,self.output)
            except JobError as exc:return exc.result
        with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(run,cases))
        for i in range(5):
            a,b=results[i],results[i+5]
            if i==4:
                self.assertEqual(a["rule_id"],"geometry.validation");self.assertEqual(b["rule_id"],"geometry.validation")
            else:
                self.assertEqual(a["package_id"],b["package_id"])
                self.assertEqual(verify(a["package"])["status"],"PASS")
        LOG.append(dict(case="concurrent_mixed",jobs=10,successes=8,expected_failures=2,status="PASS"))

    def test_source_bundle_rebuild_and_optimized_cli(self):
        source=self.path("r3")
        env={**os.environ,"PYTHONPATH":str(source/"source"),"PYTHONDONTWRITEBYTECODE":"1","PYTHONOPTIMIZE":"1"}
        p=subprocess.run([sys.executable,"-m","hanok_generator","build","--input",str(source/"design_request.json"),"--output",str(self.root/"optimized")],
                         cwd=self.root,env=env,capture_output=True,text=True,encoding="utf-8",timeout=120)
        self.assertEqual(p.returncode,0,p.stderr)
        result=json.loads(p.stdout)
        self.assertEqual(digest(Path(result["package"])/"window.dxf"),digest(source/"window.dxf"))
        self.assertEqual(result["package_id"],self.results["r3"]["package_id"])
        p=subprocess.run([sys.executable,"-m","hanok_generator","build","--type","double","--size","463x586","--lattice","12x4","--output",str(self.root/"optimized")],
                         cwd=self.root,env=env,capture_output=True,text=True,encoding="utf-8",timeout=120)
        self.assertEqual(p.returncode,1,p.stderr);self.assertEqual(json.loads(p.stderr)["rule_id"],"geometry.validation")
        LOG.append(dict(case="optimized_source_bundle",status="PASS",entire_package_identical=True,overlap_rejected=True))

    def test_manifest_tampering_is_read_only(self):
        copydir=self.root/"tampered";shutil.copytree(self.path("r3"),copydir)
        manifest=(copydir/"package_manifest.json").read_bytes()
        with (copydir/"README.txt").open("a",encoding="utf-8") as f:f.write("changed")
        with self.assertRaises(PackageError):verify(copydir)
        self.assertEqual((copydir/"package_manifest.json").read_bytes(),manifest)

    def test_source_export_ignores_nested_generated_packages(self):
        from hanok_generator import package
        root=self.root/'fake_source'
        for name in ['module.py','engine/math.py','presets/default.json','request.schema.json','output/packages/id/source/hanok_generator/old.py','output/packages/id/design_spec.json']:
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}',encoding='utf-8')
        with patch.object(package,'__file__',str(root/'package.py')):
            names={name for name,_ in package.source_files()}
        self.assertEqual(names,{'module.py','engine/math.py','presets/default.json','request.schema.json'})

    def test_input_schema_and_strict_values(self):
        bad=[dict(request(),typo=1),request("single"),dict(request(),hinge_side="left"),dict(request(),hinge_side=None),request(bars=(True,4)),
             request(outer_mm=[float("nan"),586]),request(outer_mm=[10**400,586]),request(bars=(33,4)),
             request("single",side="left",preset="hanok_A3_portrait_R3")]
        for value in bad:
            with self.subTest(value=str(value)[:80]),self.assertRaises(InputError):resolve(value)
        self.assertEqual(resolve(request(bars=(2.0,4.0))).request['lattice_per_leaf'],[2,4])

    def test_decimal_geometry_and_input_guards_under_optimization(self):
        # 200 original outer-size cases, now using outer-driven picture-free requests.
        code='''import json,tempfile\nfrom pathlib import Path\nfrom decimal import Decimal\nfrom hanok_generator.model import resolve\nfrom hanok_generator.engine import builder\nfrom hanok_generator.engine.generate_spec import derive,ParameterError\nwith tempfile.TemporaryDirectory() as tmp:\n for axis,start in [(0,"463"),(1,"586")]:\n  for i in range(1,101):\n   size=[463,586];size[axis]=float(Decimal(start)+Decimal(i)/10)\n   p=resolve(dict(type="double",outer_mm=size,lattice_per_leaf=[2,4])).parameters\n   builder.configure(p,tmp);_,r,_=builder.build()\n   if r["checks_passed"]!=67 or not r["saved_dxf_reread"]:raise RuntimeError("decimal failure")\n p=resolve(dict(type="double",outer_mm=[463,586],lattice_per_leaf=[2,4])).parameters\n for group,key,value in [("machining","pocket_depth",9),("machining","tool_diameter",10)]:\n  q=json.loads(json.dumps(p));q[group][key]=value\n  try:derive(q)\n  except ParameterError:pass\n  else:raise RuntimeError("guard bypass")\nprint(json.dumps(dict(decimals=200,guards=2,status="PASS")))\n'''
        processes=[]
        for optimized in ("0","1"):
            env={**os.environ,"PYTHONOPTIMIZE":optimized,"PYTHONHASHSEED":"0","PYTHONDONTWRITEBYTECODE":"1"}
            processes.append(subprocess.Popen([sys.executable,"-c",code],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding="utf-8"))
        # Both sweeps run at once; CI runners take about twice as long as a desktop (Windows went past 300 s).
        deadline=time.monotonic()+900
        for p in processes:
            stdout,stderr=p.communicate(timeout=max(0,deadline-time.monotonic()))
            self.assertEqual(p.returncode,0,stderr)
            self.assertEqual(json.loads(stdout)["decimals"],200)
        LOG.append(dict(case="decimal_sweeps",normal=200,optimized=200,input_guards=4,status="PASS"))


if __name__=="__main__":
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(GeneratorTests))
    record=dict(status="PASS" if result.wasSuccessful() else "FAIL",tests=result.testsRun,
                failures=[str(f) for f in result.failures],errors=[str(f) for f in result.errors],cases=LOG,
                source_sha256={name:digest(p) for name,p in source_files()})
    (HERE/"results.json").write_bytes((json.dumps(record,ensure_ascii=False,indent=2)+"\n").encode("utf-8"))
    raise SystemExit(0 if result.wasSuccessful() else 1)
