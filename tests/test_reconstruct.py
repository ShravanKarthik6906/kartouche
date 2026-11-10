"""Reconstruction: RTL flip, script font, size overrides, link paths, packaging (reconstruct.py)."""

import sqlite3
import zipfile

import deconstruct
import idml_check
import reconstruct
import story_placements
import translate


def prepare(tmp_path, sample_extracted, langs):
    db = str(tmp_path / "r.db")
    doc = deconstruct.deconstruct(str(sample_extracted), "fractions_lesson.idml", db)
    story_placements.populate_story_placements(db, doc, str(sample_extracted))
    translate.translate_document(db, doc, langs, dry_run=True)
    return db, doc


def stories_text(idml_path):
    with zipfile.ZipFile(idml_path) as zf:
        return {n: zf.read(n).decode() for n in zf.namelist() if n.startswith("Stories/")}


def test_arabic_is_rtl_with_arabic_font(tmp_path, sample_extracted):
    db, doc = prepare(tmp_path, sample_extracted, ["ar"])
    res = reconstruct.reconstruct(db, doc, "ar", str(sample_extracted), str(tmp_path / "work_ar"))
    assert res["rtl_flips"] == 9 and res["missing"] == 0
    stories = stories_text(res["idml_path"])
    for xml in stories.values():
        assert 'StoryDirection="RightToLeftDirection"' in xml
        assert 'StoryDirection="LeftToRightDirection"' not in xml
    assert any("<AppliedFont type=\"string\">Noto Sans Arabic</AppliedFont>" in x for x in stories.values())
    with zipfile.ZipFile(res["idml_path"]) as zf:
        assert b"Noto Sans Arabic" in zf.read("Resources/Fonts.xml")
    with zipfile.ZipFile(res["bundle_path"]) as zf:
        names = zf.namelist()
    assert "Document Fonts/NotoSansArabic-Regular.ttf" in names
    assert "Links/number_line.png" in names


def test_latin_language_stays_ltr_without_font_override(tmp_path, sample_extracted):
    db, doc = prepare(tmp_path, sample_extracted, ["de"])
    res = reconstruct.reconstruct(db, doc, "de", str(sample_extracted), str(tmp_path / "work_de"))
    assert res["rtl_flips"] == 0
    stories = stories_text(res["idml_path"])
    assert all("RightToLeftDirection" not in x and "Noto Sans Arabic" not in x for x in stories.values())
    assert any("[de]Equivalent Fractions" in x for x in stories.values())
    with zipfile.ZipFile(res["bundle_path"]) as zf:
        assert not any(n.startswith("Document Fonts/") for n in zf.namelist())


def test_output_is_a_valid_idml(tmp_path, sample_extracted):
    db, doc = prepare(tmp_path, sample_extracted, ["es"])
    res = reconstruct.reconstruct(db, doc, "es", str(sample_extracted), str(tmp_path / "w"))
    with zipfile.ZipFile(res["idml_path"]) as zf:
        first = zf.infolist()[0]
        assert first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED
        assert not any(n.startswith("Links/") for n in zf.namelist())
    assert idml_check.check_idml(res["idml_path"]) == []


def test_shrink_override_written_as_point_size(tmp_path, sample_extracted):
    db, doc = prepare(tmp_path, sample_extracted, ["es"])
    conn = sqlite3.connect(db)
    title_id = conn.execute("SELECT id FROM text_runs WHERE raw_text = 'Equivalent Fractions'").fetchone()[0]
    conn.execute("""INSERT INTO overflow_resolutions (text_run_id, target_language, resolution,
                    original_point_size, final_point_size, shrink_pct) VALUES (?, 'es', 'fits_shrunk', 28, 25.2, 10)""",
                 (title_id,))
    conn.commit()
    res = reconstruct.reconstruct(db, doc, "es", str(sample_extracted), str(tmp_path / "w"))
    assert res["shrunk"] == 1
    assert any('PointSize="25.2"' in x for x in stories_text(res["idml_path"]).values())


def test_absolute_link_paths_become_relative(tmp_path, sample_extracted):
    spread = sorted((sample_extracted / "Spreads").glob("*.xml"))[0]
    spread.write_text(spread.read_text().replace(
        'LinkResourceURI="file:Links/fraction_bars.png"',
        'LinkResourceURI="file:/Users/someone/Jobs/Lesson%20Folder/Links/fraction_bars.png"'))
    db, doc = prepare(tmp_path, sample_extracted, ["es"])
    res = reconstruct.reconstruct(db, doc, "es", str(sample_extracted), str(tmp_path / "w"))
    assert res["link_uris_rewritten"] == 1
    with zipfile.ZipFile(res["idml_path"]) as zf:
        xml = zf.read("Spreads/" + spread.name).decode()
    assert 'LinkResourceURI="file:Links/fraction_bars.png"' in xml and "/Users/" not in xml
