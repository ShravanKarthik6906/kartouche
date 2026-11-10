"""
Job state for the web app: kept in memory while a job runs and written to
the state database, so a page refresh or a server restart shows the real
state instead of a 404.

Rosetta runs jobs in background threads of a single server process, so any
job still marked "running" when the process starts was cut off by a restart
and is marked "interrupted". (This is why render.yaml runs one worker.)
"""

import copy
import json
import shutil
import threading
import time
import uuid
from pathlib import Path

# Pipeline steps in order, as shown to the visitor. weight = share of the
# overall progress bar (translation dominates the running time).
STEPS = [
    ("read", "Reading your document", 4),
    ("find", "Finding text on each page", 4),
    ("translate", "Translating", 70),
    ("fit", "Fitting text to the layout", 12),
    ("qa", "Quality checks", 4),
    ("build", "Building your file", 6),
]
STEP_KEYS = [s[0] for s in STEPS]

ACTIVE = ("queued", "running")
SAVE_INTERVAL_SECONDS = 1.0


def new_job_id():
    return uuid.uuid4().hex[:16]


class JobStore:
    def __init__(self, db, jobs_root: Path):
        self.db = db
        self.jobs_root = Path(jobs_root)
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        self._jobs = {}           # job_id -> dict, for jobs owned by this process
        self._last_saved = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------ lifecycle

    def mark_orphans_interrupted(self):
        """Call once at start-up: jobs left running by a previous process are dead."""
        for row in self.db.query("SELECT id, data FROM jobs"):
            data = json.loads(row["data"])
            if data.get("status") in ACTIVE:
                data["status"] = "interrupted"
                data["updated_at"] = time.time()
                self.db.execute("UPDATE jobs SET data = ?, updated_at = ? WHERE id = ?",
                                (json.dumps(data), data["updated_at"], row["id"]))

    def create(self, job_id, *, langs, source_name, is_sample=False, notices=None, word_count=0):
        now = time.time()
        job = {
            "id": job_id,
            "status": "queued",
            "step": None,
            "step_progress": None,         # [done, total] within the current step
            "step_started_at": None,
            "steps_done": [],
            "langs": langs,
            "lang_status": {l: {"state": "pending", "error": None} for l in langs},
            "source_name": source_name,
            "is_sample": is_sample,
            "word_count": word_count,
            "notices": notices or [],
            "log": [],
            "error": None,                 # {"code", "title", "message", "detail"}
            "results": {},
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": 0,
                      "model": None, "cached_calls": 0},
            "cost": None,
            "created_at": now,
            "started_at": None,
            "finished_at": None,
            "updated_at": now,
        }
        with self._lock:
            self._jobs[job_id] = job
        self._save(job_id, force=True)
        return job

    def finish(self, job_id):
        """Persist the final state and stop holding the job in memory."""
        self._save(job_id, force=True)
        with self._lock:
            self._jobs.pop(job_id, None)
            self._last_saved.pop(job_id, None)

    # ------------------------------------------------------------ updates

    def update(self, job_id, force=False, **fields):
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.update(fields)
            job["updated_at"] = time.time()
        self._save(job_id, force=force)

    def mutate(self, job_id, fn, force=False):
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            fn(job)
            job["updated_at"] = time.time()
        self._save(job_id, force=force)

    def log(self, job_id, message):
        def add(job):
            job["log"].append(f"{time.strftime('%H:%M:%S')}  {message}")
            job["log"] = job["log"][-400:]
        self.mutate(job_id, add)

    def add_usage(self, job_id, model, prompt_tokens, completion_tokens):
        def add(job):
            u = job["usage"]
            u["prompt_tokens"] += prompt_tokens
            u["completion_tokens"] += completion_tokens
            u["total_tokens"] += prompt_tokens + completion_tokens
            u["calls"] += 1
            u["model"] = model
        self.mutate(job_id, add)

    def _save(self, job_id, force=False):
        now = time.time()
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            if not force and now - self._last_saved.get(job_id, 0) < SAVE_INTERVAL_SECONDS:
                return
            self._last_saved[job_id] = now
            blob = json.dumps(job)
            created = job["created_at"]
        self.db.execute(
            "INSERT INTO jobs (id, data, created_at, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
            (job_id, blob, created, now),
        )

    # ------------------------------------------------------------ reads

    def get(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                return copy.deepcopy(job)
        rows = self.db.query("SELECT data FROM jobs WHERE id = ?", (job_id,))
        return json.loads(rows[0]["data"]) if rows else None

    def running_count(self):
        with self._lock:
            return sum(1 for j in self._jobs.values() if j["status"] in ACTIVE)

    def job_dir(self, job_id):
        return self.jobs_root / job_id

    # ------------------------------------------------------------ cleanup

    def cleanup(self, max_age_hours):
        """Delete finished jobs (folder + record) older than max_age_hours. Returns count removed."""
        if max_age_hours <= 0:
            return 0
        cutoff = time.time() - max_age_hours * 3600
        removed = 0
        for row in self.db.query("SELECT id FROM jobs WHERE created_at < ?", (cutoff,)):
            with self._lock:
                if row["id"] in self._jobs:
                    continue  # still running in this process
            shutil.rmtree(self.job_dir(row["id"]), ignore_errors=True)
            self.db.execute("DELETE FROM jobs WHERE id = ?", (row["id"],))
            removed += 1
        # Folders with no record at all (e.g. a crash mid-upload)
        for d in self.jobs_root.iterdir():
            if d.is_dir() and d.stat().st_mtime < cutoff and not self.db.query("SELECT 1 FROM jobs WHERE id = ?", (d.name,)):
                shutil.rmtree(d, ignore_errors=True)
                removed += 1
        return removed
