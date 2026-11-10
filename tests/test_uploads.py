"""Upload validation (uploads.py) and the upload size limit (app.py)."""

import io
import zipfile

import pytest

import uploads
from conftest import SAMPLE_DIR, SAMPLE_IDML, SAMPLE_ZIP


def make_zip(path, entries):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return path


def links():
    return {p.name: p.read_bytes() for p in (SAMPLE_DIR / "Links").iterdir()}


def test_plain_idml(tmp_path):
    up = tmp_path / "upload.idml"
    up.write_bytes(SAMPLE_IDML.read_bytes())
    job = tmp_path / "job"
    job.mkdir()
    prep = uploads.prepare_upload(up, "My Lesson.idml", job)
    assert prep.idml_filename == "My Lesson.idml"
    assert (prep.extracted_dir / "designmap.xml").exists()
    assert not prep.links_provided
    assert prep.links_missing == ["fraction_bars.png", "fraction_circles.png", "number_line.png"]
    assert 200 < prep.word_count < 1000


def test_sample_zip_with_links(tmp_path):
    up = tmp_path / "upload.zip"
    up.write_bytes(SAMPLE_ZIP.read_bytes())
    (tmp_path / "job").mkdir()
    prep = uploads.prepare_upload(up, "fractions_lesson.zip", tmp_path / "job")
    assert prep.links_missing == []
    assert len(prep.links_found) == 3
    assert (prep.extracted_dir / "Links" / "number_line.png").exists()


def test_deeply_nested_links_and_mac_junk(tmp_path):
    entries = {"__MACOSX/Pack/._lesson.idml": b"junk", "Pack/.DS_Store": b"junk",
               "Pack/Inner/lesson.idml": SAMPLE_IDML.read_bytes()}
    for name, data in links().items():
        entries[f"Pack/Inner/Deeper/Links/{name}"] = data
        entries[f"__MACOSX/Pack/Inner/Deeper/Links/._{name}"] = b"junk"
    up = make_zip(tmp_path / "u.zip", entries)
    (tmp_path / "job").mkdir()
    prep = uploads.prepare_upload(up, "u.zip", tmp_path / "job")
    assert prep.idml_filename == "lesson.idml"
    assert prep.links_missing == []
    assert not any(p.name.startswith("._") for p in (prep.extracted_dir / "Links").rglob("*"))


def test_zip_with_some_links_missing(tmp_path):
    entries = {"lesson.idml": SAMPLE_IDML.read_bytes(),
               "Links/fraction_bars.png": links()["fraction_bars.png"]}
    up = make_zip(tmp_path / "u.zip", entries)
    (tmp_path / "job").mkdir()
    prep = uploads.prepare_upload(up, "u.zip", tmp_path / "job")
    assert prep.links_provided
    assert prep.links_missing == ["fraction_circles.png", "number_line.png"]


@pytest.mark.parametrize("entries, filename, message", [
    ({"notes.txt": b"hi"}, "u.zip", "doesn't contain an .idml"),
    ({"a.idml": SAMPLE_IDML.read_bytes(), "b/b.idml": SAMPLE_IDML.read_bytes()}, "u.zip", "2 .idml files"),
    ({"doc.indd": b"x"}, "u.zip", ".indd file but no .idml"),
    ({"bad.idml": b"not a zip"}, "u.zip", "isn't a valid .idml"),
    ({"x.idml": None}, "u.zip", "looks incomplete"),
])
def test_bad_zips(tmp_path, entries, filename, message):
    if entries.get("x.idml", 1) is None:
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, "w") as zf:
            zf.writestr("mimetype", "application/vnd.adobe.indesign-idml-package")
        entries = {"x.idml": inner.getvalue()}
    up = make_zip(tmp_path / "u.zip", entries)
    (tmp_path / "job").mkdir()
    with pytest.raises(uploads.UploadError, match=message):
        uploads.prepare_upload(up, filename, tmp_path / "job")


@pytest.mark.parametrize("filename, message", [
    ("doc.indd", "not an .indd"), ("notes.pdf", "Please upload an .idml"), ("broken.zip", "couldn't be opened")])
def test_wrong_file_types(tmp_path, filename, message):
    up = tmp_path / "up"
    up.write_bytes(b"not really")
    (tmp_path / "job").mkdir()
    with pytest.raises(uploads.UploadError, match=message):
        uploads.prepare_upload(up, filename, tmp_path / "job")


def test_unsafe_link_paths_are_skipped(tmp_path):
    entries = {"lesson.idml": SAMPLE_IDML.read_bytes(), "Links/../../evil.png": b"x",
               "Links/fraction_bars.png": b"png"}
    up = make_zip(tmp_path / "u.zip", entries)
    (tmp_path / "job").mkdir()
    uploads.prepare_upload(up, "u.zip", tmp_path / "job")
    assert not (tmp_path / "evil.png").exists() and not (tmp_path / "job" / "evil.png").exists()


def test_oversize_upload_rejected_with_clear_message(make_app):
    app, client, _ = make_app(MAX_UPLOAD_MB="0.01")
    data = {"langs": "es", "document": (io.BytesIO(b"x" * 20000), "big.idml")}
    resp = client.post("/upload", data=data, content_type="multipart/form-data",
                       headers={"X-Requested-With": "fetch"})
    assert resp.status_code == 413
    assert "upload limit" in resp.get_json()["error"]
