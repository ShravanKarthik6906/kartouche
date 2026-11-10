"""Shared fixtures. Tests never touch the network or need an API key: the
OpenAI client is replaced by tests/fake_openai.FakeOpenAI."""

import os
import shutil
import sys
import time
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Make sure nothing in a developer's .env leaks into tests: stop config.py's
# load_dotenv() from reading .env at all, then clear anything already exported.
import dotenv  # noqa: E402
dotenv.load_dotenv = lambda *args, **kwargs: False
for var in ("OPENAI_API_KEY", "SITE_PASSWORD", "PUBLIC_DEMO", "ROSETTA_DATA_DIR", "DAILY_SPEND_CAP_USD",
            "RATE_LIMIT_JOBS_PER_HOUR", "RATE_LIMIT_SAMPLES_PER_HOUR", "MAX_WORDS_PER_JOB", "MAX_UPLOAD_MB",
            "MAX_CONCURRENT_JOBS", "JOB_TTL_HOURS", "SAMPLE_CACHE_PATH"):
    os.environ.pop(var, None)
os.environ["ROSETTA_OPENAI_MODEL"] = "gpt-5-mini"   # a model with configured pricing
os.environ.setdefault("TRANSLATE_CONCURRENCY", "4")

from fake_openai import FakeOpenAI  # noqa: E402

SAMPLE_DIR = ROOT / "samples" / "fractions_lesson"
SAMPLE_IDML = SAMPLE_DIR / "fractions_lesson.idml"
SAMPLE_ZIP = ROOT / "samples" / "fractions_lesson.zip"


@pytest.fixture
def sample_extracted(tmp_path):
    """The sample IDML unpacked with its Links folder, as the pipeline expects."""
    out = tmp_path / "idml"
    with zipfile.ZipFile(SAMPLE_IDML) as zf:
        zf.extractall(out)
    shutil.copytree(SAMPLE_DIR / "Links", out / "Links")
    return out


@pytest.fixture
def make_settings(tmp_path, monkeypatch):
    def make(**env):
        for k, v in env.items():
            monkeypatch.setenv(k, str(v))
        import config
        s = config.Settings()
        s.data_dir = tmp_path / "data"
        s.sample_cache_path = tmp_path / "data" / "sample_cache.json"
        s.sample_cache_seed = tmp_path / "no_seed.json"
        return s
    return make


@pytest.fixture
def make_app(make_settings):
    """Build an app wired to a fake OpenAI. Returns (app, client, fakes)."""
    def make(fake_cls=FakeOpenAI, **env):
        import app as appmod
        fakes = []

        def factory():
            f = fake_cls()
            fakes.append(f)
            return f
        application = appmod.create_app(make_settings(**env), openai_factory=factory, start_cleanup_thread=False)
        application.config["TESTING"] = True
        return application, application.test_client(), fakes
    return make


def wait_for_job(application, job_id, timeout=90):
    store = application.extensions["rosetta"]["store"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = store.get(job_id)
        if job and job["status"] not in ("queued", "running") and job_id not in \
                application.extensions["rosetta"].get("runners", {}):
            return job
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")
