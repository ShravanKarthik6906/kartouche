"""The UI hooks documented in the README ("Customising the UI") stay present,
so a restyle can't silently break upload.js or job.js."""

import re
from pathlib import Path

from conftest import ROOT, wait_for_job

HOME_IDS = ["upload-form", "document-input", "dropzone", "dz-file", "document-error", "lang-chips",
            "langs-error", "submit-button", "sample-button", "upload-progress", "upload-bar", "upload-status"]
JOB_IDS = ["job", "job-sub", "notices", "status-sheet", "progress-card", "progress-title", "progress-pct",
           "progress-bar", "progress-fill", "eta", "checklist", "wake-note", "error-card", "error-title",
           "error-message", "ticket-started", "results", "lang-tabs", "lang-panels", "tech", "tech-meta", "log"]


def ids_in(html):
    return set(re.findall(r'\bid="([^"]+)"', html))


def test_home_hooks(make_app):
    _app, client, _ = make_app()
    html = client.get("/").get_data(as_text=True)
    assert set(HOME_IDS) <= ids_in(html)
    assert 'name="document"' in html and 'name="langs"' in html
    assert re.search(r'id="sample-button"[^>]*|name="sample" value="1"[^>]*form="upload-form"', html)
    assert 'name="sample" value="1"' in html and 'form="upload-form"' in html
    assert 'data-max-bytes="' in html
    assert re.search(r'<form[^>]+id="upload-form"[^>]+action="/upload', html)


def test_job_hooks_and_scripts_agree(make_app):
    app, client, _ = make_app()
    resp = client.post("/upload", data={"sample": "1", "langs": "es"}, headers={"X-Requested-With": "fetch"})
    job_id = resp.get_json()["job_url"].rsplit("/", 1)[-1]
    html = client.get(f"/job/{job_id}").get_data(as_text=True)
    assert set(JOB_IDS) <= ids_in(html)
    assert f'data-job-id="{job_id}"' in html
    wait_for_job(app, job_id)

    # Every id the scripts look up exists in the template they run on.
    upload_js = (ROOT / "static" / "upload.js").read_text()
    job_js = (ROOT / "static" / "job.js").read_text()
    home_html = client.get("/").get_data(as_text=True)
    for js, page in ((upload_js, home_html), (job_js, html)):
        used = set(re.findall(r'getElementById\("([^"]+)"\)', js)) | set(re.findall(r'\$\("([^"]+)"\)', js))
        assert used <= ids_in(page), f"missing ids: {used - ids_in(page)}"


def test_no_inline_styles_and_one_stylesheet():
    for tpl in (ROOT / "templates").glob("*.html"):
        text = tpl.read_text()
        assert "style=" not in text, f"inline style in {tpl.name}"
        assert "<script>" not in text, f"inline script in {tpl.name}"
        if tpl.name != "base.html":
            assert text.lstrip().startswith('{% extends "base.html" %}'), tpl.name
    assert (ROOT / "static" / "styles.css").exists()
    css = (ROOT / "static" / "styles.css").read_text()
    assert "prefers-color-scheme: dark" in css and "prefers-reduced-motion" in css
