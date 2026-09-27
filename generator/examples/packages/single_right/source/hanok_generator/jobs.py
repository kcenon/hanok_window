"""Isolated builds, immutable completed packages, and one atomic latest pointer."""
from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

from .model import InputError, resolve
from .package import PackageError, verify, write_json


class JobError(RuntimeError):
    def __init__(self,result):
        self.result=result
        super().__init__(result["message"])


# On Windows os.replace() fails with PermissionError while another handle has the
# target open: two builds that finish together, or a reader of latest.json. Such
# handles are short-lived, so wait a little and try again, under two seconds in all.
POINTER_RETRY_DELAYS=(0.01,0.02,0.05,0.1,0.2,0.5,1.0)


def replace_pointer(source,target):
    for delay in POINTER_RETRY_DELAYS:
        try:
            return os.replace(source,target)
        except PermissionError:
            time.sleep(delay)
    return os.replace(source,target)


def run_job(request, output, *, timeout=120, _fault=None):
    root=Path(output).resolve()
    root.mkdir(parents=True,exist_ok=True)
    job_id=uuid.uuid4().hex
    stage=None
    try:
        design=resolve(request)
        staging=root/".staging";staging.mkdir(exist_ok=True)
        stage=Path(tempfile.mkdtemp(prefix=job_id+"-",dir=staging))
        package=stage/"package";package.mkdir()
        write_json(stage/"payload.json",asdict(design))
        # Explicit PYTHONPATH also supports the included source bundle, without installation.
        source_root=str(Path(__file__).parent.parent)
        env={**os.environ,"PYTHONHASHSEED":"0","PYTHONDONTWRITEBYTECODE":"1","PYTHONPATH":source_root,"PYTHONIOENCODING":"utf-8"}
        command=[sys.executable,"-m","hanok_generator.worker",str(stage/"payload.json"),str(package),str(stage/"result.json")]
        if _fault and _fault not in ("publish","pointer"):
            command.extend(["--fault",_fault])
        process=subprocess.run(command,env=env,cwd=stage,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=timeout)
        if not (stage/"result.json").is_file():
            raise JobError(dict(status="FAIL",rule_id="worker.stopped",message="작업 프로세스가 결과를 완성하지 못했습니다.",
                                returncode=process.returncode,details=process.stderr[-4000:]))
        result=json.loads((stage/"result.json").read_text(encoding="utf-8"))
        if process.returncode or result.get("status")!="PASS":
            raise JobError(result)
        checked=verify(package)
        packages=root/"packages";packages.mkdir(exist_ok=True)
        final=packages/checked["package_id"]
        if _fault=="publish":
            raise OSError("Injected failure before publication")
        try:
            # New destination on the same filesystem: no overwrite of an old package.
            package.rename(final)
        except OSError:
            # Concurrent identical builds may have already published this exact content.
            if not final.is_dir() or verify(final)["package_id"]!=checked["package_id"]:
                raise
        if _fault=="pointer":
            raise OSError("Injected failure before latest pointer replacement")
        latest=dict(package_id=checked["package_id"],path=f"packages/{checked['package_id']}")
        pointer=stage/"latest.json"
        write_json(pointer,latest)
        replace_pointer(pointer,root/"latest.json")
        return dict(**result,package=str(final),manifest=str(final/"package_manifest.json"))
    except Exception as exc:
        if isinstance(exc,JobError):
            result=exc.result
        elif isinstance(exc,InputError):
            result=dict(status="FAIL",**exc.record())
        else:
            result=dict(status="FAIL",rule_id="job.timeout" if isinstance(exc,subprocess.TimeoutExpired) else "job.failed",message=str(exc))
        failures=root/"failures";failures.mkdir(exist_ok=True)
        result=dict(result,job_id=job_id)
        record=failures/f"{job_id}.json";write_json(record,result)
        result["failure_report"]=str(record)
        raise JobError(result) from exc
    finally:
        if stage is not None:
            shutil.rmtree(stage,ignore_errors=True)
