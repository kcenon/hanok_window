"""Build queue: jobs.run_job on worker threads, bounded waiting and in-memory status."""
from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import threading
import time
import uuid

from ..jobs import JobError, run_job
from .service import failure

KEEP_FINISHED = 100  # status records only; packages and failure reports stay on disk
ACTIVE = ("queued", "running")
RESULT_FIELDS = ("status", "package_id", "checks", "parts", "pockets", "dogbones", "manufacturing_status")


class QueueFull(Exception):
    pass


def trim_check(check, limit=8):
    """A failed check with its long measurement lists cut to the first entries."""
    out = {k: check[k] for k in ("rule_id", "name", "message", "status", "expected", "actual", "targets", "tolerance")
           if k in check}
    measured = check.get("measured")
    if isinstance(measured, dict):
        out["measured"] = {}
        for key, value in measured.items():
            if isinstance(value, list) and len(value) > limit:
                out["measured"][key + "_total"] = len(value)
                value = value[:limit]
            out["measured"][key] = value
    return out


def failed_build(result):
    """Browser-sized form of a run_job failure; the full record stays in output/failures/."""
    details = result.get("details")
    body = failure(result.get("rule_id", "job.failed"), result.get("message", ""),
                   details if isinstance(details, dict) else {})
    if body["where"] == "request" and not body["rule_id"].startswith("input."):
        body["where"] = "result"
    if isinstance(details, str):
        body["log"] = details[-2000:]  # worker stderr when it stopped without writing a result
    if "job_id" in result:
        body.update(job_id=result["job_id"], failure_report=f"failures/{result['job_id']}.json")
    validation = result.get("validation")
    if isinstance(validation, dict):
        checks = validation.get("checks", [])
        body["validation"] = dict(status=validation.get("status"), phase=validation.get("phase"),
                                  total=len(checks), passed=sum(c.get("status") == "PASS" for c in checks),
                                  failed_checks=validation.get("failed_checks", []),
                                  failed=[trim_check(c) for c in checks if c.get("status") != "PASS"])
    return body


class BuildQueue:
    """At most `workers` builds run and `waiting` more wait. A thread only waits for the
    worker process that run_job starts, so the builder never loads in this process."""

    def __init__(self, output, *, workers=2, waiting=8, runner=run_job, timeout=120):
        self.output, self.workers, self.waiting = output, workers, waiting
        self.runner, self.timeout = runner, timeout
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="hanok-build")
        self._lock = threading.Lock()
        self._records = OrderedDict()

    def submit(self, request):
        with self._lock:
            if sum(r["state"] in ACTIVE for r in self._records.values()) >= self.workers + self.waiting:
                raise QueueFull(self.workers + self.waiting)
            build_id = uuid.uuid4().hex
            self._records[build_id] = dict(state="queued", request=request, submitted=time.monotonic(),
                                           started=None, finished=None, result=None, error=None)
            finished = [k for k, r in self._records.items() if r["state"] not in ACTIVE]
            for key in finished[:max(0, len(finished) - KEEP_FINISHED)]:
                del self._records[key]
        self._pool.submit(self._run, build_id)
        return self.status(build_id)

    def _run(self, build_id):
        with self._lock:
            record = self._records[build_id]
            record.update(state="running", started=time.monotonic())
        try:
            result = self.runner(record["request"], self.output, timeout=self.timeout)
            update = dict(state="passed", result={k: result[k] for k in RESULT_FIELDS})
        except JobError as exc:
            update = dict(state="failed", error=failed_build(exc.result))
        except Exception as exc:  # run_job reports through JobError; anything else is a defect
            update = dict(state="failed", error=failed_build(dict(rule_id="job.failed", message=str(exc))))
        with self._lock:
            record.update(update, finished=time.monotonic())

    def status(self, build_id):
        with self._lock:
            record = self._records.get(build_id)
            if record is None:
                return None
            now = time.monotonic()
            queued = [k for k, r in self._records.items() if r["state"] == "queued"]
            started, finished = record["started"], record["finished"]
            return dict(build_id=build_id, state=record["state"], request=record["request"],
                        position=queued.index(build_id) + 1 if build_id in queued else None,
                        waited_s=round((started or now) - record["submitted"], 2),
                        elapsed_s=round((finished or now) - started, 2) if started else 0.0,
                        result=record["result"], error=record["error"])

    def shutdown(self):
        """Wait for running builds (run_job's timeout bounds each one) and cancel waiting ones."""
        self._pool.shutdown(wait=True, cancel_futures=True)
