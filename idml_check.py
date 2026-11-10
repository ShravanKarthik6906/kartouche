"""
Structural checks for an IDML package (an InDesign Markup Language file,
which is a zip of XML files).

Only InDesign itself can say for certain that a file opens, but these checks
catch everything that would make a package plainly broken:

  * `mimetype` is the first entry, stored uncompressed, with the IDML type;
  * META-INF/container.xml and designmap.xml exist;
  * every XML file is well-formed;
  * every file designmap.xml points to exists, and every Stories/ and
    Spreads/ file is referenced from it;
  * every story in designmap's StoryList has a story file;
  * every text frame's ParentStory exists, and threaded frames
    (NextTextFrame / PreviousTextFrame) point at real frames, both ways;
  * Self ids are unique across spreads and stories.

    python idml_check.py path/to/file.idml   # prints problems, exit 1 if any
"""

import re
import sys
import zipfile

from lxml import etree

IDML_MIMETYPE = "application/vnd.adobe.indesign-idml-package"
PKG_SRC_RE = re.compile(r"^(Spreads|MasterSpreads|Stories|Resources|XML)/")


def _local(tag):
    return tag.split("}")[-1] if isinstance(tag, str) else ""


def check_idml(path):
    """Returns a list of human-readable problems (empty list = looks valid)."""
    problems = []
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as e:
        return [f"not a zip archive: {e}"]

    with zf:
        infos = zf.infolist()
        names = [i.filename for i in infos]
        if not names or names[0] != "mimetype":
            problems.append("first entry is not 'mimetype'")
        elif infos[0].compress_type != zipfile.ZIP_STORED:
            problems.append("'mimetype' is compressed (must be stored)")
        elif zf.read("mimetype").decode("ascii", "replace").strip() != IDML_MIMETYPE:
            problems.append("'mimetype' has the wrong content")

        for required in ("META-INF/container.xml", "designmap.xml"):
            if required not in names:
                problems.append(f"missing {required}")

        trees = {}
        for name in names:
            if name.endswith(".xml"):
                try:
                    trees[name] = etree.fromstring(zf.read(name))
                except etree.XMLSyntaxError as e:
                    problems.append(f"{name}: XML is not well-formed ({e})")

    dm = trees.get("designmap.xml")
    if dm is None:
        return problems

    referenced = set()
    for el in dm.iter():
        src = el.get("src")
        if src:
            referenced.add(src)
            if src not in names:
                problems.append(f"designmap.xml points to missing file {src}")
    for name in names:
        if name.startswith(("Stories/", "Spreads/", "MasterSpreads/")) and name not in referenced:
            problems.append(f"{name} is not referenced from designmap.xml")

    story_ids = set()
    for name, root in trees.items():
        if name.startswith("Stories/"):
            for el in root.iter():
                if _local(el.tag) == "Story":
                    story_ids.add(el.get("Self"))
    for sid in (dm.get("StoryList") or "").split():
        if sid not in story_ids:
            problems.append(f"StoryList names story {sid} but no Stories/ file defines it")

    # Every style / swatch a story or spread applies must be defined.
    defined = set()
    for name in ("Resources/Styles.xml", "Resources/Graphic.xml"):
        if name in trees:
            defined |= {el.get("Self") for el in trees[name].iter() if el.get("Self")}
    ref_attrs = ("AppliedParagraphStyle", "AppliedCharacterStyle", "AppliedCellStyle", "AppliedTableStyle",
                 "AppliedObjectStyle", "FillColor", "StrokeColor")
    if defined:
        for name, root in trees.items():
            if not name.startswith(("Spreads/", "MasterSpreads/", "Stories/", "Resources/Styles")):
                continue
            for el in root.iter():
                for attr in ref_attrs:
                    ref = el.get(attr)
                    if ref and ref != "n" and ref not in defined:
                        problems.append(f"{name}: {attr}={ref} is not defined")

    frames, seen_self = {}, {}
    for name, root in trees.items():
        if not name.startswith(("Spreads/", "MasterSpreads/", "Stories/")):
            continue
        for el in root.iter():
            self_id = el.get("Self")
            if self_id:
                if self_id in seen_self and seen_self[self_id] != name:
                    problems.append(f"Self id {self_id} used in both {seen_self[self_id]} and {name}")
                elif self_id in seen_self:
                    problems.append(f"Self id {self_id} used twice in {name}")
                seen_self[self_id] = name
            if _local(el.tag) == "TextFrame":
                frames[self_id] = el
    for fid, el in frames.items():
        ps = el.get("ParentStory")
        if ps and ps not in story_ids:
            problems.append(f"text frame {fid} belongs to unknown story {ps}")
        nxt, prev = el.get("NextTextFrame", "n"), el.get("PreviousTextFrame", "n")
        if nxt != "n":
            if nxt not in frames:
                problems.append(f"text frame {fid} threads to missing frame {nxt}")
            elif frames[nxt].get("PreviousTextFrame") != fid:
                problems.append(f"text frame {fid} -> {nxt} thread is not mirrored")
            elif frames[nxt].get("ParentStory") != ps:
                problems.append(f"threaded frames {fid} and {nxt} belong to different stories")
        if prev != "n" and prev not in frames:
            problems.append(f"text frame {fid} threads from missing frame {prev}")
    return problems


def linked_files(path):
    """File names (not paths) of every linked asset an IDML package refers to."""
    out = set()
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if name.startswith(("Spreads/", "MasterSpreads/", "Stories/")) and name.endswith(".xml"):
                for m in re.finditer(rb'LinkResourceURI="([^"]+)"', zf.read(name)):
                    uri = m.group(1).decode("utf-8", "replace")
                    tail = uri.replace("\\", "/").rsplit("/", 1)[-1]
                    tail = tail.split(":", 1)[-1] if "/" not in uri else tail
                    from urllib.parse import unquote
                    if tail:
                        out.add(unquote(tail))
    return out


if __name__ == "__main__":
    issues = check_idml(sys.argv[1])
    for p in issues:
        print("-", p)
    print("OK" if not issues else f"{len(issues)} problem(s)")
    sys.exit(1 if issues else 0)
