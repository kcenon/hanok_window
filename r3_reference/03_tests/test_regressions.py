#!/usr/bin/env python3
"""R2 geometry regression, decimal builds and defect injection in temporary files.

Run with the CNC requirements installed. All geometry cases call the production
builder and validator; decimal cases save and reread DXFs without PNG rendering.
Repeat with PYTHONOPTIMIZE=1 to verify that input rejection is not assert-based.
The suite restarts itself under PYTHONHASHSEED=0 so DXF hashes from separate
runs are comparable; --record runs both modes and writes one combined record.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal

HERE=Path(__file__).resolve().parent
CNC=HERE.parent/'02_cnc'
sys.path.insert(0,str(CNC))
import ezdxf
import shapely
from shapely.geometry import box, Polygon
from shapely.affinity import translate
from cad_helpers import entity_polygon, meta, tag
from generate_spec import build as build_spec, derive, ParameterError
from numeric_policy import ARC_CHORD_TOL_MM, geometry_matches, policy_record

BASE=json.loads((CNC/'design_parameters.json').read_text())
DXF_NAME='hanok_window_A3_portrait_double_leaf_one_board_CNC.dxf'
R2_DXF=HERE.parents[1]/'research'/'baselines'/'PORTRAIT_DL_R2'/'02_cnc'/DXF_NAME
LOG=[]


class RegressionBase(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='hanok-regression-')
        self.work=Path(self.temp.name)
        for path in CNC.glob('*.py'):
            shutil.copy2(path,self.work/path.name)

    def tearDown(self):
        self.temp.cleanup()

    def builder(self,parameters):
        (self.work/'design_parameters.json').write_text(json.dumps(parameters)+'\n')
        spec=importlib.util.spec_from_file_location('hanok_regression_builder',self.work/'build_portrait_double_leaf.py')
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def successful_build(self,label,parameters):
        b=self.builder(parameters)
        doc,report,_=b.build()
        self.assertEqual(report['checks_passed'],64,label)
        self.assertTrue(report['saved_dxf_reread'],label)
        self.assertEqual(report['manufacturing_assessment']['status'],'PENDING')
        LOG.append(dict(case=label,parameters=parameters,status='PASS',checks=64,
                        saved_dxf_reread=True,dxf_sha256=report['sha256']))
        return b,doc,report

    def rejected_geometry(self,label,parameters,rule,count=None):
        b=self.builder(parameters)
        with self.assertRaises(b.ValidationError) as caught:
            b.build()
        report=caught.exception.report
        self.assertIn(rule,report['failed_checks'])
        check=next(q for q in report['checks'] if q['name']==rule)
        if count is not None:
            self.assertEqual(len(check['measured']['connections']),count)
        LOG.append(dict(case=label,status='REJECTED_AS_EXPECTED',report=report))
        return check


class Controls(RegressionBase):
    def test_r2_geometry_and_baseline(self):
        reference=json.loads((HERE/'r2_geometry_reference.json').read_text())['spec']
        generated=build_spec(BASE)
        generated['revision']=reference['revision']
        self.assertEqual(generated,reference,'R2 geometry, IDs, mating links and nesting must all stay unchanged')
        _,_,report=self.successful_build('R2_geometry_with_R3_validation',BASE)
        self.assertAlmostEqual(report['manufacturing_assessment']['machined_web']['measured_mm'],29.2666666667,places=6)
        self.assertAlmostEqual(report['manufacturing_assessment']['edge_web']['measured_mm'],16.8,places=6)
        self.assertIsNone(report['manufacturing_assessment']['machined_web']['required_minimum_mm'])

    def test_failed_build_leaves_outputs_untouched(self):
        self.successful_build('before_rejected_rebuild',BASE)
        names=['design_spec.json',DXF_NAME,'validation_report.json','pocket_manifest.csv']
        before={n:hashlib.sha256((self.work/n).read_bytes()).hexdigest() for n in names}
        p=copy.deepcopy(BASE);p['lattice']['vertical_per_leaf']=12
        b=self.builder(p)
        with self.assertRaises(b.ValidationError):b.build()
        self.assertEqual({n:hashlib.sha256((self.work/n).read_bytes()).hexdigest() for n in names},before)
        self.assertEqual(list(self.work.glob('_validated_candidate*')),[])
        LOG.append(dict(case='rejected_rebuild_keeps_previous_outputs',status='PASS',files=before))

    def test_valid_variants(self):
        variants=[]
        p=copy.deepcopy(BASE);p['lattice'].update(vertical_per_leaf=1,horizontal_per_leaf=5)
        variants.append(('lattice_1_5',p))
        p=copy.deepcopy(BASE);p['frame'].update(outer_width=600,outer_height=800);p['picture'].update(sheet_width=434,sheet_height=634)
        variants.append(('outer_600_800',p))
        p=copy.deepcopy(BASE);p['lattice']['end_lap_length']=12
        variants.append(('end_lap_12',p))
        for width,outer,picture in [(40,309,123),(50,349,143)]:
            p=copy.deepcopy(BASE);p['frame']['outer_width']=outer;p['leaf']['member_width']=width
            p['lattice'].update(vertical_per_leaf=1,end_lap_length=35)
            p['picture'].update(sheet_width=picture,sheet_height=480-2*width)
            variants.append((f'end_lap_35_opening_30_sash_{width}',p))
        p=copy.deepcopy(BASE);p['clearance']['frame_to_leaf']=3.1;p['leaf']['member_width']=30.2
        p['picture'].update(sheet_width=296.4,sheet_height=419.4)
        variants.append(('decimal_gap_3_1_member_30_2',p))
        p=copy.deepcopy(BASE);p['frame'].update(outer_width=463.4,outer_height=586.4,member_width=40.1)
        p['clearance'].update(frame_to_leaf=3.1,leaf_to_leaf=3.3);p['leaf']['member_width']=30.2
        p['lattice'].update(bar_width=10.2,end_lap_length=12.2);p['picture'].update(sheet_width=296.6,sheet_height=419.6)
        p['stock'].update(length=1220.3,width=900.7,thickness=20.2)
        p['machining'].update(tool_diameter=6.2,relief_radius=3.4,pocket_depth=10.1)
        variants.append(('combined_decimal_members_gaps_stock_tool_depth',p))
        for label,p in variants:
            with self.subTest(case=label):self.successful_build(label,p)

    def test_explicit_parameter_errors(self):
        changes=[('picture','sheet_width',290,'picture.region_width'),
                 ('picture','sheet_height',410,'picture.region_height'),
                 ('machining','pocket_depth',9,'half_lap.depth'),
                 ('machining','tool_diameter',10,'machining.relief_cutter_compatibility'),
                 ('lattice','vertical_per_leaf',13,'lattice.positive_gap'),
                 ('lattice','end_lap_length',0,'input.finite_dimension'),
                 ('lattice','end_lap_length',30,'lattice.blind_seat_length'),
                 ('lattice','end_lap_length',35,'lattice.blind_seat_length'),
                 ('lattice','end_lap_length',26.8,'lattice.seat_relief_inside_member'),
                 ('machining','relief_radius',20.5,'lattice.seat_relief_inside_member'),
                 ('lattice','vertical_per_leaf',2.5,'input.lattice_count'),
                 ('lattice','vertical_per_leaf',0,'scope.lattice_count'),
                 ('lattice','horizontal_per_leaf',0,'scope.lattice_count'),
                 ('leaf','count',1,'scope.leaf_count'),
                 ('frame','outer_height',float('nan'),'input.finite_dimension'),
                 ('stock','length',600,'nesting.part_fits_stock')]
        for group,field,value,rule in changes:
            with self.subTest(field=f'{group}.{field}',value=value):
                p=copy.deepcopy(BASE);p[group][field]=value
                with self.assertRaises(ParameterError) as caught:build_spec(p)
                self.assertEqual(caught.exception.rule_id,rule)
                LOG.append(dict(case=f'{group}.{field}={value}',status='REJECTED_AS_EXPECTED',rule=rule))
        p=copy.deepcopy(BASE);p['frame'].update(outer_width=523,outer_height=646);p['picture']['region_margin']=40
        with self.assertRaises(ParameterError) as caught:derive(p)
        self.assertEqual(caught.exception.rule_id,'leaf.aspect_ratio')

    def test_overlaps_contacts_and_non_open_edge(self):
        p=copy.deepcopy(BASE);p['lattice']['vertical_per_leaf']=12
        self.rejected_geometry('dense_12_4',p,'distinct_machining_regions_separated',52)
        p=copy.deepcopy(BASE);p['frame']['outer_width']=309;p['leaf']['member_width']=40
        p['lattice']['end_lap_length']=35;p['picture'].update(sheet_width=123,sheet_height=400)
        self.rejected_geometry('lap_guard_removed_dense_control',p,'distinct_machining_regions_separated',4)
        p['frame']['outer_width']=327.4;p['picture']['sheet_width']=141.4
        detail=self.rejected_geometry('tangent_relief_circles',p,'distinct_machining_regions_separated',4)
        self.assertTrue(all(r['overlap_area_mm2']<1e-6 for r in detail['measured']['connections']))
        # Exact tangency (lap 26.8 + R3.2 = 30) is now refused as a parameter.
        # 2 um short of it passes that rule but lies inside the validator's arc
        # and linear uncertainty, so the saved-geometry guard must still reject it.
        p=copy.deepcopy(BASE);p['lattice']['end_lap_length']=26.799998
        detail=self.rejected_geometry('relief_within_uncertainty_of_non_open_edge',p,'machining_preserves_non_open_edges')
        self.assertLess(min(f['distance_mm'] for f in detail['measured']['failures'] if 'distance_mm' in f),1e-5)

    def test_saved_geometry_guards_without_parameter_guard(self):
        for kind,rule in [('picture','picture_margins_match_each_side'),
                          ('tool','machining_relief_radius_at_least_tool_radius')]:
            with self.subTest(kind=kind):
                b,doc,_=self.successful_build('injection_base_'+kind,BASE)
                # Isolate the geometry guard: only omit regeneration of the
                # consistency spec, which would otherwise reject the parameters
                # before we can inspect the independent geometry-check result.
                b.SPEC=self.work/'no_consistency_spec_for_injection.json'
                if kind=='picture':
                    e=next(e for e in doc.modelspace() if meta(e).get('view')=='assembly' and meta(e).get('role')=='picture')
                    points=list(e.get_points('xyb'));right=max(v[0] for v in points)
                    e.set_points([(x-7 if abs(x-right)<1e-7 else x,y,bulge) for x,y,bulge in points],format='xyb')
                    b.A3W=290;b.PARAMS['picture']['sheet_width']=290
                else:
                    b.PARAMS['machining']['tool_diameter']=10
                    for e in doc.modelspace():
                        if e.dxf.layer=='DOGBONE':
                            data=meta(e);data['radius_mm']=999;tag(e,**data)
                for phase in ['IN_MEMORY_BEFORE_SAVE','READ_BACK_FROM_SAVED_DXF']:
                    if phase.startswith('READ'):
                        path=self.work/'injected.dxf';doc.saveas(path);doc=ezdxf.readfile(path)
                    with self.assertRaises(b.ValidationError) as caught:b.validate(doc,phase)
                    report=caught.exception.report;self.assertIn(rule,report['failed_checks'])
                    detail=next(q for q in report['checks'] if q['name']==rule)['measured']
                    if kind=='picture':
                        self.assertAlmostEqual(detail['measured_mm']['right'],17,places=7)
                    else:self.assertAlmostEqual(detail['minimum_actual_radius_mm'],3.2,places=7)
                    LOG.append(dict(case='independent_'+kind,phase=phase,status='REJECTED_AS_EXPECTED',report=report))

    def test_numeric_error_bounds(self):
        target=box(0,0,100,20)
        self.assertTrue(geometry_matches(translate(target,1e-12,-1e-12),target))
        # A thin but long defect cannot pass just because its area is tiny.
        spur=Polygon([(0,0),(100,0),(100,10),(101,10+1e-10),(100,10+2e-10),(100,20),(0,20)])
        self.assertLess(spur.symmetric_difference(target).area,1e-7)
        self.assertFalse(geometry_matches(spur,target))
        for sign in [-1,1]:
            doc=ezdxf.new();radius=3.2;cx,cy=1350.,100.
            e=doc.modelspace().add_lwpolyline([(cx+radius,cy,sign),(cx-radius,cy,sign)],format='xyb',close=True)
            points=list(entity_polygon(e).exterior.coords)
            maximum=max(abs(math.hypot((a[0]+b[0])/2-cx,(a[1]+b[1])/2-cy)-radius)
                        for a,b in zip(points,points[1:]))
            self.assertLessEqual(maximum,ARC_CHORD_TOL_MM+1e-10)
            LOG.append(dict(case=f'circular_chord_bound_bulge_{sign}',status='PASS',maximum_error_mm=maximum))


class DecimalSweep(RegressionBase):
    def test_two_hundred_sizes(self):
        for axis,start in [('width','463'),('height','586')]:
            for i in range(1,101):
                value=Decimal(start)+Decimal(i)/10
                p=copy.deepcopy(BASE);p['frame']['outer_'+axis]=float(value)
                p['picture']['sheet_'+axis]=float(value-166)
                with self.subTest(axis=axis,value=str(value)):
                    self.successful_build(f'decimal_{axis}_{value}',p)
            print(f'Completed {axis}: 100 saved-DXF builds',flush=True)


def reexec_with_fixed_hash_seed():
    """Run under PYTHONHASHSEED=0, as the command-line build does.

    The cases call build() in this process, so they never pass through the
    builder's own restart. Without it ezdxf orders two CLASSES entries by the
    per-process string hash, and DXF hashes from separate runs agree only by chance.
    """
    if os.environ.get('PYTHONHASHSEED')=='0':return
    flags=['-'+'O'*sys.flags.optimize] if sys.flags.optimize else []
    os.execve(sys.executable,[sys.executable,*flags,*sys.argv],{**os.environ,'PYTHONHASHSEED':'0'})


def production_contours(path):
    rows={}
    for e in ezdxf.readfile(path).modelspace():
        if e.dxf.layer in ('CUT_THROUGH','DOGBONE') or e.dxf.layer.startswith('POCKET_'):
            m=meta(e);rows[(e.dxf.layer,m.get('feature_id') or m['part_id'])]=(list(e.get_points('xyb')),m)
    return rows


def record(path):
    """Run the suite normally and with PYTHONOPTIMIZE=1, then write one combined record."""
    runs=[]
    with tempfile.TemporaryDirectory(prefix='hanok-record-') as tmp:
        procs=[]
        for level in (0,1):
            env={k:v for k,v in os.environ.items() if k!='PYTHONOPTIMIZE'}
            env['PYTHONHASHSEED']='0'
            if level:env['PYTHONOPTIMIZE']=str(level)
            out=Path(tmp)/f'run{level}.json';log=open(Path(tmp)/f'run{level}.log','w')
            procs.append((out,log,subprocess.Popen([sys.executable,__file__,'--output',str(out)],
                                                   env=env,stdout=log,stderr=subprocess.STDOUT)))
        for out,log,proc in procs:
            proc.wait();log.close()
            if not out.is_file():raise SystemExit(Path(log.name).read_text()[-3000:])
            runs.append(json.loads(out.read_text()))
    hashes=[{c['case']:c['dxf_sha256'] for c in run['cases'] if 'dxf_sha256' in c} for run in runs]
    comparison=dict(hash_seed='0',cases_compared=len(hashes[0]),
                    identical=sum(h==hashes[1].get(k) for k,h in hashes[0].items()),
                    all_identical=hashes[0]==hashes[1])
    names=[q['name'] for q in json.loads((CNC/'validation_report.json').read_text())['checks']]
    plan=(HERE.parent/'01_plan'/'MERGED_PLAN.md').read_text(encoding='utf-8')
    mapping=dict(total=len(names),missing=[n for n in names if n not in plan])
    r2=dict(spec_including_nesting='checked by Controls.test_r2_geometry_and_baseline in each run')
    if R2_DXF.is_file():
        old,new=production_contours(R2_DXF),production_contours(CNC/DXF_NAME)
        same=sum(old[k]==new.get(k) for k in old)
        r2.update(r2_dxf_sha256=hashlib.sha256(R2_DXF.read_bytes()).hexdigest(),
                  production_contours_compared=len(old),identical_geometry_and_metadata=same,
                  all_identical=same==len(old)==len(new))
    else:r2.update(all_identical=None,reason=f'R2 archive not found: {R2_DXF}')
    ok=all(r['status']=='PASS' for r in runs) and comparison['all_identical'] and not mapping['missing'] \
        and r2['all_identical'] is not False
    path.write_text(json.dumps(dict(
        revision=BASE['revision'],status='PASS' if ok else 'FAIL',dxf_hash_comparison=comparison,
        r2_geometry_preservation=r2,plan_check_mapping=mapping,
        test_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='Each sweep case generated, saved and reread a DXF; PNG rendering is verified separately for the '
              'released default package. This is not a proof for all parameter combinations or material strength.',
        runs=runs),ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(status='PASS' if ok else 'FAIL',dxf_hash_comparison=comparison,
                          plan_check_mapping=mapping,r2=r2),ensure_ascii=False))
    return 0 if ok else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite',choices=['all','controls','decimals'],default='all')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--record',type=Path,help='run normally and with -O, then write the combined record here')
    args=parser.parse_args()
    reexec_with_fixed_hash_seed()
    if args.record:return record(args.record)
    suite=unittest.TestSuite()
    if args.suite in ('all','controls'):suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    if args.suite in ('all','decimals'):suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(DecimalSweep))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report=dict(status='PASS' if result.wasSuccessful() else 'FAIL',python=sys.version,
                optimization=sys.flags.optimize,ezdxf=ezdxf.__version__,shapely=shapely.__version__,
                revision=BASE['revision'],numeric_policy=policy_record(),tests_run=result.testsRun,
                failures=[str(q) for q in result.failures],errors=[str(q) for q in result.errors],cases=LOG,
                source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(CNC.glob('*.py'))})
    if args.output:
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':
    raise SystemExit(main())
