"""Every configured language has fonts that cover its characters."""

import pytest
from fontTools.ttLib import TTFont

import languages
import overflow
from overflow import FONTS_ASSET_DIR

SAMPLE_CHARS = {
    "es": "áéíóúüñÁÉÍÓÚÑ¿¡«»",
    "fr": "àâæçéèêëîïôœùûüÿÀÂÇÉÈÊËÎÏÔŒÙÛÜ«»’",
    "de": "äöüßÄÖÜ„“‚‘",
    "pt": "áâãàçéêíóôõúÁÂÃÀÇÉÊÍÓÔÕÚ",
    "ar": "ابتثجحخدذرزسشصضطظعغفقكلمنهويءآأؤإئةى٠١٢٣٤٥٦٧٨٩،؛؟",
}
LATIN_FONTS = ["LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf", "LiberationSans-Italic.ttf",
               "Inter-Regular.ttf", "Inter-Bold.ttf"]


def test_every_language_has_test_characters():
    assert set(SAMPLE_CHARS) == set(languages.LANGUAGES)


@pytest.mark.parametrize("code", sorted(languages.LANGUAGES))
def test_font_coverage(code):
    lang = languages.get(code)
    files = list(lang.font_files.values()) if lang.font else LATIN_FONTS
    for f in files:
        cmap = TTFont(FONTS_ASSET_DIR / f).getBestCmap()
        missing = [c for c in SAMPLE_CHARS[code] if ord(c) not in cmap]
        assert not missing, f"{f} lacks {''.join(missing)} needed for {lang.name}"


@pytest.mark.parametrize("code", sorted(languages.LANGUAGES))
def test_measurement_works_for_each_language(code):
    w, _ = overflow.measure_text_width_pt(SAMPLE_CHARS[code], "Arial", "Regular", 10, code)
    assert w > 0


def test_config_is_consistent():
    import translate
    for code, lang in languages.LANGUAGES.items():
        assert translate.LANGUAGE_NAMES[code] == lang.prompt_name
        assert lang.direction in ("ltr", "rtl")
        if lang.font:
            assert lang.font_files and all((FONTS_ASSET_DIR / f).exists() for f in lang.font_files.values())
