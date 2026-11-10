"""Web app routes, job lifecycle, access modes and public-demo limits."""

import io
import json
import time

import pytest

from conftest import SAMPLE_IDML, SAMPLE_ZIP, wait_for_job
from fake_openai import FakeOpenAI

AJAX = {"X-Requested-With": "fetch"}


def start(client, **form):
    data = {"langs": form.pop("langs", ["es"])}
    if form.pop("sample", False):
        data["sample"] = "1"
    if "file" in form:
        path, name = form.pop("file")
        data["document"] = (io.BytesIO(path.read_bytes()), name)
    resp = client.post("/upload", data=data, content_type="multipart/form-data", headers=AJAX)
    return resp


def job_id(resp):
    return resp.get_json()["job_url"].rsplit("/", 1)[-1]


def test_home_page(make_app):
    _app, client, _ = make_app()
    html = client.get("/").get_data(as_text=True)
    assert "Translate InDesign documents into other languages" in html
    assert "Try it with a sample lesson" in html
    assert "Runs locally only" not in html
    for lang in ("Spanish", "French", "German", "Portuguese", "Arabic"):
        assert lang in html
    assert client.get("/sample.zip").data == SAMPLE_ZIP.read_bytes()
    assert client.get("/static/favicon.svg").status_code == 200
    assert client.get("/fonts/NotoSansArabic-Regular.ttf").status_code == 200
    assert client.get("/fonts/../app.py").status_code == 404


def test_sample_end_to_end_and_downloads(make_app):
    app, client, fakes = make_app()
    resp = start(client, sample=True, langs=["es", "ar"])
    assert resp.status_code == 200
    jid = job_id(resp)
    assert client.get(f"/job/{jid}").status_code == 200
    job = wait_for_job(app, jid)
    assert job["status"] == "done"

    view = client.get(f"/api/job/{jid}").get_json()
    assert view["progress"] == 1.0 and all(s["state"] == "done" for s in view["steps"])
    assert "rosetta.db" not in json.dumps(view)  # no server paths leak
    for lang in ("es", "ar"):
        dl = view["results"][lang]["downloads"]
        pkg = client.get(dl["package"])
        assert pkg.status_code == 200 and pkg.headers["Content-Disposition"].startswith("attachment")
        assert client.get(dl["idml"]).data[:2] == b"PK"
        assert "QA report" in client.get(dl["report"]).get_data(as_text=True)
        assert client.get(dl["report_json"]).get_json()["target_language"] == lang
    prev = client.get(f"/api/job/{jid}/preview").get_json()
    assert set(prev["langs"]) == {"es", "ar"}
    assert client.get(f"/download/{jid}/es/../../state.db").status_code == 404

    # Second sample run is answered from the cache: no new API calls, no cost.
    calls_before = sum(len(f.calls) for f in fakes)
    job2 = wait_for_job(app, job_id(start(client, sample=True, langs=["es", "ar"])))
    assert job2["status"] == "done"
    assert sum(len(f.calls) for f in fakes) == calls_before
    assert job2["usage"]["calls"] == 0 and job2["usage"]["cached_calls"] > 0
    assert job2["cost"]["usd"] == 0


def test_plain_idml_upload_gets_links_notice(make_app):
    app, client, _ = make_app()
    jid = job_id(start(client, file=(SAMPLE_IDML, "lesson.idml")))
    job = wait_for_job(app, jid)
    assert job["status"] == "done"
    assert "No Links folder was included" in job["notices"][0]["text"]


def test_validation_messages(make_app):
    _app, client, _ = make_app()
    r = start(client, langs=[], sample=True)
    assert r.status_code == 400 and r.get_json()["field"] == "langs"
    r = client.post("/upload", data={"langs": "es"}, headers=AJAX)
    assert "Choose an .idml or .zip" in r.get_json()["error"]
    r = client.post("/upload", data={"langs": "es", "document": (io.BytesIO(b"x"), "a.indd")},
                    content_type="multipart/form-data")
    assert r.status_code == 400 and "not an .indd" in r.get_data(as_text=True)  # no-JS form gets the page back


def test_unknown_and_expired_jobs(make_app):
    _app, client, _ = make_app()
    page = client.get("/job/doesnotexist")
    assert page.status_code == 404 and "couldn't find" in page.get_data(as_text=True)
    assert client.get("/api/job/doesnotexist").status_code == 404


def test_restart_marks_running_jobs_interrupted(make_app, make_settings):
    import app as appmod
    app, client, _ = make_app()
    store = app.extensions["rosetta"]["store"]
    store.create("stuck", langs=["es"], source_name="x.idml")
    store.update("stuck", status="running", force=True)
    # A new process starting against the same data directory:
    s = app.config["SETTINGS"]
    app2 = appmod.create_app(s, openai_factory=FakeOpenAI, start_cleanup_thread=False)
    view = app2.test_client().get("/api/job/stuck").get_json()
    assert view["status"] == "interrupted"


def test_cleanup_removes_old_jobs(make_app):
    app, client, _ = make_app()
    jid = job_id(start(client, sample=True))
    wait_for_job(app, jid)
    store = app.extensions["rosetta"]["store"]
    store.db.execute("UPDATE jobs SET created_at = ? WHERE id = ?", (time.time() - 48 * 3600, jid))
    assert store.cleanup(24) == 1
    assert store.get(jid) is None and not store.job_dir(jid).exists()


def test_password_gate_in_private_mode(make_app):
    _app, client, _ = make_app(SITE_PASSWORD="letmein")
    assert client.get("/").status_code == 401
    import base64
    ok = {"Authorization": "Basic " + base64.b64encode(b"anyone:letmein").decode()}
    assert client.get("/", headers=ok).status_code == 200
    assert client.get("/healthz").status_code == 200


def test_public_mode_ignores_password_and_rate_limits(make_app):
    app, client, _ = make_app(PUBLIC_DEMO="true", SITE_PASSWORD="letmein", RATE_LIMIT_JOBS_PER_HOUR="2",
                              DAILY_SPEND_CAP_USD="100")
    assert client.get("/").status_code == 200
    for _ in range(2):
        r = start(client, file=(SAMPLE_IDML, "a.idml"))
        assert r.status_code == 200
        wait_for_job(app, job_id(r))
    r = start(client, file=(SAMPLE_IDML, "a.idml"))
    assert r.status_code == 429 and "limit of 2 translations per hour" in r.get_json()["error"]
    # A different visitor is unaffected.
    r = client.post("/upload", data={"langs": "es", "document": (io.BytesIO(SAMPLE_IDML.read_bytes()), "a.idml")},
                    content_type="multipart/form-data", headers={**AJAX, "X-Forwarded-For": "203.0.113.9"})
    assert r.status_code == 200
    wait_for_job(app, job_id(r))


def test_public_mode_word_limit(make_app):
    _app, client, _ = make_app(PUBLIC_DEMO="true", MAX_WORDS_PER_JOB="50")
    r = start(client, file=(SAMPLE_IDML, "a.idml"))
    assert r.status_code == 413 and "up to 50 words" in r.get_json()["error"]


def test_spending_cap_pauses_uploads_but_sample_still_works(make_app):
    app, client, fakes = make_app(PUBLIC_DEMO="true", DAILY_SPEND_CAP_USD="1")
    # Warm the sample cache while there's budget left; real spend is recorded.
    first = wait_for_job(app, job_id(start(client, sample=True)))
    assert first["status"] == "done"
    ledger = app.extensions["rosetta"]["ledger"]
    assert 0 < ledger.spent() < 1 and not ledger.cap_reached()
    ledger.add(1.0)  # the rest of today's budget gets used by other visitors
    assert ledger.cap_reached()

    r = start(client, file=(SAMPLE_IDML, "a.idml"))
    assert r.status_code == 503 and "budget" in r.get_json()["error"]
    assert "Uploads are paused" in client.get("/").get_data(as_text=True)

    again = wait_for_job(app, job_id(start(client, sample=True)))
    assert again["status"] == "done" and again["usage"]["calls"] == 0

    # A sample language that isn't cached yet can't spend past the cap.
    blocked = wait_for_job(app, job_id(start(client, sample=True, langs=["de"])))
    assert blocked["status"] == "error" and blocked["error"]["code"] == "budget"


def test_missing_api_key_is_explained(make_settings):
    import app as appmod
    application = appmod.create_app(make_settings(), start_cleanup_thread=False)  # real factory, no key
    client = application.test_client()
    assert "no OpenAI API key" in client.get("/").get_data(as_text=True)
    r = start(client, file=(SAMPLE_IDML, "a.idml"))
    assert r.status_code == 503
    job = wait_for_job(application, job_id(start(client, sample=True)))
    assert job["status"] == "error" and job["error"]["code"] == "missing_key"
    assert "OPENAI_API_KEY" in job["error"]["message"]
