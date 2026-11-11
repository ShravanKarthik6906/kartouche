"""
Upload handling: accept what people actually have, validate it, and unpack
it safely for the pipeline.

Accepted:
  * a plain .idml file (images then can't be relinked - we say so);
  * a .zip containing exactly one .idml, plus optionally its Links/ folder
    at any depth (e.g. an InDesign "Package" folder, zipped). macOS junk
    (__MACOSX/, ._files, .DS_Store) is ignored.

Every problem raises UploadError with a plain-language message that says
what to do next. Nothing here calls the network or spends money.
"""

import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from lxml import etree

import idml_check
from deconstruct import looks_translatable

# A real IDML is mostly small XML; Links can hold large images. Refuse
# archives that would expand to more than this (zip-bomb guard).
MAX_UNCOMPRESSED_BYTES = 2 * 1024 ** 3
MAX_ZIP_ENTRIES = 20000

EXPORT_HINT = "In InDesign choose File › Export… and pick “InDesign Markup (IDML)”."


class UploadError(ValueError):
    """A problem with the uploaded file, worded for the person who uploaded it."""


@dataclass
class PreparedUpload:
    idml_filename: str              # e.g. "Brochure.idml"
    idml_path: Path                 # the original .idml, copied into the job folder
    extracted_dir: Path             # the unpacked IDML, with Links/ inside if provided
    links_found: list = field(default_factory=list)
    links_missing: list = field(default_factory=list)
    links_provided: bool = False    # a Links folder (or loose images) came with the upload
    word_count: int = 0             # words that will be sent for translation
    story_count: int = 0


def is_junk(name: str) -> bool:
    parts = PurePosixPath(name).parts
    return any(p == "__MACOSX" or p.startswith("._") or p in (".DS_Store", "Thumbs.db") for p in parts)


def _safe_target(base: Path, rel: str) -> Path | None:
    """Resolve rel under base, refusing absolute paths and '..' escapes."""
    rel = rel.replace("\\", "/")
    if rel.startswith("/") or any(part == ".." for part in rel.split("/")):
        return None
    target = (base / rel).resolve()
    try:
        target.relative_to(base.resolve())
    except ValueError:
        return None
    return target


def _open_zip(path: Path, what: str):
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError):
        raise UploadError(f"This {what} couldn't be opened - it may be damaged or not really a {what}.")
    infos = zf.infolist()
    if len(infos) > MAX_ZIP_ENTRIES or sum(i.file_size for i in infos) > MAX_UNCOMPRESSED_BYTES:
        zf.close()
        raise UploadError(f"This {what} is too large once unpacked. Please upload a smaller document.")
    return zf


def _extract_idml(idml_path: Path, out_dir: Path):
    """Unpack an .idml package after checking it really is one."""
    try:
        zf = zipfile.ZipFile(idml_path)
    except (zipfile.BadZipFile, OSError):
        raise UploadError(f"This file isn't a valid .idml file (it may be an .indd saved with the wrong "
                          f"extension). {EXPORT_HINT}")
    with zf:
        names = zf.namelist()
        if "designmap.xml" not in names or not any(n.startswith("Stories/") for n in names):
            raise UploadError(f"This .idml file looks incomplete - it has no document map or no text stories. "
                              f"Try exporting it from InDesign again. {EXPORT_HINT}")
        if len(names) > MAX_ZIP_ENTRIES or sum(i.file_size for i in zf.infolist()) > MAX_UNCOMPRESSED_BYTES:
            raise UploadError("This .idml file is too large once unpacked. Please upload a smaller document.")
        out_dir.mkdir(parents=True, exist_ok=True)
        for info in zf.infolist():
            if info.is_dir():
                continue
            target = _safe_target(out_dir, info.filename)
            if target is None:
                raise UploadError("This .idml file contains unsafe file paths and can't be processed.")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
    try:
        etree.parse(str(out_dir / "designmap.xml"))
    except etree.XMLSyntaxError:
        raise UploadError(f"This .idml file is damaged (its document map can't be read). {EXPORT_HINT}")


def count_words(extracted_dir: Path):
    """(translatable words, number of stories) - matches what deconstruct will send."""
    words, stories = 0, 0
    for story in sorted((extracted_dir / "Stories").glob("Story_*.xml")):
        stories += 1
        try:
            root = etree.parse(str(story), etree.XMLParser(recover=True)).getroot()
        except etree.XMLSyntaxError:
            continue
        if root is None:
            continue
        for el in root.iter():
            if isinstance(el.tag, str) and el.tag.split("}")[-1] == "Content" and el.text:
                if looks_translatable(el.text):
                    words += len(el.text.split())
    return words, stories


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".psd", ".ai", ".eps", ".pdf", ".svg", ".gif",
                  ".bmp", ".indd", ".idms", ".heic", ".webp"}


def prepare_upload(upload_path: Path, original_filename: str, job_dir: Path) -> PreparedUpload:
    """Validate the uploaded file and unpack it into job_dir. Raises UploadError."""
    suffix = Path(original_filename or "").suffix.lower()
    extracted_dir = job_dir / "idml_extracted"
    links_dir = extracted_dir / "Links"

    if suffix == ".indd":
        raise UploadError(f"Kartouche needs an .idml file, not an .indd file. {EXPORT_HINT}")
    if suffix not in (".idml", ".zip"):
        raise UploadError("Please upload an .idml file, or a .zip containing one .idml file "
                          "(and, optionally, its Links folder).")

    links_provided = False
    if suffix == ".idml":
        idml_filename = Path(original_filename).name
        idml_path = job_dir / idml_filename
        shutil.move(str(upload_path), idml_path)
        _extract_idml(idml_path, extracted_dir)
    else:
        zf = _open_zip(upload_path, "zip file")
        with zf:
            members = [i for i in zf.infolist() if not i.is_dir() and not is_junk(i.filename)]
            idmls = [i for i in members if i.filename.lower().endswith(".idml")]
            if not idmls:
                if any(i.filename.lower().endswith(".indd") for i in members):
                    raise UploadError(f"This zip contains an .indd file but no .idml file. {EXPORT_HINT}")
                raise UploadError("This zip doesn't contain an .idml file. Add the .idml exported from "
                                  "InDesign and try again.")
            if len(idmls) > 1:
                listed = ", ".join(PurePosixPath(i.filename).name for i in idmls[:4])
                raise UploadError(f"This zip contains {len(idmls)} .idml files ({listed}). Please upload one "
                                  f"document at a time.")
            idml_info = idmls[0]
            idml_filename = PurePosixPath(idml_info.filename).name
            idml_path = job_dir / idml_filename
            with zf.open(idml_info) as src, open(idml_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
            _extract_idml(idml_path, extracted_dir)

            # Links: anything inside a folder named "Links" (any depth, any case).
            # Fallback: image files sitting loose next to the .idml.
            link_members = []
            for info in members:
                parts = PurePosixPath(info.filename).parts
                idx = next((k for k, p in enumerate(parts[:-1]) if p.lower() == "links"), None)
                if idx is not None:
                    link_members.append((info, "/".join(parts[idx + 1:])))
            if not link_members:
                idml_parent = PurePosixPath(idml_info.filename).parent
                for info in members:
                    p = PurePosixPath(info.filename)
                    if p.parent == idml_parent and p.suffix.lower() in IMAGE_SUFFIXES and info is not idml_info:
                        link_members.append((info, p.name))
            for info, rel in link_members:
                target = _safe_target(links_dir, rel)
                if target is None:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            links_provided = bool(link_members)
        upload_path.unlink(missing_ok=True)

    referenced = idml_check.linked_files(idml_path)
    present = {p.name for p in links_dir.rglob("*") if p.is_file()} if links_dir.exists() else set()
    words, stories = count_words(extracted_dir)
    if stories == 0:
        raise UploadError(f"This .idml file has no text stories to translate. {EXPORT_HINT}")
    if words == 0:
        raise UploadError("We couldn't find any translatable text in this document. It may contain only "
                          "images, numbers or outlined text.")

    return PreparedUpload(
        idml_filename=idml_filename,
        idml_path=idml_path,
        extracted_dir=extracted_dir,
        links_found=sorted(referenced & present),
        links_missing=sorted(referenced - present),
        links_provided=links_provided,
        word_count=words,
        story_count=stories,
    )
