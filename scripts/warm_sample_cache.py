"""
Pre-compute the built-in sample's translations so the "Try it with a sample
lesson" button never costs anything on the deployed site.

    python scripts/warm_sample_cache.py            # all languages
    python scripts/warm_sample_cache.py es ar      # just these

Runs the full pipeline on samples/fractions_lesson.zip with REAL, BILLED
OpenAI calls (needs OPENAI_API_KEY; with gpt-5-mini the whole sample in all
five languages costs roughly $0.05-0.10), and stores every model answer in
samples/translation_cache.json. Commit that file: the web app reads it for
sample runs, and only calls the API for prompts it doesn't contain. Re-running
is cheap - answers already in the cache are reused, not re-requested.
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402  (loads .env)
import languages  # noqa: E402
import limits  # noqa: E402
import llm  # noqa: E402
import translate  # noqa: E402
import uploads  # noqa: E402
from jobs import JobStore  # noqa: E402
from pipeline import JobRunner  # noqa: E402
from state import StateDB  # noqa: E402


def main(langs):
    if not llm.has_api_key():
        sys.exit("OPENAI_API_KEY is not set (put it in .env). This script makes real API calls.")
    cache_path = ROOT / "samples" / "translation_cache.json"
    client = llm.CachingClient(llm.LazyClient(llm.make_client), cache_path)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        store = JobStore(StateDB(tmp / "state.db"), tmp / "jobs")
        job_dir = tmp / "jobs" / "warm"
        job_dir.mkdir(parents=True)
        upload = job_dir / "upload.zip"
        upload.write_bytes(config.settings.sample_zip.read_bytes())
        prepared = uploads.prepare_upload(upload, "fractions_lesson.zip", job_dir)
        store.create("warm", langs=langs, source_name=prepared.idml_filename, is_sample=True)
        runner = JobRunner(store, "warm", job_dir=job_dir, extracted_dir=prepared.extracted_dir,
                           idml_filename=prepared.idml_filename, langs=langs, client=client,
                           model=translate.DEFAULT_MODEL,
                           on_usage=lambda m, p, c: store.add_usage("warm", m, p, c))
        runner.run()
        job = store.get("warm")
    cost = limits.compute_cost(job["usage"])
    print(f"Status: {job['status']}  languages: {job['lang_status']}")
    print(f"New API calls: {job['usage']['calls']}  answered from cache: {client.hits}  "
          f"cost: {('$%.4f' % cost['usd']) if cost.get('available') else cost.get('note')}")
    print(f"Cache: {cache_path.relative_to(ROOT)} - commit it so the deployed sample is free.")


if __name__ == "__main__":
    chosen = sys.argv[1:] or list(languages.LANGUAGES)
    unknown = [c for c in chosen if c not in languages.LANGUAGES]
    if unknown:
        sys.exit(f"Unknown language code(s): {', '.join(unknown)}. Choose from {', '.join(languages.LANGUAGES)}.")
    main(chosen)
