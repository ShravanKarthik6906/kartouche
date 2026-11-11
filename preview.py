"""
Builds the in-browser preview of a finished job from its kartouche.db: the
original and translated text side by side, grouped by page and story in
reading order, with bold/italic runs, tables, and every fix or flag the
pipeline recorded. Also produces the per-language summary numbers.

The translated text shown is exactly what reconstruct.py writes into the
.idml (including any shortened-to-fit wording), fragment by fragment.
"""

import sqlite3
from collections import defaultdict
from pathlib import Path

from lxml import etree

import story_placements
from overflow import StyleResolver

OTHER_PAGE = "Other text"

# How the visitor sees each kind of flag. kind: "review" items are
# highlighted and counted as needing a human; "fixed" and "info" are not.
EXCEPTION_FLAGS = {
    "missing_translation": ("review", "Not translated", "No usable translation came back for this text, so the "
                                                         "original wording was kept."),
    "translation_error": ("review", "Translated inconsistently", "The same English text was translated in "
                                                                "different ways in different places."),
    "layout_risk_heuristic": ("info", "Much longer or shorter than the original", "Worth a glance in InDesign "
                                                                                  "to check the layout."),
}


def _local(tag):
    return tag.split("}")[-1] if isinstance(tag, str) else ""


def spread_order(idml_dir: Path):
    """Spread file paths in the document's real order (designmap), falling back to name order."""
    idml_dir = Path(idml_dir)
    try:
        dm = etree.parse(str(idml_dir / "designmap.xml")).getroot()
        ordered = [idml_dir / el.get("src") for el in dm if _local(el.tag) == "Spread" and el.get("src")]
        ordered = [p for p in ordered if p.exists()]
        if ordered:
            return ordered
    except (OSError, etree.XMLSyntaxError):
        pass
    return sorted((idml_dir / "Spreads").glob("*.xml"))


def story_positions(idml_dir: Path):
    """story_self_id -> list of (spread_index, page_name, y, x) for each frame, in reading order."""
    positions = defaultdict(list)
    for s_index, path in enumerate(spread_order(idml_dir)):
        try:
            root = etree.parse(str(path), etree.XMLParser(recover=True)).getroot()
        except (OSError, etree.XMLSyntaxError):
            continue
        spread = root[0] if len(root) else root
        pages, placements = story_placements.find_frame_placements(spread)
        if not pages:
            continue
        tops = _frame_top_left(spread)
        for story_id, frame_id, point in placements:
            _page_self, page_name = story_placements.nearest_page(point, pages)
            page_index = next(i for i, p in enumerate(pages) if p[1] == page_name)
            top, left = tops.get(frame_id, (point[1], point[0]))
            # Reading order: top edge in 24pt bands (frames that start level are read left
            # to right), then left edge.
            positions[story_id].append((s_index, page_index, page_name, round(top / 24), round(left, 1)))
    for v in positions.values():
        v.sort()
    return positions


def _frame_top_left(spread):
    """frame Self -> (top, left) in spread space, from its own path and ItemTransform."""
    out = {}
    for el in spread.iter():
        if _local(el.tag) not in story_placements.FRAME_TAGS or not el.get("ParentStory"):
            continue
        m = story_placements.parse_transform(el.get("ItemTransform"))
        pts = []
        for pt in el.findall(".//{*}PathPointType"):
            if pt.get("Anchor"):
                x, y = (float(v) for v in pt.get("Anchor").split())
                pts.append(story_placements.apply_transform(m, x, y))
        if pts:
            out[el.get("Self")] = (min(p[1] for p in pts), min(p[0] for p in pts))
    return out


def _list_types(styles_path: Path):
    out = {}
    try:
        root = etree.parse(str(styles_path)).getroot()
    except (OSError, etree.XMLSyntaxError):
        return out
    for el in root.iter():
        if _local(el.tag) == "ParagraphStyle":
            t = el.get("BulletsAndNumberingListType")
            if t in ("BulletList", "NumberedList"):
                out[el.get("Self")] = "bullet" if t == "BulletList" else "number"
    return out


def _is_bold(style):
    s = (style or "").lower()
    return "bold" in s or "black" in s or "heavy" in s or "semibold" in s or s in ("600", "700", "800", "900")


def _is_italic(style):
    s = (style or "").lower()
    return "italic" in s or "oblique" in s


def build_preview(db_path, document_id, idml_extracted_dir, langs):
    idml_dir = Path(idml_extracted_dir)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    styles_path = idml_dir / "Resources" / "Styles.xml"
    resolver = StyleResolver(styles_path) if styles_path.exists() else None
    list_types = _list_types(styles_path)
    positions = story_positions(idml_dir)

    stories = conn.execute("SELECT id, story_self_id FROM stories WHERE document_id = ?", (document_id,)).fetchall()
    style_cache = {}

    def run_format(char_style, para_style):
        key = (char_style, para_style)
        if key not in style_cache:
            if resolver is None:
                style_cache[key] = (False, False, 11.0)
            else:
                r = resolver.resolve(char_style, para_style)
                style_cache[key] = (_is_bold(r["font_style"]), _is_italic(r["font_style"]), r["point_size"])
        return style_cache[key]

    story_blocks = {}
    for st in stories:
        runs = conn.execute("""
            SELECT id, raw_text, paragraph_style, character_style, is_table_cell, table_self_id,
                   cell_name, needs_translation, paragraph_seq
            FROM text_runs WHERE story_id = ? ORDER BY sequence_index
        """, (st["id"],)).fetchall()
        if not any(r["needs_translation"] for r in runs):
            continue

        blocks, tables = [], {}
        para_index = {}
        for r in runs:
            bold, italic, size = run_format(r["character_style"], r["paragraph_style"])
            run = {"id": r["id"], "text": r["raw_text"], "b": bold, "i": italic, "t": bool(r["needs_translation"])}
            if r["is_table_cell"] and r["table_self_id"]:
                table = tables.get(r["table_self_id"])
                if table is None:
                    table = {"type": "table", "cells": {}}
                    tables[r["table_self_id"]] = table
                    blocks.append(table)
                try:
                    col, row = (int(v) for v in (r["cell_name"] or "0:0").split(":"))
                except ValueError:
                    col, row = 0, len(table["cells"])
                table["cells"].setdefault((row, col), []).append(run)
                continue
            key = r["paragraph_seq"]
            if key not in para_index:
                pstyle = r["paragraph_style"] or ""
                _b, _i, psize = run_format(None, r["paragraph_style"])
                kind = "heading" if psize >= 13 else ("small" if psize <= 9.5 else "body")
                para_index[key] = {"type": "para", "kind": kind, "list": list_types.get(pstyle), "runs": []}
                blocks.append(para_index[key])
            para_index[key]["runs"].append(run)

        out_blocks = []
        for b in blocks:
            if b["type"] == "table":
                n_rows = max(k[0] for k in b["cells"]) + 1
                n_cols = max(k[1] for k in b["cells"]) + 1
                rows = [[b["cells"].get((ri, ci), []) for ci in range(n_cols)] for ri in range(n_rows)]
                out_blocks.append({"type": "table", "rows": rows})
            elif any(run["text"].strip() for run in b["runs"]):
                out_blocks.append(b)
        pos = positions.get(st["story_self_id"], [])
        story_blocks[st["story_self_id"]] = {
            "id": st["story_self_id"],
            "order": pos[0][:2] + pos[0][3:] if pos else (10 ** 6, 0, 0, 0),
            "page": pos[0][2] if pos else OTHER_PAGE,
            "pages": sorted({p[2] for p in pos}, key=lambda n: (len(n), n)),
            "blocks": out_blocks,
        }

    # Group into pages in reading order (top-to-bottom, then left-to-right).
    ordered = sorted(story_blocks.values(), key=lambda s: tuple(s["order"]))
    pages = []
    for s in ordered:
        if not pages or pages[-1]["name"] != s["page"]:
            pages.append({"name": s["page"], "stories": []})
        pages[-1]["stories"].append({"id": s["id"], "pages": s["pages"], "blocks": s["blocks"]})
    # Unplaced stories (master pages etc.) go last, under one heading.
    other = [p for p in pages if p["name"] == OTHER_PAGE]
    pages = [p for p in pages if p["name"] != OTHER_PAGE]
    if other:
        pages.append({"name": OTHER_PAGE, "stories": [s for p in other for s in p["stories"]]})

    lang_data = {lang: _language_view(conn, document_id, lang, story_blocks) for lang in langs}
    conn.close()
    return {"pages": pages, "langs": lang_data}


def _language_view(conn, document_id, lang, story_blocks):
    texts = {}
    for row in conn.execute("""
        SELECT t.id, t.raw_text, t.needs_translation, tr.translated_text, tr.status, o.retranslated_text
        FROM text_runs t JOIN stories s ON s.id = t.story_id
        LEFT JOIN translations tr ON tr.text_run_id = t.id AND tr.target_language = ?
        LEFT JOIN overflow_resolutions o ON o.text_run_id = t.id AND o.target_language = ?
        WHERE s.document_id = ?
    """, (lang, lang, document_id)):
        if row["status"] == "translated" and row["translated_text"] is not None:
            texts[row["id"]] = row["retranslated_text"] or row["translated_text"]

    flags = defaultdict(list)
    fit = {"fits": 0, "wrapped": 0, "shrunk": 0, "shortened": 0, "unresolved": 0}
    resolution_key = {"fits": "fits", "fits_wrapped": "wrapped", "fits_shrunk": "shrunk",
                      "fits_retranslated": "shortened", "unresolved": "unresolved"}
    for row in conn.execute("""
        SELECT o.text_run_id, o.resolution, o.shrink_pct, o.original_point_size, o.final_point_size,
               o.lines_needed, o.frame_height_pt, tr.translated_text
        FROM overflow_resolutions o
        JOIN text_runs t ON t.id = o.text_run_id JOIN stories s ON s.id = t.story_id
        LEFT JOIN translations tr ON tr.text_run_id = o.text_run_id AND tr.target_language = o.target_language
        WHERE s.document_id = ? AND o.target_language = ?
    """, (document_id, lang)):
        fit[resolution_key.get(row["resolution"], "fits")] += 1
        rid = row["text_run_id"]
        if row["resolution"] == "fits_shrunk":
            flags[rid].append({"kind": "fixed", "label": f"Text size reduced {row['shrink_pct']:g}% to fit",
                               "detail": f"{row['original_point_size']:g}pt → {row['final_point_size']:.1f}pt"})
        elif row["resolution"] == "fits_retranslated":
            flags[rid].append({"kind": "review", "label": "Shortened to fit — check the wording",
                               "detail": f"The first translation was too long for its frame: "
                                         f"“{row['translated_text']}”"})
        elif row["resolution"] == "unresolved":
            flags[rid].append({"kind": "review", "label": "Doesn't fit its frame",
                               "detail": f"Needs about {row['lines_needed']} lines but the frame holds less "
                                         f"({row['frame_height_pt']:.0f}pt tall), even after shrinking and "
                                         f"shortening. Enlarge the frame or edit the text in InDesign."})

    for row in conn.execute("""
        SELECT e.category, e.severity, ef.text_run_id FROM exceptions e
        JOIN exception_fragments ef ON ef.exception_id = e.id
        WHERE e.document_id = ? AND e.target_language = ?
    """, (document_id, lang)):
        spec = EXCEPTION_FLAGS.get(row["category"])
        if spec:
            kind, label, detail = spec
            if not any(f["label"] == label for f in flags[row["text_run_id"]]):
                flags[row["text_run_id"]].append({"kind": kind, "label": label, "detail": detail})

    paragraphs_total = paragraphs_done = fragments_done = 0
    for story in story_blocks.values():
        for b in story["blocks"]:
            groups = [b["runs"]] if b["type"] == "para" else [cell for row in b["rows"] for cell in row]
            for runs in groups:
                needed = [r for r in runs if r["t"]]
                if not needed:
                    continue
                paragraphs_total += 1
                done = [r for r in needed if r["id"] in texts]
                fragments_done += len(done)
                if len(done) == len(needed):
                    paragraphs_done += 1

    review_items = sum(1 for fl in flags.values() if any(f["kind"] == "review" for f in fl))
    return {
        "texts": {str(k): v for k, v in texts.items()},
        "flags": {str(k): v for k, v in flags.items() if v},
        "summary": {
            "paragraphs_total": paragraphs_total,
            "paragraphs_translated": paragraphs_done,
            "fragments_translated": fragments_done,
            "fit": fit,
            "auto_fixed": fit["shrunk"] + fit["shortened"],
            "review_items": review_items,
        },
    }
