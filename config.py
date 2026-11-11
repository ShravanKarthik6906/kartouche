"""
Web-app settings, all read from environment variables (or .env) in one
place. Every variable is documented in .env.example and render.yaml.

Two modes:
  * Private (default): optional SITE_PASSWORD gate, no usage limits.
  * Public demo (PUBLIC_DEMO=true): no password; per-visitor rate limits, a
    document size limit and a daily spending cap protect the OpenAI bill.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent


def _bool(name, default=False):
    v = os.environ.get(name)
    if v is None or v.strip() == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _float(name, default):
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return float(default)


def _int(name, default):
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return int(default)


class Settings:
    def __init__(self):
        self.public_demo = _bool("PUBLIC_DEMO")
        # The password gate only applies in private mode.
        self.site_password = None if self.public_demo else (os.environ.get("SITE_PASSWORD") or None)

        # KARTOUCHE_DATA_DIR; the pre-rename ROSETTA_DATA_DIR is still read as a fallback
        # so an existing deployment keeps working until its settings are updated.
        self.data_dir = Path(os.environ.get("KARTOUCHE_DATA_DIR") or os.environ.get("ROSETTA_DATA_DIR")
                             or ROOT / "webapp_jobs")
        self.max_upload_mb = _float("MAX_UPLOAD_MB", 50)
        self.job_ttl_hours = _float("JOB_TTL_HOURS", 24)

        # Limits. Defaults are on in public mode and off (0 = unlimited) in private mode.
        pub = self.public_demo
        self.jobs_per_hour = _int("RATE_LIMIT_JOBS_PER_HOUR", 3 if pub else 0)
        self.samples_per_hour = _int("RATE_LIMIT_SAMPLES_PER_HOUR", 20 if pub else 0)
        self.max_words = _int("MAX_WORDS_PER_JOB", 2500 if pub else 0)
        self.daily_spend_cap_usd = _float("DAILY_SPEND_CAP_USD", 2.0 if pub else 0)
        self.max_concurrent_jobs = _int("MAX_CONCURRENT_JOBS", 2 if pub else 4)

        self.sample_zip = ROOT / "samples" / "fractions_lesson.zip"
        # Committed, read-only answers for the sample (see scripts/warm_sample_cache.py).
        self.sample_cache_seed = ROOT / "samples" / "translation_cache.json"
        self.sample_cache_path = Path(os.environ.get("SAMPLE_CACHE_PATH") or self.data_dir / "sample_cache.json")

    @property
    def max_upload_bytes(self):
        return int(self.max_upload_mb * 1024 * 1024)


settings = Settings()


def reload():
    """Re-read the environment (used by tests)."""
    global settings
    settings = Settings()
    return settings
