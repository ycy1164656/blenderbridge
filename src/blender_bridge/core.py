"""No bpy: protocol, bounded jobs, request deduplication and output boundary."""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import queue
import secrets
import shutil
import threading
import time
import uuid
from .catalog import OPS, validate


class BridgeError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def default_sessions():
    return Path(os.environ.get("BLENDER_BRIDGE_SESSIONS", Path.home() / ".blender-bridge" / "sessions"))


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(temp, 0o600)
    temp.replace(path)


class RuntimeState:
    def __init__(self, output_root, read_roots=(), allow_python=False, max_jobs=1000):
        self.session = str(uuid.uuid4())
        self.token = secrets.token_urlsafe(32)
        self.revision = 0
        self.output_root = Path(output_root).resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.read_roots = [self.output_root] + [Path(p).resolve() for p in read_roots]
        self.allow_python = allow_python
        self.max_jobs = max_jobs
        self.jobs = {}
        self.pending = queue.Queue(maxsize=128)
        self.lock = threading.RLock()
        self.snapshot = {}
        self.artifacts = {}
        self.active_job = None
        self.started = time.time()
        self.selections = {}
        self.bake_plans = {}
        self.preview_metadata = {}
        self.registry_path = self.output_root / '.bridge' / 'artifacts.json'
        if self.registry_path.is_file():
            self.artifacts = json.loads(self.registry_path.read_text(encoding='utf-8'))
        journal = self.output_root / '.bridge' / 'runtime-journal.jsonl'
        if journal.is_file():
            for line in journal.read_text(encoding='utf-8').splitlines():
                try:
                    entry = json.loads(line)
                    self.jobs[entry['id']] = entry
                except (ValueError, KeyError):
                    continue
            for job in self.jobs.values():
                if job['state'] in ('queued', 'running'):
                    job.update(state='interrupted', error={'code':'RESULT_UNKNOWN','message':'Previous runtime ended before a terminal outcome; inspect artifacts, never replay automatically'})

    def health(self):
        with self.lock:
            from . import __version__
            return {"bridge_version": __version__, "protocol_version": 1, "session": self.session,
                    "revision": self.revision, "pid": os.getpid(), "active_job": self.active_job,
                    "started": self.started, "output_root": str(self.output_root),
                    "allow_python": self.allow_python, "snapshot": copy.deepcopy(self.snapshot)}

    def submit(self, request):
        if set(request) - {"operation", "args", "session", "revision", "request_id"}:
            raise BridgeError("INVALID_REQUEST", "Unknown request fields")
        rid = request.get("request_id")
        if not isinstance(rid, str) or not 8 <= len(rid) <= 128:
            raise BridgeError("INVALID_REQUEST", "Stable request_id of 8..128 characters required")
        name = request.get("operation")
        if name not in OPS:
            raise BridgeError("UNKNOWN_OPERATION", str(name))
        if OPS[name]['execution_domain'] != 'blender_main_thread':
            raise BridgeError('WRONG_EXECUTION_DOMAIN', 'Use the Host gateway for this operation')
        validate(request.get("args", {}), OPS[name]["inputSchema"])
        if name == "python.execute" and not self.allow_python:
            raise BridgeError("PYTHON_DISABLED", "Trusted Python is disabled in this runtime")
        fingerprint = hashlib.sha256(json.dumps(request, sort_keys=True, allow_nan=False).encode()).hexdigest()
        with self.lock:
            if rid in self.jobs:
                if self.jobs[rid]["fingerprint"] != fingerprint:
                    raise BridgeError("REQUEST_ID_CONFLICT", "Request ID already belongs to different arguments")
                return self.job(rid)
            self.check_context(request)
            if sum(j.get('request',{}).get('session')==self.session for j in self.jobs.values()) >= self.max_jobs:
                raise BridgeError("SESSION_CAPACITY", "Job history is full; checkpoint and start a new runtime. IDs are never silently evicted.")
            if self.pending.full():
                raise BridgeError("QUEUE_FULL", "Too many queued operations")
            job = {"id": rid, "operation": name, "state": "queued", "submitted": time.time(),
                   "request": copy.deepcopy(request), "fingerprint": fingerprint}
            self.jobs[rid] = job
            self._journal(job)
            self.pending.put_nowait(rid)
            return self.job(rid)

    def check_context(self, request):
        if request.get("session") != self.session:
            raise BridgeError("STALE_SESSION", "Re-discover the Blender session; never auto-retarget a write")
        revision = request.get("revision")
        guarded = OPS[request["operation"]]['requires_revision']
        if (guarded or revision is not None) and (type(revision) is not int or revision != self.revision):
            raise BridgeError("STALE_REVISION", f"Inspect scene again; current revision is {self.revision}")

    def job(self, rid):
        with self.lock:
            if rid not in self.jobs:
                raise BridgeError("JOB_NOT_FOUND", "Job not found in this runtime")
            return copy.deepcopy({k: v for k, v in self.jobs[rid].items() if k not in ("request", "fingerprint")})

    def cancel(self, rid):
        with self.lock:
            self.job(rid)
            if self.jobs[rid]["state"] != "queued":
                raise BridgeError("CANNOT_CANCEL", "Only queued jobs can be cancelled; running bpy calls cannot be interrupted safely")
            self.jobs[rid]["state"] = "cancelled"
            self._journal(self.jobs[rid])
            return self.job(rid)

    def output_path(self, name, suffix, overwrite=False):
        path = Path(name)
        if not path.is_absolute():
            path = self.output_root / path
        path = path.resolve()
        if not path.is_relative_to(self.output_root) or path == self.output_root or path.suffix.lower() != suffix:
            raise BridgeError("PATH_DENIED", f"Expected {suffix} file beneath output_root")
        if path.exists():
            if not overwrite:
                raise BridgeError("FILE_EXISTS", "Choose a new path or explicitly set overwrite=true")
            backup = self.output_root / ".backups" / f"{time.time_ns()}-{path.name}"
            backup.parent.mkdir(exist_ok=True)
            shutil.copy2(path, backup)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def input_path(self, name):
        path = Path(name).resolve()
        if not any(path.is_relative_to(root) for root in self.read_roots) or not path.is_file():
            raise BridgeError("PATH_DENIED", "Input must exist under a configured read root")
        return path

    def artifact(self, path, kind, provenance=None):
        path = Path(path).resolve()
        if not path.is_relative_to(self.output_root) or not path.is_file() or not path.stat().st_size:
            raise BridgeError("ARTIFACT_MISSING", "Output is missing or empty")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        aid = str(uuid.uuid4())
        effective_revision = self.revision + int(bool(self.active_job and OPS[self.jobs[self.active_job]['operation']]['mutates']))
        result = {"id": aid, "path": str(path), "kind": kind, "bytes": path.stat().st_size,
                  "sha256": digest.hexdigest(), "session": self.session, "revision": effective_revision,
                  "created": time.time()}
        if provenance is not None:
            result['provenance'] = provenance
        with self.lock:
            self.artifacts[aid] = result
            atomic_json(self.registry_path, self.artifacts)
        return result

    def annotate_artifact(self, aid, **values):
        with self.lock:
            self.artifacts[aid].update(values)
            atomic_json(self.registry_path, self.artifacts)
            return copy.deepcopy(self.artifacts[aid])

    def _journal(self, job):
        path = self.output_root / '.bridge' / 'runtime-journal.jsonl'
        path.parent.mkdir(exist_ok=True)
        entry = {k:v for k,v in job.items() if k != 'request'}
        with path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(entry, ensure_ascii=False, allow_nan=False) + '\n')

    def rotate_session(self):
        self.session = str(uuid.uuid4())
        self.selections.clear()

    def execute_one(self, executor, snapshot):
        try:
            rid = self.pending.get_nowait()
        except queue.Empty:
            return
        job = self.jobs[rid]
        with self.lock:
            if job["state"] != "queued":
                return
            self.active_job = rid
            job.update(state="running", started=time.time(), before_revision=self.revision)
            self._journal(job)
        touched = False
        try:
            with self.lock:
                self.check_context(job["request"])
            touched = OPS[job["operation"]]["mutates"]
            result = executor(job["operation"], job["request"].get("args", {}))
            # Verify serializability before reporting success.
            json.dumps(result, allow_nan=False)
            job.update(state="succeeded", result=result)
        except Exception as exc:
            job.update(state="failed", error={"code": getattr(exc, "code", "OPERATION_FAILED"),
                                               "message": str(exc), "partial_changes_possible": touched})
            if hasattr(exc,'details'): job['error']['details']=exc.details
        finally:
            with self.lock:
                if touched:
                    self.revision += 1
                self.active_job = None
                job.update(finished=time.time(), revision=self.revision)
                job['after_revision'] = self.revision
                job['session'] = self.session
                try:
                    self.snapshot = snapshot()
                except Exception as exc:
                    self.snapshot = {"error": str(exc)}
                # Audit excludes arbitrary code and secrets, persists terminal outcome.
                record = self.job(rid)
                self._journal(job)
                log = self.output_root / ".bridge" / "jobs.jsonl"
                log.parent.mkdir(exist_ok=True)
                try:
                    with log.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
                except OSError as exc:
                    job['audit_warning'] = str(exc)

