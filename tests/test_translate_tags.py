"""Tagged-paragraph build/parse round trip (translate.py)."""

import translate


def frag(i, text, needs=1):
    return {"id": i, "raw_text": text, "needs_translation": needs}


def test_build_wraps_translatable_and_keeps_anchors():
    frags = [frag(1, "Write a fraction equal to "), frag(2, "3/5", 0), frag(3, ".", 0)]
    tagged, ws = translate.build_tagged_paragraph(frags)
    assert tagged == "<t1>Write a fraction equal to</t1>3/5."  # edge spaces are re-attached after translation
    assert ws[1] == ("", " ")
    assert 2 not in ws and 3 not in ws


def test_round_trip_restores_edge_whitespace():
    frags = [frag(10, "  The "), frag(11, "numerator"), frag(12, " is the top number. ")]
    tagged, ws = translate.build_tagged_paragraph(frags)
    assert tagged == "<t10>The</t10><t11>numerator</t11><t12>is the top number.</t12>"
    parsed = translate.parse_tagged_result("<t10>El</t10> <t11>numerador</t11> <t12>es el número de arriba.</t12>")
    assert parsed == {10: "El", 11: "numerador", 12: "es el número de arriba."}
    rebuilt = {i: ws[i][0] + parsed[i] + ws[i][1] for i in parsed}
    assert rebuilt[10] == "  El "
    assert rebuilt[12] == " es el número de arriba. "


def test_parse_handles_reordered_tags_and_multiline():
    out = translate.parse_tagged_result("<t2>segundo</t2> y <t1>primero\nlínea</t1>")
    assert out == {1: "primero\nlínea", 2: "segundo"}


def test_parse_ignores_mismatched_tags():
    assert translate.parse_tagged_result("<t1>roto</t2> <t3>ok</t3>") == {3: "ok"}


def test_dry_run_translates_every_tag(tmp_path, sample_extracted):
    import deconstruct
    import sqlite3
    db = str(tmp_path / "r.db")
    doc = deconstruct.deconstruct(str(sample_extracted), "s.idml", db)
    stats = translate.translate_document(db, doc, ["es"], dry_run=True)
    assert stats["es"]["errors"] == 0 and stats["es"]["translated"] > 50
    rows = sqlite3.connect(db).execute(
        "SELECT translated_text FROM translations WHERE status='translated'").fetchall()
    assert all(r[0].lstrip().startswith("[es]") for r in rows)
