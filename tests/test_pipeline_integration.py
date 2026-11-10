"""Full pipeline on the sample with a mocked OpenAI client - no network, no key."""

import json
import zipfile

import pytest

import idml_check
import languages
import uploads
from conftest import SAMPLE_ZIP
from fake_openai import FakeOpenAI, pseudo_translate
from jobs import JobStore
from pipeline import JobRunner
from state import StateDB

ALL = list(languages.LANGUAGES)


def run_sample(tmp_path, langs, client):
    store = JobStore(StateDB(tmp_path / "state.db"), tmp_path / "jobs")
    job_dir = tmp_path / "jobs" / "j1"
    job_dir.mkdir(parents=True)
    up = job_dir / "upload.zip"
    up.write_bytes(SAMPLE_ZIP.read_bytes())
    prep = uploads.prepare_upload(up, "fractions_lesson.zip", job_dir)
    store.create("j1", langs=langs, source_name=prep.idml_filename)
    usage = []
    JobRunner(store, "j1", job_dir=job_dir, extracted_dir=prep.extracted_dir, idml_filename=prep.idml_filename,
              langs=langs, client=client, model="gpt-5-mini",
              on_usage=lambda *a: (usage.append(a), store.add_usage("j1", *a))).run()
    return store.get("j1"), job_dir, usage


@pytest.fixture(scope="module")
def all_languages(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("full")
    fake = FakeOpenAI()
    job, job_dir, usage = run_sample(tmp, ALL, fake)
    return job, job_dir, usage, fake


def stories(idml_path):
    with zipfile.ZipFile(idml_path) as zf:
        return {n: zf.read(n).decode() for n in zf.namelist() if n.startswith("Stories/")}


def test_every_language_succeeds(all_languages):
    job, _dir, usage, fake = all_languages
    assert job["status"] == "done", job["error"]
    assert all(job["lang_status"][l]["state"] == "done" for l in ALL)
    assert set(job["steps_done"]) == {"read", "find", "translate", "fit", "qa", "build"}
    assert len(usage) == len(fake.calls) > 0
    assert job["cost"]["available"] and job["cost"]["usd"] > 0


@pytest.mark.parametrize("lang", ALL)
def test_output_idml_is_valid_and_translated(all_languages, lang):
    job, job_dir, _u, _f = all_languages
    res = job["results"][lang]
    idml = job_dir / res["idml"]
    with zipfile.ZipFile(idml) as zf:
        first = zf.infolist()[0]
        assert first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED
    assert idml_check.check_idml(idml) == []
    text = "".join(stories(idml).values())
    expected = pseudo_translate("Practice", languages.get(lang).prompt_name)
    assert f"<Content>{expected}</Content>" in text
    assert "<Content>Practice</Content>" not in text
    assert "<Content>2/3</Content>" in text  # numbers are kept exactly
    rtl = 'StoryDirection="RightToLeftDirection"' in text
    assert rtl == (lang == "ar")
    assert res["summary"]["paragraphs_translated"] == res["summary"]["paragraphs_total"] > 30


def test_arabic_stories_are_all_rtl(all_languages):
    job, job_dir, _u, _f = all_languages
    for xml in stories(job_dir / job["results"]["ar"]["idml"]).values():
        assert "LeftToRightDirection" not in xml.split("<ParagraphStyleRange")[0]


def test_reports_and_preview(all_languages):
    job, job_dir, _u, _f = all_languages
    preview = json.loads((job_dir / "preview.json").read_text())
    assert [p["name"] for p in preview["pages"]] == ["1", "2", "3", "Other text"]
    first_page = [s["id"] for s in preview["pages"][0]["stories"]]
    assert len(first_page) == 5
    body = next(s for s in preview["pages"][0]["stories"] if s["pages"] == ["1", "2"])
    assert any(b["type"] == "table" for b in body["blocks"])
    for lang in ALL:
        rep = json.loads((job_dir / job["results"][lang]["report_json"]).read_text())
        assert rep["target_language"] == lang
        html = (job_dir / job["results"][lang]["report_html"]).read_text()
        assert "QA report" in html


def test_overflow_fixes_are_applied(all_languages):
    """The fake makes Latin text 25-35% longer, so the 300pt title must be fixed to fit."""
    job, job_dir, _u, _f = all_languages
    es = job["results"]["es"]
    assert es["summary"]["auto_fixed"] >= 1
    assert es["shrunk"] + es["retranslated"] >= 1


class FailsForArabic(FakeOpenAI):
    def __init__(self):
        super().__init__()
        inner = self.chat.completions.create

        def create(model, messages, **kw):
            if "into Arabic" in messages[0]["content"]:
                raise RuntimeError("simulated Arabic-only failure")
            return inner(model=model, messages=messages, **kw)
        self.chat.completions.create = create


def test_one_failed_language_does_not_hide_the_other(tmp_path):
    job, _dir, _u = run_sample(tmp_path, ["ar", "es"], FailsForArabic())
    assert job["status"] == "done"
    assert job["lang_status"]["ar"]["state"] == "failed"
    assert job["lang_status"]["es"]["state"] == "done"
    assert "es" in job["results"] and "ar" not in job["results"]


def test_account_wide_errors_stop_the_run_with_a_plain_message(tmp_path):
    import llm
    job, _dir, _u = run_sample(tmp_path, ["es", "fr"], FakeOpenAI(fail_with=llm.BudgetExceeded("cap")))
    assert job["status"] == "error"
    assert job["error"]["code"] == "budget"
    assert "budget" in job["error"]["title"].lower()
    assert all(job["lang_status"][l]["state"] == "failed" for l in ("es", "fr"))
