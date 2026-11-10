"""Overflow measurement against known strings and frames (overflow.py)."""

import pytest
from fontTools.ttLib import TTFont

import overflow
from overflow import FONTS_ASSET_DIR


def advance_sum(font_file, text, size):
    """Independent check: plain sum of advance widths (no kerning in this string)."""
    f = TTFont(FONTS_ASSET_DIR / font_file)
    cmap, hmtx, upem = f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm
    return sum(hmtx[cmap[ord(c)]][0] for c in text) / upem * size


def test_measurement_matches_font_metrics():
    width, note = overflow.measure_text_width_pt("Equivalent", "Arial", "Regular", 10, "es")
    assert width == pytest.approx(advance_sum("LiberationSans-Regular.ttf", "Equivalent", 10), rel=0.02)
    assert "same metrics as Arial" in note


def test_bold_is_wider_and_size_scales_linearly():
    reg, _ = overflow.measure_text_width_pt("Fractions", "Arial", "Regular", 12, "fr")
    bold, _ = overflow.measure_text_width_pt("Fractions", "Arial", "Bold", 12, "fr")
    double, _ = overflow.measure_text_width_pt("Fractions", "Arial", "Regular", 24, "fr")
    assert bold > reg
    assert double == pytest.approx(2 * reg, rel=1e-6)


def test_arabic_uses_bundled_arabic_font_exactly():
    path, _num, approx, note = overflow.resolve_font_file("Arial", "Regular", "ar")
    assert path.endswith("NotoSansArabic-Regular.ttf") and not approx
    width, _ = overflow.measure_text_width_pt("الكسور المتكافئة", "Arial", "Regular", 12, "ar")
    assert width > 0


GEO = {"usable_width_pt": 100.0, "frame_height_pt": 30.0}


def test_tiers_fit_wrap_shrink_unresolved():
    fits = overflow.resolve_overflow("Half", "Arial", "Regular", 12, 14, GEO, "es")
    assert fits["resolution"] == "fits" and fits["tier"] == 1

    wrapped = overflow.resolve_overflow("one two three four five six", "Arial", "Regular", 12, 14, GEO, "es")
    assert wrapped["resolution"] == "fits_wrapped" and wrapped["detail"]["lines_needed"] == 2

    # The sample's title frame: Spanish needs 2 lines at 28pt (one won't fit 300pt), fits on one at 25.2pt.
    shrunk = overflow.resolve_overflow("Fracciones equivalentes", "Arial", "Bold", 28, 32,
                                       {"usable_width_pt": 300, "frame_height_pt": 36}, "es")
    assert shrunk["resolution"] == "fits_shrunk" and shrunk["shrink_pct"] == 10
    assert shrunk["final_point_size"] == pytest.approx(25.2)

    unresolved = overflow.resolve_overflow("x " * 200, "Arial", "Regular", 12, 14, GEO, "es")
    assert unresolved["resolution"] == "unresolved"


def test_frame_geometry_from_sample(sample_extracted):
    # The title frame is 300pt wide with no insets; the "Remember" callout has 10pt insets.
    from lxml import etree
    spreads = sorted((sample_extracted / "Spreads").glob("*.xml"))
    frames = [el for el in etree.parse(str(spreads[0])).iter() if el.tag == "TextFrame"]
    widths = {}
    for f in frames:
        geo = overflow.get_frame_geometry(str(sample_extracted), f.get("Self"))
        widths[f.get("Self")] = geo
    usable = sorted(round(g["usable_width_pt"]) for g in widths.values())
    assert 300 in usable and 152 in usable
    callout = next(g for g in widths.values() if round(g["usable_width_pt"]) == 152)
    assert callout["frame_height_pt"] == pytest.approx(212 - 20)
