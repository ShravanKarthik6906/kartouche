"""
QA report per language: a self-contained HTML page for people, and a JSON
file with the same data for tools. Built from the exceptions recorded by
overflow_resolve.py and exception_checks.py.
"""

import json
import sqlite3
from datetime import datetime, timezone
from html import escape
from pathlib import Path

import languages

CATEGORY_LABELS = {
    "unresolved_overflow": "Doesn't fit its frame",
    "overflow_retranslation_review": "Shortened to fit - check the wording",
    "missing_translation": "Not translated",
    "translation_error": "Translated inconsistently",
    "layout_risk_heuristic": "Much longer or shorter than the original",
}
CATEGORY_ADVICE = {
    "unresolved_overflow": "Enlarge the frame or edit the text in InDesign.",
    "overflow_retranslation_review": "A shorter wording was used so the text fits. Confirm it still says the "
                                     "same thing.",
    "missing_translation": "The original English was kept. Translate this text by hand or run the job again.",
    "translation_error": "Pick one wording and use it everywhere.",
    "layout_risk_heuristic": "Check the layout around this text in InDesign.",
}
SEVERITY_LABELS = {"HIGH": "Needs attention", "MED": "Please review", "LOW": "For information"}


def fetch_exceptions(db_path, document_id, lang):
    """All exceptions for one language, with the text and page each one concerns."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT id, category, severity, description, status, created_at
        FROM exceptions WHERE document_id = ? AND target_language = ?
        ORDER BY CASE severity WHEN 'HIGH' THEN 0 WHEN 'MED' THEN 1 ELSE 2 END, category, id
    """, (document_id, lang)).fetchall()
    out = []
    for exc in rows:
        frags = conn.execute("""
            SELECT t.id, t.raw_text, tr.translated_text, o.retranslated_text,
                   (SELECT GROUP_CONCAT(DISTINCT sp.page_name) FROM story_placements sp
                    WHERE sp.story_id = t.story_id) AS pages
            FROM exception_fragments ef
            JOIN text_runs t ON t.id = ef.text_run_id
            LEFT JOIN translations tr ON tr.text_run_id = t.id AND tr.target_language = ?
            LEFT JOIN overflow_resolutions o ON o.text_run_id = t.id AND o.target_language = ?
            WHERE ef.exception_id = ?
        """, (lang, lang, exc["id"])).fetchall()
        item = dict(exc)
        item["text_run_ids"] = [f["id"] for f in frags]
        item["fragments"] = [{
            "text_run_id": f["id"],
            "original": f["raw_text"],
            "translation": f["translated_text"],
            "shortened": f["retranslated_text"],
            "pages": sorted(set((f["pages"] or "").split(",")) - {""}, key=lambda n: (len(n), n)),
        } for f in frags]
        out.append(item)
    conn.close()
    return out


def write_json(exceptions, document_id, lang, out_path: Path, source_name=None):
    out_path.write_text(json.dumps({
        "document_id": document_id,
        "source_file": source_name,
        "target_language": lang,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_exceptions": len(exceptions),
        "exceptions": exceptions,
    }, indent=2, ensure_ascii=False), encoding="utf-8")


def write_html(exceptions, lang, out_path: Path, source_name="document"):
    lang_cfg = languages.LANGUAGES.get(lang)
    lang_name = lang_cfg.name if lang_cfg else lang
    dir_attr = ' dir="rtl"' if lang_cfg and lang_cfg.rtl else ""

    counts = {}
    for e in exceptions:
        counts[e["severity"]] = counts.get(e["severity"], 0) + 1

    cards = []
    for e in exceptions:
        frag_html = []
        for f in e["fragments"][:6]:
            where = ("Page " + ", ".join(f["pages"])) if f["pages"] else "Master page / unplaced text"
            translated = f["shortened"] or f["translation"]
            frag_html.append(
                f'<div class="frag"><div class="where">{escape(where)}</div>'
                f'<div class="pair"><div><span class="lbl">English</span><p>{escape(f["original"])}</p></div>'
                f'<div><span class="lbl">{escape(lang_name)}</span>'
                f'<p{dir_attr}>{escape(translated) if translated else "<em>not translated</em>"}</p>'
                + (f'<p class="was"{dir_attr}>Before shortening: {escape(f["translation"])}</p>'
                   if f["shortened"] and f["translation"] else "")
                + '</div></div></div>')
        if len(e["fragments"]) > 6:
            frag_html.append(f'<p class="more">+ {len(e["fragments"]) - 6} more occurrence(s)</p>')
        sev = e["severity"]
        cards.append(
            f'<article class="card sev-{escape(sev.lower())}">'
            f'<header><span class="badge">{escape(SEVERITY_LABELS.get(sev, sev))}</span>'
            f'<h3>{escape(CATEGORY_LABELS.get(e["category"], e["category"]))}</h3></header>'
            f'<p class="advice">{escape(CATEGORY_ADVICE.get(e["category"], ""))}</p>'
            + "".join(frag_html) +
            f'<details><summary>Technical detail</summary><p>{escape(e["description"])}</p></details>'
            '</article>')

    if exceptions:
        summary = (f'{len(exceptions)} item(s) to look at: '
                   + ", ".join(f'{n} {SEVERITY_LABELS.get(s, s).lower()}' for s, n in counts.items()) + ".")
    else:
        summary = "Nothing was flagged. Every piece of text was translated, fits its frame and is consistent."

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>QA report - {escape(lang_name)} - {escape(source_name)}</title>
<style>
  :root {{ --ink:#1c2430; --muted:#5b6675; --line:#e2e6ec; --bg:#f7f8fa; --accent:#1f61a8;
          --high:#b42318; --high-bg:#fef3f2; --med:#93370d; --med-bg:#fffaeb; }}
  * {{ box-sizing: border-box; }}
  body {{ font: 15px/1.55 -apple-system, "Segoe UI", Inter, Roboto, sans-serif; color: var(--ink);
         background: var(--bg); margin: 0; padding: 32px 16px; }}
  main {{ max-width: 860px; margin: 0 auto; }}
  h1 {{ font-size: 24px; margin: 0 0 4px; }} .sub {{ color: var(--muted); margin: 0 0 24px; }}
  .summary {{ background: #fff; border: 1px solid var(--line); border-radius: 10px; padding: 14px 18px; margin-bottom: 20px; }}
  .card {{ background: #fff; border: 1px solid var(--line); border-left: 4px solid var(--line); border-radius: 10px;
          padding: 16px 18px; margin-bottom: 14px; }}
  .card.sev-high {{ border-left-color: var(--high); }} .card.sev-med {{ border-left-color: #dc6803; }}
  header {{ display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}
  h3 {{ font-size: 16px; margin: 0; }}
  .badge {{ font-size: 12px; font-weight: 600; padding: 2px 9px; border-radius: 99px; background: #eef1f5; color: var(--muted); }}
  .sev-high .badge {{ background: var(--high-bg); color: var(--high); }} .sev-med .badge {{ background: var(--med-bg); color: var(--med); }}
  .advice {{ color: var(--muted); margin: 6px 0 10px; }}
  .frag {{ border-top: 1px solid var(--line); padding-top: 10px; margin-top: 10px; }}
  .where {{ font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }}
  .pair {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  .pair p {{ margin: 2px 0; }} .lbl {{ font-size: 12px; color: var(--muted); }}
  .was {{ color: var(--muted); font-size: 13px; }}
  [dir=rtl] {{ font-family: "Noto Sans Arabic", "Geeza Pro", Tahoma, sans-serif; text-align: right; }}
  details {{ margin-top: 10px; color: var(--muted); font-size: 13px; }}
  .foot {{ color: var(--muted); font-size: 12px; margin-top: 28px; }}
  @media (max-width: 600px) {{ .pair {{ grid-template-columns: 1fr; gap: 6px; }} }}
</style></head>
<body><main>
  <h1>QA report: {escape(lang_name)}</h1>
  <p class="sub">{escape(source_name)}</p>
  <div class="summary">{escape(summary)}</div>
  {''.join(cards)}
  <p class="foot">Generated by Kartouche on {datetime.now(timezone.utc).strftime('%d %b %Y, %H:%M UTC')}.
  These checks cover completeness, consistency and fit. They don't check that the translation is linguistically
  correct, so have a fluent speaker review it before publishing.</p>
</main></body></html>"""
    out_path.write_text(html, encoding="utf-8")
