"""The built-in sample is a structurally valid, reproducible IDML."""

import shutil
import zipfile

import idml_check
from conftest import ROOT, SAMPLE_IDML, SAMPLE_ZIP


def test_sample_passes_structure_checks():
    assert idml_check.check_idml(SAMPLE_IDML) == []


def test_sample_exercises_the_features_it_claims():
    with zipfile.ZipFile(SAMPLE_IDML) as zf:
        stories = "".join(zf.read(n).decode() for n in zf.namelist() if n.startswith("Stories/"))
        spreads = "".join(zf.read(n).decode() for n in zf.namelist() if n.startswith("Spreads/"))
    assert "<Table " in stories
    assert 'CharacterStyle/Bold' in stories and 'CharacterStyle/Italic' in stories
    assert "ParagraphStyle/Bullet" in stories and "ParagraphStyle/Numbered" in stories
    assert spreads.count("<Image ") == 3
    threaded = [line for line in spreads.split("<TextFrame ") if 'NextTextFrame="u' in line]
    assert len(threaded) == 1
    assert idml_check.linked_files(SAMPLE_IDML) == {"fraction_bars.png", "number_line.png", "fraction_circles.png"}


def test_generator_is_deterministic(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("make_sample_copy", ROOT / "samples" / "make_sample.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "OUT_DIR", tmp_path / "fractions_lesson")
    monkeypatch.setattr(mod, "ZIP_PATH", tmp_path / "fractions_lesson.zip")
    mod.build()
    assert (tmp_path / "fractions_lesson.zip").read_bytes() == SAMPLE_ZIP.read_bytes()


def test_checker_catches_broken_packages(tmp_path):
    broken = tmp_path / "broken.idml"
    with zipfile.ZipFile(SAMPLE_IDML) as src, zipfile.ZipFile(broken, "w") as dst:
        for info in src.infolist():
            data = src.read(info)
            if info.filename.startswith("Stories/") and b"u103" in data[:400]:
                continue  # drop the threaded body story
            if info.filename == "Resources/Styles.xml":
                data = data.replace(b'Self="ParagraphStyle/Caption"', b'Self="ParagraphStyle/Gone"')
            dst.writestr(info, data, compress_type=info.compress_type)
    problems = "\n".join(idml_check.check_idml(broken))
    assert "missing file Stories/Story_u103.xml" in problems
    assert "belongs to unknown story u103" in problems
    assert "ParagraphStyle/Caption is not defined" in problems
