"""
Rosetta web app.

A thin Flask layer over the pipeline: it validates uploads (uploads.py),
runs the pipeline in a background thread (pipeline.py), keeps job state on
disk (jobs.py), enforces the public-demo limits (limits.py), and serves the
results, preview and downloads. No translation or layout logic lives here.

Run locally:
    python app.py            # http://127.0.0.1:5050

Settings come from environment variables / .env; see config.py and
.env.example. Two modes:
  * private (default): optional SITE_PASSWORD (HTTP Basic Auth), no limits;
  * PUBLIC_DEMO=true: open to everyone, with per-visitor rate limits, a
    document size limit and a daily spending cap.
"""

import logging
import os
import shutil
import threading
import time
from pathlib import Path

from flask import (Flask, Response, abort, jsonify, redirect, render_template, request, send_file,
                   send_from_directory, url_for)
from werkzeug.middleware.proxy_fix import ProxyFix

import config
import languages
import limits
import llm
import translate
import uploads
from jobs import STEPS, JobStore, new_job_id
from pipeline import JobRunner
from state import StateDB

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("rosetta.app")

ROOT = Path(__file__).resolve().parent
FONT_FILES = {"Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-Bold.ttf",
              "NotoSansArabic-Regular.ttf", "NotoSansArabic-Bold.ttf"}
CLEANUP_INTERVAL_SECONDS = 30 * 60


def create_app(settings=None, openai_factory=None, start_cleanup_thread=True):
    """
    settings: a config.Settings (defaults to the environment).
    openai_factory: callable returning an OpenAI-compatible client, used
    instead of the real one (tests pass a fake). Called lazily, only when a
    call actually has to reach the API.
    """
    s = settings or config.settings
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = s.max_upload_bytes
    app.config["SETTINGS"] = s
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=int(os.environ.get("PROXY_COUNT", "1")), x_proto=1)

    s.data_dir.mkdir(parents=True, exist_ok=True)
    db = StateDB(s.data_dir / "state.db")
    store = JobStore(db, s.data_dir / "jobs")
    store.mark_orphans_interrupted()
    ledger = limits.SpendLedger(db, s.daily_spend_cap_usd)
    limiter = limits.RateLimiter(db)
    model = translate.DEFAULT_MODEL
    app.extensions["rosetta"] = {"db": db, "store": store, "ledger": ledger, "limiter": limiter}

    def cleanup():
        try:
            n = store.cleanup(s.job_ttl_hours)
            if n:
                log.info("Cleaned up %d old job(s)", n)
        except Exception:
            log.exception("Cleanup failed")

    cleanup()
    if start_cleanup_thread:
        def loop():
            while True:
                time.sleep(CLEANUP_INTERVAL_SECONDS)
                cleanup()
        threading.Thread(target=loop, daemon=True, name="rosetta-cleanup").start()

    # ------------------------------------------------------------ access + headers

    @app.before_request
    def gate():
        if not s.site_password or request.path == "/healthz":
            return None
        auth = request.authorization
        if not auth or auth.password != s.site_password:
            return Response("Authentication required.", 401, {"WWW-Authenticate": 'Basic realm="Rosetta"'})
        return None

    @app.after_request
    def headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if resp.mimetype == "text/html" and not request.path.startswith("/download/"):
            resp.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
                "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        return resp

    # ------------------------------------------------------------ helpers

    def lang_list():
        return [{"code": l.code, "name": l.name, "native": l.native, "rtl": l.rtl,
                 "selected": l.code in languages.DEFAULT_SELECTION} for l in languages.LANGUAGES.values()]

    def uploads_paused_reason():
        """Why new (non-sample) uploads can't start right now, or None."""
        if not llm.has_api_key() and openai_factory is None:
            return ("Translation isn't set up on this server yet (there's no OpenAI API key), so only the sample "
                    "lesson can run, and only if its translations are already cached.")
        if s.public_demo and not limits.price_for(model):
            return "Uploads are paused: this demo can't track the cost of the configured translation model."
        if s.public_demo and ledger.cap_reached():
            return ("Uploads are paused for today because this demo's daily translation budget has been used. "
                    "You can still try the sample lesson, and uploads reopen tomorrow (UTC).")
        return None

    def page_context(**extra):
        ctx = {
            "languages": lang_list(),
            "public_demo": s.public_demo,
            "max_upload_mb": int(s.max_upload_mb),
            "max_words": s.max_words,
            "jobs_per_hour": s.jobs_per_hour,
            "job_ttl_hours": int(s.job_ttl_hours),
            "paused_reason": uploads_paused_reason(),
        }
        ctx.update(extra)
        return ctx

    def wants_json():
        return request.headers.get("X-Requested-With") == "fetch" or \
            request.accept_mimetypes.best == "application/json"

    def fail(message, status=400, field=None):
        if wants_json():
            return jsonify({"error": message, "field": field}), status
        return render_template("index.html", **page_context(error=message)), status

    def visitor_id():
        return request.remote_addr or "unknown"

    def make_client(is_sample):
        client = llm.LazyClient(openai_factory or llm.make_client)
        if s.public_demo:
            def before_call():
                if not limits.price_for(model):
                    raise llm.BudgetExceeded("no pricing configured for the model")
                if ledger.cap_reached():
                    raise llm.BudgetExceeded("daily spending cap reached")
            client = llm.GuardedClient(client, before_call)
        if is_sample:
            client = llm.CachingClient(client, s.sample_cache_path, seed_paths=[s.sample_cache_seed])
        return client

    # ------------------------------------------------------------ pages

    @app.route("/")
    def index():
        return render_template("index.html", **page_context())

    @app.route("/healthz")
    def healthz():
        return {"ok": True}

    @app.route("/sample.zip")
    def sample_download():
        return send_file(s.sample_zip, as_attachment=True, download_name="rosetta_sample_fractions_lesson.zip")

    @app.route("/fonts/<name>")
    def fonts(name):
        if name not in FONT_FILES:
            abort(404)
        resp = send_from_directory(ROOT / "fonts", name, max_age=7 * 24 * 3600)
        return resp

    @app.route("/upload", methods=["POST"])
    def upload():
        is_sample = request.form.get("sample") == "1"
        chosen = set(request.form.getlist("langs"))
        langs = [code for code in languages.LANGUAGES if code in chosen]
        if not langs:
            return fail("Choose at least one language to translate into.", field="langs")

        if s.public_demo:
            kind, limit = ("sample", s.samples_per_hour) if is_sample else ("upload", s.jobs_per_hour)
            ok, wait = limiter.check(visitor_id(), kind, limit)
            if not ok:
                mins = max(1, round(wait / 60))
                what = "sample runs" if is_sample else "translations"
                return fail(f"You've reached this demo's limit of {limit} {what} per hour. "
                            f"Please try again in about {mins} minute{'s' if mins != 1 else ''}.", 429)
            if store.running_count() >= s.max_concurrent_jobs:
                return fail("Rosetta is busy with other translations right now. Please try again in a minute.", 503)

        if not is_sample:
            paused = uploads_paused_reason()
            if paused:
                return fail(paused, 503)
            file = request.files.get("document")
            if not file or not file.filename:
                return fail("Choose an .idml or .zip file to upload.", field="document")

        job_id = new_job_id()
        job_dir = store.job_dir(job_id)
        job_dir.mkdir(parents=True)
        try:
            if is_sample:
                filename = "fractions_lesson.zip"
                upload_path = job_dir / "upload.zip"
                shutil.copyfile(s.sample_zip, upload_path)
            else:
                filename = Path(file.filename).name
                upload_path = job_dir / ("upload" + Path(filename).suffix.lower())
                file.save(upload_path)
            prepared = uploads.prepare_upload(upload_path, filename, job_dir)
        except uploads.UploadError as e:
            shutil.rmtree(job_dir, ignore_errors=True)
            return fail(str(e), field="document")
        except Exception:
            log.exception("Unexpected error preparing upload")
            shutil.rmtree(job_dir, ignore_errors=True)
            return fail("Something went wrong while reading that file. Please check it and try again.", 500)

        if s.max_words and prepared.word_count > s.max_words and not is_sample:
            shutil.rmtree(job_dir, ignore_errors=True)
            return fail(f"This document has about {prepared.word_count:,} words to translate. The public demo "
                        f"accepts up to {s.max_words:,} words per document. Rosetta is open source, so you can "
                        f"run it yourself for larger documents.", 413, field="document")

        notices = []
        if prepared.links_missing and not prepared.links_provided:
            n = len(prepared.links_missing)
            notices.append({"kind": "info", "text":
                            f"No Links folder was included, so the {n} linked image{'s' if n != 1 else ''} in "
                            f"this document won't be packaged with the result. The text is translated as normal. "
                            f"Put the images in a Links folder next to the translated .idml and InDesign will "
                            f"relink them."})
        elif prepared.links_missing:
            n = len(prepared.links_missing)
            shown = ", ".join(prepared.links_missing[:3]) + (" and others" if n > 3 else "")
            notices.append({"kind": "info", "text":
                            f"{n} linked file{'s were' if n != 1 else ' was'} missing from the Links folder "
                            f"({shown}). The text is translated as normal; relink those images in InDesign."})

        if s.public_demo:
            limiter.record(visitor_id(), "sample" if is_sample else "upload")

        store.create(job_id, langs=langs, source_name=prepared.idml_filename, is_sample=is_sample,
                     notices=notices, word_count=prepared.word_count)
        client = make_client(is_sample)

        def on_usage(call_model, prompt_tokens, completion_tokens):
            store.add_usage(job_id, call_model, prompt_tokens, completion_tokens)
            cost = limits.cost_usd(call_model, prompt_tokens, completion_tokens)
            if cost:
                ledger.add(cost)

        runner = JobRunner(store, job_id, job_dir=job_dir, extracted_dir=prepared.extracted_dir,
                           idml_filename=prepared.idml_filename, langs=langs, client=client, model=model,
                           on_usage=on_usage, public=s.public_demo, is_sample=is_sample)
        app.extensions["rosetta"].setdefault("runners", {})[job_id] = runner

        def run():
            try:
                runner.run()
            finally:
                app.extensions["rosetta"]["runners"].pop(job_id, None)

        threading.Thread(target=run, daemon=True, name=f"rosetta-job-{job_id}").start()
        target = url_for("job_page", job_id=job_id)
        if wants_json():
            return jsonify({"job_url": target})
        return redirect(target)

    @app.errorhandler(413)
    def too_large(_e):
        return fail(f"That file is larger than the {int(s.max_upload_mb)} MB upload limit. If your Links "
                    f"folder is large, try uploading just the .idml file.", 413, field="document")

    @app.route("/job/<job_id>")
    def job_page(job_id):
        job = store.get(job_id)
        if job is None:
            return render_template("missing.html", **page_context()), 404
        return render_template("job.html", job_id=job_id, source_name=job["source_name"],
                               langs=[languages.get(l) for l in job["langs"] if l in languages.LANGUAGES],
                               **page_context())

    # ------------------------------------------------------------ API

    def public_view(job):
        steps_done = set(job.get("steps_done") or [])
        total_weight = sum(w for _k, _l, w in STEPS)
        done_weight, steps = 0.0, []
        sp = job.get("step_progress") or {}
        for key, label, weight in STEPS:
            if key in steps_done or job["status"] == "done":
                state = "done"
                done_weight += weight
            elif key == job.get("step") and job["status"] == "running":
                state = "current"
                done_weight += weight * sp.get("fraction", 0.0)
            else:
                state = "pending"
            steps.append({"key": key, "label": label, "state": state,
                          "detail": sp.get("detail") if state == "current" else None})

        eta = None
        if job["status"] == "running" and job.get("step") == "translate" and job.get("step_started_at"):
            frac = sp.get("fraction", 0.0)
            elapsed = time.time() - job["step_started_at"]
            if frac >= 0.05 and elapsed >= 3:
                eta = int(elapsed * (1 - frac) / frac * 1.15) + 5

        results = {}
        for lang, r in (job.get("results") or {}).items():
            if "package" not in r:
                continue
            base = f"/download/{job['id']}/{lang}"
            results[lang] = {
                "summary": r.get("summary"),
                "exception_count": r.get("exception_count"),
                "downloads": {"package": f"{base}/package", "idml": f"{base}/idml",
                              "report": f"{base}/report", "report_json": f"{base}/report_json"},
                "package_name": r.get("download_package_name"),
                "idml_name": r.get("download_idml_name"),
            }

        cost = job.get("cost")
        if cost is None and job.get("usage"):
            cost = limits.compute_cost(job["usage"])
        lang_meta = {}
        for code in job["langs"]:
            lang = languages.LANGUAGES.get(code)
            lang_meta[code] = {"name": lang.name if lang else code, "native": lang.native if lang else code,
                               "rtl": bool(lang and lang.rtl), **job["lang_status"].get(code, {})}

        status = job["status"]
        return {
            "id": job["id"],
            "status": status,
            "source_name": job["source_name"],
            "is_sample": job.get("is_sample", False),
            "progress": 1.0 if status == "done" else round(done_weight / total_weight, 4),
            "eta_seconds": eta,
            "steps": steps,
            "langs": job["langs"],
            "languages": lang_meta,
            "notices": job.get("notices", []),
            "error": job.get("error"),
            "results": results,
            "usage": job.get("usage"),
            "cost": cost,
            "log": job.get("log", []),
            "created_at": job.get("created_at"),
            "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at"),
        }

    @app.route("/api/job/<job_id>")
    def api_job(job_id):
        job = store.get(job_id)
        if job is None:
            return jsonify({"error": "not_found"}), 404
        return jsonify(public_view(job))

    @app.route("/api/job/<job_id>/preview")
    def api_preview(job_id):
        job = store.get(job_id)
        path = store.job_dir(job_id) / "preview.json"
        if job is None or not path.exists():
            return jsonify({"error": "not_found"}), 404
        return Response(path.read_text(encoding="utf-8"), mimetype="application/json")

    @app.route("/download/<job_id>/<lang>/<kind>")
    def download(job_id, lang, kind):
        job = store.get(job_id)
        if job is None:
            abort(404)
        r = (job.get("results") or {}).get(lang)
        if not r:
            abort(404)
        job_dir = store.job_dir(job_id)
        spec = {
            "package": (r.get("package"), r.get("download_package_name"), True),
            "idml": (r.get("idml"), r.get("download_idml_name"), True),
            "report": (r.get("report_html"), f"QA_report_{lang}.html", False),
            "report_json": (r.get("report_json"), f"QA_report_{lang}.json", True),
        }.get(kind)
        if not spec or not spec[0]:
            abort(404)
        path = (job_dir / spec[0]).resolve()
        if job_dir.resolve() not in path.parents or not path.exists():
            abort(404)
        return send_file(path, as_attachment=spec[2], download_name=spec[1])

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    print(f"Rosetta is running: open http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
