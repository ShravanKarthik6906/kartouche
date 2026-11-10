"""
The one place that defines which target languages Rosetta offers.

Every other module (translation prompts, font measurement, right-to-left
handling in reconstruction, the web UI, the preview) reads from here, so
adding a language is a single entry below plus a check that the fonts
cover its characters (tests/test_languages.py does that automatically).

Fields:
  code          ISO 639-1 code, used in URLs, file names and the database.
  name          English display name.
  native        The language's own name for itself (shown in the UI).
  prompt_name   How the language is named to the translation model.
  direction     "ltr" or "rtl". RTL languages get StoryDirection flipped.
  font          None = keep the document's own fonts (they cover Latin
                scripts). Otherwise a font family that is applied to every
                translated run, measured exactly, and shipped in the
                delivery package, because typical document fonts have no
                glyphs for that script.
  font_files    {style: file in fonts/} for `font`.
  script        OpenType script tag for HarfBuzz shaping (None = guess).
  css_font      Font stack the browser preview uses.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Language:
    code: str
    name: str
    native: str
    prompt_name: str
    direction: str = "ltr"
    font: str | None = None
    font_files: dict = field(default_factory=dict)
    script: str | None = None
    css_font: str = "var(--font-doc)"

    @property
    def rtl(self) -> bool:
        return self.direction == "rtl"


LANGUAGES = {
    lang.code: lang
    for lang in (
        Language("es", "Spanish", "Español", "Spanish"),
        Language("fr", "French", "Français", "French"),
        Language("de", "German", "Deutsch", "German"),
        Language("pt", "Portuguese", "Português", "Brazilian Portuguese"),
        Language(
            "ar", "Arabic", "العربية", "Arabic",
            direction="rtl",
            font="Noto Sans Arabic",
            font_files={"Regular": "NotoSansArabic-Regular.ttf", "Bold": "NotoSansArabic-Bold.ttf"},
            script="Arab",
            css_font="'Noto Sans Arabic', var(--font-doc)",
        ),
    )
}

DEFAULT_SELECTION = ("es", "ar")


def get(code: str) -> Language:
    return LANGUAGES[code]


def name(code: str) -> str:
    lang = LANGUAGES.get(code)
    return lang.name if lang else code
