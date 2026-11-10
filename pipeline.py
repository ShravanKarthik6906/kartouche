"""
Runs the Rosetta pipeline for one web job, in a background thread, and
reports progress into the job store. Calls the same stage functions as the
command-line workflow; no translation or layout logic lives here.

Steps (as the visitor sees them):
  read      deconstruct.py         - unpack the text into rosetta.db
  find      story_placements.py    - which page/frame each story is on
  translate translate.py           - one language at a time
  fit       overflow_resolve.py    - measure fit, wrap/shrink/shorten
  qa        exception_checks.py    - consistency / completeness checks + reports
  build     reconstruct.py         - write each translated .idml + package
            preview.py             - side-by-side preview data

Each language is handled independently: if one fails, the others still
finish and are shown. An error that would affect every remaining call
(e.g. no API credit, spending cap reached) stops translation for the
languages not yet started, with a plain-language explanation.
"""

import json
import logging
import time
import traceback
from pathlib import Path

import deconstruct
import exception_checks
import languages
import limits
import llm
import overflow_resolve
import preview
import reconstruct
import reports
import story_placements
import translate
from jobs import STEPS

log = logging.getLogger("rosetta.pipeline")

STEP_LABELS = {k: label for k, label, _w in STEPS}


def friendly_error(exc, public=False):
    """(code, title, message, detail) for any exception raised by a stage."""
    if isinstance(exc, llm.FatalAPIError):
        code = exc.code
        exc_for_detail = exc.original
    else:
        code = llm.classify_error(exc)
        exc_for_detail = exc
    if code == "unknown":
        text = str(exc)
        if "No Stories/ folder" in text or isinstance(exc, (FileNotFoundError,)):
            title, message = ("Part of this document couldn't be read",
                              "The file seems to be incomplete. Try exporting the .idml from InDesign again.")
        elif exc.__class__.__name__ == "XMLSyntaxError":
            title, message = ("Part of this document couldn't be read",
                              "Some of the document's XML is damaged. Try exporting the .idml from InDesign again.")
        else:
            title, message = llm.ERROR_MESSAGES["unknown"]
    else:
        title, message = llm.ERROR_MESSAGES[code]
    if public:
        detail = f"{type(exc_for_detail).__name__}: {exc_for_detail}"
    else:
        detail = "".join(traceback.format_exception(type(exc_for_detail), exc_for_detail,
                                                    exc_for_detail.__traceback__)).strip()
    # Never echo anything that looks like a key back to the browser.
    detail = _redact(detail)
    return {"code": code, "title": title, "message": message, "detail": detail}


def _redact(text):
    import re
    return re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "sk-***", text)


class JobRunner:
    def __init__(self, store, job_id, *, job_dir, extracted_dir, idml_filename, langs, client, model,
                 on_usage, public=False, is_sample=False):
        self.store = store
        self.job_id = job_id
        self.job_dir = Path(job_dir)
        self.extracted_dir = Path(extracted_dir)
        self.idml_filename = idml_filename
        self.langs = list(langs)
        self.client = client
        self.model = model
        self.on_usage = on_usage
        self.public = public
        self.is_sample = is_sample
        self.db_path = str(self.job_dir / "rosetta.db")
        self.failed = {}          # lang -> error dict
        self.notices = []

    # ------------------------------------------------------------ helpers

    def log(self, msg):
        self.store.log(self.job_id, msg)

    def step(self, key):
        def go(job):
            if job["step"] and job["step"] not in job["steps_done"]:
                job["steps_done"].append(job["step"])
            job["step"] = key
            job["step_progress"] = None
            job["step_started_at"] = time.time()
        self.store.mutate(self.job_id, go, force=True)
        self.log(f"{STEP_LABELS[key]}…")

    def progress(self, fraction, detail=None):
        self.store.update(self.job_id, step_progress={"fraction": max(0.0, min(1.0, fraction)), "detail": detail})

    def counter(self, label=None, offset=0.0, scale=1.0):
        def cb(done, total):
            frac = offset + scale * (done / total if total else 1.0)
            self.progress(frac, f"{label} · {done} of {total}" if label else None)
        return cb

    def set_lang(self, lang, state, error=None):
        def go(job):
            job["lang_status"][lang] = {"state": state, "error": error}
        self.store.mutate(self.job_id, go, force=True)

    def fail_lang(self, lang, exc, stage):
        err = friendly_error(exc, self.public)
        if self.is_sample and err["code"] == "budget":
            err["message"] = ("The sample hasn't been prepared in this language yet, and this demo's daily "
                              "translation budget has been used. Please try again tomorrow, or pick a language "
                              "that has already been run.")
        self.failed[lang] = err
        self.set_lang(lang, "failed", err)
        self.log(f"{languages.name(lang)} failed during {stage}: {err['detail'].splitlines()[-1] if err['detail'] else ''}")
        if not self.public:
            log.exception("Job %s: %s failed during %s", self.job_id, lang, stage, exc_info=exc)
        else:
            log.warning("Job %s: %s failed during %s: %s", self.job_id, lang, stage, err["detail"])

    def active(self):
        return [l for l in self.langs if l not in self.failed]

    def notice(self, text):
        self.notices.append(text)
        self.store.mutate(self.job_id, lambda job: job["notices"].append({"kind": "warning", "text": text}))

    # ------------------------------------------------------------ run

    def run(self):
        self.store.update(self.job_id, status="running", started_at=time.time(), force=True)
        try:
            self._run()
        except Exception as exc:  # anything that escaped a stage = whole-job failure
            err = friendly_error(exc, self.public)
            log.exception("Job %s failed", self.job_id)
            self.log(f"Stopped: {err['detail'].splitlines()[-1] if err['detail'] else err['title']}")
            self.store.update(self.job_id, status="error", error=err, finished_at=time.time(), force=True)
        finally:
            def account(job):
                job["usage"]["cached_calls"] = getattr(self.client, "hits", 0)
                job["cost"] = limits.compute_cost(job["usage"])
            self.store.mutate(self.job_id, account)
            self.store.finish(self.job_id)

    def _run(self):
        # 1. Read
        self.step("read")
        doc = deconstruct.deconstruct(str(self.extracted_dir), self.idml_filename, self.db_path,
                                      progress_callback=self.counter())
        self.document_id = doc

        # 2. Find
        self.step("find")
        story_placements.populate_story_placements(self.db_path, doc, str(self.extracted_dir),
                                                   progress_callback=self.counter())

        # 3. Translate, one language at a time
        self.step("translate")
        n = len(self.langs)
        for i, lang in enumerate(self.langs):
            if lang in self.failed:
                continue
            self.set_lang(lang, "translating")
            name = languages.name(lang)
            try:
                stats = translate.translate_document(
                    self.db_path, doc, target_langs=[lang], client=self.client, model=self.model,
                    progress_callback=self.counter(name, offset=i / n, scale=1 / n),
                    usage_callback=self.on_usage,
                )
                s = stats[lang]
                self.log(f"{name}: {s['translated']} pieces of text translated, {s['errors']} failed.")
                if s["translated"] == 0 and s["errors"] > 0:
                    raise RuntimeError(f"Every {name} translation request failed")
                if s["errors"]:
                    self.notice(f"{s['errors']} piece(s) of {name} text couldn't be translated and kept their "
                                f"original wording. They're listed in the QA report.")
                self.set_lang(lang, "translated")
            except llm.FatalAPIError as exc:
                if exc.code not in llm.FATAL_CODES:
                    # Repeated failures specific to this language: give up on it, try the next.
                    self.fail_lang(lang, exc, "translation")
                    continue
                # Account-wide (bad key, no credit, budget...): every remaining language would fail too.
                for later in self.langs[i:]:
                    if later not in self.failed:
                        self.fail_lang(later, exc, "translation")
                break
            except Exception as exc:
                self.fail_lang(lang, exc, "translation")

        if not self.active():
            return self._finish()

        # 4. Fit to layout. A failure here doesn't lose the translation: the
        # file is still built, without the automatic layout fixes.
        self.step("fit")
        act = self.active()
        for i, lang in enumerate(act):
            try:
                stats = overflow_resolve.run_overflow_checks(
                    self.db_path, doc, str(self.extracted_dir), [lang], client=self.client, model=self.model,
                    progress_callback=self.counter(languages.name(lang), offset=i / len(act), scale=1 / len(act)),
                    usage_callback=self.on_usage,
                )
                self.log(f"{languages.name(lang)} layout: {stats}")
            except Exception as exc:
                err = friendly_error(exc, self.public)
                self.log(f"{languages.name(lang)} layout fitting stopped early: {err['detail'].splitlines()[-1]}")
                self.notice(f"Layout fitting for {languages.name(lang)} couldn't finish ({err['title'].lower()}). "
                            f"The file was still built, but check it for text that overflows its frame.")

        # 5. Quality checks + reports
        self.step("qa")
        results = {}
        for lang in self.active():
            try:
                exception_checks.run_all_checks(self.db_path, doc, [lang])
                exc_rows = reports.fetch_exceptions(self.db_path, doc, lang)
                html_path = self.job_dir / f"qa_report_{lang}.html"
                json_path = self.job_dir / f"qa_report_{lang}.json"
                reports.write_html(exc_rows, lang, html_path, source_name=self.idml_filename)
                reports.write_json(exc_rows, doc, lang, json_path, source_name=self.idml_filename)
                results[lang] = {"report_html": html_path.name, "report_json": json_path.name,
                                 "exception_count": len(exc_rows)}
            except Exception as exc:
                self.fail_lang(lang, exc, "quality checks")

        # 6. Build files
        self.step("build")
        act = self.active()
        stem = Path(self.idml_filename).stem
        for i, lang in enumerate(act):
            try:
                rec = reconstruct.reconstruct(
                    self.db_path, doc, lang, str(self.extracted_dir), str(self.job_dir / f"work_{lang}"),
                    idml_filename=self.idml_filename,
                    progress_callback=self.counter(languages.name(lang), offset=i / len(act), scale=1 / len(act)),
                )
                # Friendlier download names than the internal work-folder layout.
                idml_out = Path(rec["idml_path"])
                pkg_out = Path(rec["bundle_path"])
                results[lang].update({
                    "idml": idml_out.relative_to(self.job_dir).as_posix(),
                    "package": pkg_out.relative_to(self.job_dir).as_posix(),
                    "download_idml_name": f"{stem}_{lang}.idml",
                    "download_package_name": f"{stem}_{lang}_InDesign_package.zip",
                    "replaced": rec["replaced"], "missing": rec["missing"], "rtl_flips": rec["rtl_flips"],
                    "shrunk": rec["shrunk"], "retranslated": rec["retranslated"],
                })
                shutil_rmtree(self.job_dir / f"work_{lang}")  # the unzipped copy is no longer needed
                self.set_lang(lang, "done")
            except Exception as exc:
                self.fail_lang(lang, exc, "building the file")
                results.pop(lang, None)

        # Preview data for the browser
        done = [l for l in self.active() if l in results]
        if done:
            try:
                data = preview.build_preview(self.db_path, doc, str(self.extracted_dir), done)
                (self.job_dir / "preview.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                for lang in done:
                    results[lang]["summary"] = data["langs"][lang]["summary"]
            except Exception as exc:
                log.exception("Job %s: preview failed", self.job_id)
                self.notice("The side-by-side preview couldn't be built, but your files are ready to download.")
                self.log(f"Preview failed: {exc}")

        self.store.update(self.job_id, results=results)
        return self._finish()

    def _finish(self):
        job = self.store.get(self.job_id)
        done_langs = [l for l in self.langs if job["lang_status"][l]["state"] == "done"]
        if job["steps_done"] is not None and job["step"]:
            self.store.mutate(self.job_id, lambda j: j["steps_done"].append(j["step"]) if j["step"] not in j["steps_done"] else None)
        if done_langs:
            self.log("All done." if not self.failed else
                     f"Finished: {len(done_langs)} of {len(self.langs)} language(s) succeeded.")
            self.store.update(self.job_id, status="done", step="done", finished_at=time.time(), force=True)
        else:
            first = next(iter(self.failed.values()), None) or {
                "code": "unknown", "title": llm.ERROR_MESSAGES["unknown"][0],
                "message": llm.ERROR_MESSAGES["unknown"][1], "detail": ""}
            self.store.update(self.job_id, status="error", error=first, finished_at=time.time(), force=True)


def shutil_rmtree(path):
    import shutil
    shutil.rmtree(path, ignore_errors=True)
