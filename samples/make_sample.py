"""
Generate Kartouche's built-in sample document: a short, original grade-4
math lesson on equivalent fractions, as a real IDML package.

    python samples/make_sample.py

Writes:
    samples/fractions_lesson/fractions_lesson.idml
    samples/fractions_lesson/Links/*.png
    samples/fractions_lesson.zip          (ready to upload to Kartouche)

Everything here (text, layout, art) is original and generated in code.
The package structure follows Adobe's published IDML specification:
`mimetype` (stored, first), META-INF/container.xml, designmap.xml,
Resources/{Graphic,Fonts,Styles,Preferences}.xml, MasterSpreads/, Spreads/,
Stories/, XML/{BackingStory,Tags}.xml.

The lesson is built to exercise what Kartouche handles: headings, body text
with bold/italic runs mid-sentence, a bulleted and a numbered list, a table,
two callout boxes, one story threaded across two frames on two pages, a
master-page footer with an automatic page number, and three linked images.

The fonts are Arial (on every Mac and Windows machine), so the sample opens
cleanly in InDesign. Kartouche measures it with Liberation Sans, which has
the same metrics as Arial.

Output is deterministic (fixed zip timestamps, no randomness), so
re-running the script produces byte-identical files.
"""

import io
import struct
import zipfile
import zlib
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "fractions_lesson"
IDML_NAME = "fractions_lesson.idml"
ZIP_PATH = HERE / "fractions_lesson.zip"

DOM = "16.0"
PKG_NS = "http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging"
XML_DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
FIXED_DATE = (2026, 1, 1, 0, 0, 0)

PAGE_W, PAGE_H = 612.0, 792.0  # US Letter, points
IMAGE_DPI = 300  # PNGs are rendered so they place at 100% scale

# Colours (CMYK, 0-100)
COLORS = {
    "Lesson Blue": (85, 45, 0, 10),
    "Lesson Blue Tint": (12, 4, 0, 0),
    "Callout Yellow": (0, 6, 30, 0),
    "Ink": (0, 0, 0, 90),
}
# Same colours in RGB for the generated images
RGB = {
    "blue": (31, 97, 168),
    "blue_tint": (220, 233, 247),
    "ink": (40, 44, 52),
    "grid": (150, 160, 175),
    "white": (255, 255, 255),
    "orange": (226, 120, 40),
}


# ---------------------------------------------------------------- ids

class Ids:
    """Deterministic unique Self ids in InDesign's 'u<hex>' style."""

    def __init__(self, start=0x100):
        self.n = start

    def __call__(self):
        self.n += 1
        return f"u{self.n:x}"


new_id = Ids()


# ---------------------------------------------------------------- stories
#
# A story is a list of paragraphs. A paragraph is (paragraph_style, runs,
# extra_attrs). A run is (character_style, text). Character styles:
#   None -> [No character style], "Bold", "Italic", "Number" (blue, bold)
# A paragraph may instead be ("__table__", table_spec, {}).

def P(style, *runs, **attrs):
    norm = []
    for r in runs:
        norm.append((None, r) if isinstance(r, str) else r)
    return (style, norm, attrs)


B = lambda t: ("Bold", t)
I = lambda t: ("Italic", t)
N = lambda t: ("Number", t)

TABLE = {
    "columns": [92, 104, 100, 220],
    "header": ["Start with", "Multiply by", "Equivalent", "In words"],
    "rows": [
        ["1/2", "2/2", "2/4", "One half is the same as two fourths."],
        ["1/3", "3/3", "3/9", "One third is the same as three ninths."],
        ["3/4", "2/2", "6/8", "Three fourths is the same as six eighths."],
        ["2/5", "4/4", "8/20", "Two fifths is the same as eight twentieths."],
    ],
}

STORIES = {
    "kicker": [P("Kicker", "Grade 4 Math  ·  Fractions Unit  ·  Lesson 7")],
    "title": [P("Title", "Equivalent Fractions")],
    "body": [
        P("Body",
          "Imagine you and a friend each have a sandwich of the same size. You cut yours into ",
          B("2 equal parts"), " and eat one part. Your friend cuts theirs into ",
          B("4 equal parts"), " and eats two of them. Who ate more?"),
        P("Body",
          "Neither of you! You both ate ", I("half"),
          " of a sandwich. Fractions that name the same amount are called ",
          B("equivalent fractions"), "."),
        P("Heading", "In this lesson you will:"),
        P("Bullet", "Use fraction bars to see when two fractions are equal."),
        P("Bullet", "Find equivalent fractions by ", B("multiplying"),
          " the numerator and the denominator by the same number."),
        P("Bullet", "Explain your thinking with words, pictures and numbers."),
        P("Heading", "Finding equivalent fractions", StartParagraph="NextFrame"),
        P("Body",
          "To make an equivalent fraction, multiply the top number and the bottom number by the ",
          I("same"), " number. The fraction looks different, but its value does not change."),
        P("Body", "Look for the pattern in the table below."),
        ("__table__", TABLE, {}),
        P("Body",
          "You can also check your work on a ", B("number line"),
          ". Equivalent fractions always land on exactly the same point."),
    ],
    "remember": [
        P("Callout Head", "Remember"),
        P("Callout Body", "The ", B("numerator"),
          " is the top number. It tells how many parts you have."),
        P("Callout Body", "The ", B("denominator"),
          " is the bottom number. It tells how many equal parts make one whole."),
    ],
    "caption1": [
        P("Caption", B("Figure 1."), " Three fraction bars. The shaded parts are the same size."),
    ],
    "caption2": [
        P("Caption", B("Figure 2."), " The fractions ", N("1/2"), ", ", N("2/4"), " and ",
          N("4/8"), " all sit on the same point of the number line."),
    ],
    "practice": [
        P("Title Small", "Practice"),
        P("Body", "Answer each question. Show your work with a ", I("picture"),
          " or a ", I("number sentence"), "."),
        P("Numbered", "Shade a fraction bar to show ", N("2/3"),
          ". Then shade a second bar to show ", N("4/6"), ". What do you notice?"),
        P("Numbered", "Write a fraction that is equivalent to ", N("3/5"), "."),
        P("Numbered", "Maya says that ", N("2/6"), " and ", N("1/3"),
          " are equivalent. Is she right? Explain how you know."),
        P("Numbered", "Draw a number line from ", N("0"), " to ", N("1"),
          ". Mark ", N("1/2"), " and one other fraction that is equal to it."),
    ],
    "challenge": [
        P("Callout Head", "Challenge"),
        P("Callout Body", "Find ", B("three"), " fractions that are equivalent to ",
          N("2/3"), ". Use the pattern from the table to help you."),
        P("Callout Body", I("Hint:"), " multiply by 2, then by 3, then by 4."),
    ],
    "footer": [P("Footer", "Grade 4 Math  ·  Equivalent Fractions  ·  Page ", ("__pagenum__", ""))],
}

STORY_IDS = {name: new_id() for name in STORIES}


def char_style_ref(name):
    return "CharacterStyle/$ID/[No character style]" if name is None else f"CharacterStyle/{name}"


def render_runs(runs, last):
    out = []
    for i, (cstyle, text) in enumerate(runs):
        is_last = last and i == len(runs) - 1
        if cstyle == "__pagenum__":
            out.append('<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/$ID/[No character style]">'
                       '<Content><?ACE 18?></Content>'
                       + ("" if is_last else "") + '</CharacterStyleRange>')
            continue
        br = "" if not (i == len(runs) - 1 and not last) else "<Br/>"
        out.append(f'<CharacterStyleRange AppliedCharacterStyle="{char_style_ref(cstyle)}">'
                   f'<Content>{escape(text)}</Content>{br}</CharacterStyleRange>')
    return "".join(out)


def render_table(spec):
    tid = new_id()
    cols = spec["columns"]
    rows = [spec["header"]] + spec["rows"]
    parts = [f'<Table Self="{tid}" HeaderRowCount="1" FooterRowCount="0" BodyRowCount="{len(rows) - 1}" '
             f'ColumnCount="{len(cols)}" AppliedTableStyle="TableStyle/$ID/[Basic Table]" '
             f'TableDirection="LeftToRightDirection">']
    for r in range(len(rows)):
        parts.append(f'<Row Self="{tid}Row{r}" Name="{r}" SingleRowHeight="24" MinimumHeight="20" AutoGrow="true"/>')
    for c, w in enumerate(cols):
        parts.append(f'<Column Self="{tid}Column{c}" Name="{c}" SingleColumnWidth="{w}"/>')
    # IDML cell names are "column:row"; cells are written row by row.
    k = 0
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            header = r == 0
            pstyle = "Table Head" if header else ("Table Body" if c == 3 else "Table Number")
            cstyle = None if header or c == 3 else "Number"
            fill = "Color/Lesson Blue" if header else ("Color/Lesson Blue Tint" if r % 2 == 0 else "Color/Paper")
            parts.append(
                f'<Cell Self="{tid}i{k}" Name="{c}:{r}" RowSpan="1" ColumnSpan="1" '
                f'AppliedCellStyle="CellStyle/$ID/[None]" AppliedCellStylePriority="0" FillColor="{fill}" '
                f'TopInset="4" BottomInset="4" LeftInset="5" RightInset="5" VerticalJustification="CenterAlign">'
                f'<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/{pstyle}">'
                f'<CharacterStyleRange AppliedCharacterStyle="{char_style_ref(cstyle)}">'
                f'<Content>{escape(text)}</Content></CharacterStyleRange></ParagraphStyleRange></Cell>')
            k += 1
    parts.append("</Table>")
    return "".join(parts)


def render_story(story_id, paragraphs):
    body = []
    for i, (pstyle, runs, attrs) in enumerate(paragraphs):
        last = i == len(paragraphs) - 1
        if pstyle == "__table__":
            body.append('<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/Body">'
                        '<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/$ID/[No character style]">'
                        + render_table(runs) + ("" if last else "<Br/>")
                        + '</CharacterStyleRange></ParagraphStyleRange>')
            continue
        extra = "".join(f' {k}={quoteattr(v)}' for k, v in attrs.items())
        body.append(f'<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/{pstyle}"{extra}>'
                    + render_runs(runs, last) + '</ParagraphStyleRange>')
    return (XML_DECL +
            f'<idPkg:Story xmlns:idPkg="{PKG_NS}" DOMVersion="{DOM}">'
            f'<Story Self="{story_id}" AppliedTOCStyle="n" UserText="true" IsEndnoteStory="false" '
            f'TrackChanges="false" StoryTitle="$ID/" AppliedNamedGrid="n">'
            f'<StoryPreference OpticalMarginAlignment="false" OpticalMarginSize="12" FrameType="TextFrameType" '
            f'StoryOrientation="Horizontal" StoryDirection="LeftToRightDirection"/>'
            f'<InCopyExportOption IncludeGraphicProxies="true" IncludeAllResources="false"/>'
            + "".join(body) +
            '</Story></idPkg:Story>\n')


# ---------------------------------------------------------------- styles

PARA_STYLES = {
    # name: (font_style, point_size, leading, extra attrs, color)
    "Kicker": ("Bold", 9.5, 12, {"Tracking": "40", "Capitalization": "AllCaps"}, "Lesson Blue"),
    "Title": ("Bold", 28, 32, {}, "Ink"),
    "Title Small": ("Bold", 22, 26, {"SpaceAfter": "6"}, "Ink"),
    "Heading": ("Bold", 14, 18, {"SpaceBefore": "8", "SpaceAfter": "4"}, "Lesson Blue"),
    "Body": ("Regular", 11, 15, {"SpaceAfter": "7"}, "Ink"),
    "Bullet": ("Regular", 11, 15, {"SpaceAfter": "4", "LeftIndent": "18", "FirstLineIndent": "-12",
                                   "BulletsAndNumberingListType": "BulletList"}, "Ink"),
    "Numbered": ("Regular", 11, 15, {"SpaceAfter": "8", "LeftIndent": "20", "FirstLineIndent": "-20",
                                     "BulletsAndNumberingListType": "NumberedList"}, "Ink"),
    "Callout Head": ("Bold", 13, 16, {"SpaceAfter": "4"}, "Lesson Blue"),
    "Callout Body": ("Regular", 10, 13.5, {"SpaceAfter": "5"}, "Ink"),
    "Caption": ("Italic", 9, 12, {}, "Ink"),
    "Table Head": ("Bold", 9.5, 12, {}, "Paper"),
    "Table Number": ("Regular", 10, 12, {"Justification": "CenterAlign"}, "Ink"),
    "Table Body": ("Regular", 9.5, 12, {}, "Ink"),
    "Footer": ("Regular", 8, 10, {}, "Ink"),
}

CHAR_STYLES = {
    "Bold": {"FontStyle": "Bold"},
    "Italic": {"FontStyle": "Italic"},
    "Number": {"FontStyle": "Bold", "FillColor": "Color/Lesson Blue"},
}


def styles_xml():
    cs = ['<CharacterStyle Self="CharacterStyle/$ID/[No character style]" Imported="false" '
          'SplitDocument="false" EmitCss="true" StyleUniqueId="$ID/" IncludeClass="true" '
          'Name="$ID/[No character style]"/>']
    for name, attrs in CHAR_STYLES.items():
        a = "".join(f' {k}="{v}"' for k, v in attrs.items())
        cs.append(f'<CharacterStyle Self="CharacterStyle/{name}" Imported="false" KeyboardShortcut="0 0" '
                  f'Name="{name}"{a}><Properties><BasedOn type="string">$ID/[No character style]</BasedOn>'
                  f'<PreviewColor type="enumeration">Nothing</PreviewColor></Properties></CharacterStyle>')

    ps = ['<ParagraphStyle Self="ParagraphStyle/$ID/[No paragraph style]" Name="$ID/[No paragraph style]" '
          'Imported="false" NextStyle="ParagraphStyle/$ID/[No paragraph style]" KeyboardShortcut="0 0" '
          'FontStyle="Regular" PointSize="11" FillColor="Color/Black" Hyphenation="true" '
          'ParagraphDirection="LeftToRightDirection" Composer="HL Composer">'
          '<Properties><Leading type="unit">14</Leading><AppliedFont type="string">Arial</AppliedFont>'
          '<AppliedLanguage type="string">$ID/English: USA</AppliedLanguage></Properties></ParagraphStyle>',
          '<ParagraphStyle Self="ParagraphStyle/$ID/NormalParagraphStyle" Name="$ID/NormalParagraphStyle" '
          'Imported="false" NextStyle="ParagraphStyle/$ID/NormalParagraphStyle" KeyboardShortcut="0 0">'
          '<Properties><BasedOn type="string">$ID/[No paragraph style]</BasedOn>'
          '<PreviewColor type="enumeration">Nothing</PreviewColor></Properties></ParagraphStyle>']
    for name, (fstyle, size, leading, extra, color) in PARA_STYLES.items():
        a = "".join(f' {k}="{v}"' for k, v in extra.items())
        bullet = ""
        if extra.get("BulletsAndNumberingListType") == "BulletList":
            bullet = ('<BulletChar BulletCharacterType="UnicodeOnly" BulletCharacterValue="8226"/>'
                      '<BulletsFont type="string">$ID/</BulletsFont>')
        elif extra.get("BulletsAndNumberingListType") == "NumberedList":
            bullet = '<NumberingExpression type="string">^#.^t</NumberingExpression>'
        ps.append(f'<ParagraphStyle Self="ParagraphStyle/{name}" Name="{name}" Imported="false" '
                  f'NextStyle="ParagraphStyle/{name}" KeyboardShortcut="0 0" FontStyle="{fstyle}" '
                  f'PointSize="{size:g}" FillColor="Color/{color}"{a}>'
                  f'<Properties><BasedOn type="object">ParagraphStyle/$ID/NormalParagraphStyle</BasedOn>'
                  f'<Leading type="unit">{leading:g}</Leading><AppliedFont type="string">Arial</AppliedFont>'
                  f'{bullet}<PreviewColor type="enumeration">Nothing</PreviewColor></Properties></ParagraphStyle>')

    return (XML_DECL +
            f'<idPkg:Styles xmlns:idPkg="{PKG_NS}" DOMVersion="{DOM}">'
            f'<RootCharacterStyleGroup Self="{new_id()}">' + "".join(cs) + '</RootCharacterStyleGroup>'
            f'<RootParagraphStyleGroup Self="{new_id()}">' + "".join(ps) + '</RootParagraphStyleGroup>'
            f'<RootCellStyleGroup Self="{new_id()}"><CellStyle Self="CellStyle/$ID/[None]" '
            'AppliedParagraphStyle="ParagraphStyle/$ID/[No paragraph style]" Name="$ID/[None]"/></RootCellStyleGroup>'
            f'<RootTableStyleGroup Self="{new_id()}">'
            '<TableStyle Self="TableStyle/$ID/[No table style]" Name="$ID/[No table style]"/>'
            '<TableStyle Self="TableStyle/$ID/[Basic Table]" Name="$ID/[Basic Table]">'
            '<Properties><BasedOn type="string">$ID/[No table style]</BasedOn></Properties></TableStyle>'
            '</RootTableStyleGroup>'
            f'<RootObjectStyleGroup Self="{new_id()}">'
            '<ObjectStyle Self="ObjectStyle/$ID/[None]" Name="$ID/[None]"/>'
            '<ObjectStyle Self="ObjectStyle/$ID/[Normal Graphics Frame]" Name="$ID/[Normal Graphics Frame]">'
            '<Properties><BasedOn type="string">$ID/[None]</BasedOn></Properties></ObjectStyle>'
            '<ObjectStyle Self="ObjectStyle/$ID/[Normal Text Frame]" Name="$ID/[Normal Text Frame]">'
            '<Properties><BasedOn type="string">$ID/[None]</BasedOn></Properties></ObjectStyle>'
            '<ObjectStyle Self="ObjectStyle/$ID/[Normal Grid]" Name="$ID/[Normal Grid]">'
            '<Properties><BasedOn type="string">$ID/[None]</BasedOn></Properties></ObjectStyle>'
            '</RootObjectStyleGroup>'
            '</idPkg:Styles>\n')


def graphic_xml():
    colors = [
        '<Color Self="Color/Black" Model="Process" Space="CMYK" ColorValue="0 0 0 100" ColorOverride="Specialblack" '
        'AlternateSpace="NoAlternateColor" AlternateColorValue="" Name="Black" ColorEditable="false" '
        'ColorRemovable="false" Visible="true" SwatchCreatorID="7937"/>',
        '<Color Self="Color/Paper" Model="Process" Space="CMYK" ColorValue="0 0 0 0" ColorOverride="Specialpaper" '
        'AlternateSpace="NoAlternateColor" AlternateColorValue="" Name="Paper" ColorEditable="true" '
        'ColorRemovable="false" Visible="true" SwatchCreatorID="7937"/>',
        '<Color Self="Color/Registration" Model="Registration" Space="CMYK" ColorValue="100 100 100 100" '
        'ColorOverride="Specialregistration" AlternateSpace="NoAlternateColor" AlternateColorValue="" '
        'Name="Registration" ColorEditable="false" ColorRemovable="false" Visible="true" SwatchCreatorID="7937"/>',
    ]
    for name, (c, m, y, k) in COLORS.items():
        colors.append(f'<Color Self="Color/{name}" Model="Process" Space="CMYK" ColorValue="{c} {m} {y} {k}" '
                      f'ColorOverride="Normal" AlternateSpace="NoAlternateColor" AlternateColorValue="" '
                      f'Name="{name}" ColorEditable="true" ColorRemovable="true" Visible="true" '
                      f'SwatchCreatorID="7937"/>')
    return (XML_DECL +
            f'<idPkg:Graphic xmlns:idPkg="{PKG_NS}" DOMVersion="{DOM}">' + "".join(colors) +
            '<Ink Self="Ink/$ID/Process Cyan" Name="$ID/Process Cyan" Angle="75" ConvertToProcess="false" '
            'Frequency="70" NeutralDensity="0.61" PrintInk="true" TrapOrder="1" InkType="Normal"/>'
            '<Ink Self="Ink/$ID/Process Magenta" Name="$ID/Process Magenta" Angle="15" ConvertToProcess="false" '
            'Frequency="70" NeutralDensity="0.76" PrintInk="true" TrapOrder="2" InkType="Normal"/>'
            '<Ink Self="Ink/$ID/Process Yellow" Name="$ID/Process Yellow" Angle="0" ConvertToProcess="false" '
            'Frequency="70" NeutralDensity="0.16" PrintInk="true" TrapOrder="3" InkType="Normal"/>'
            '<Ink Self="Ink/$ID/Process Black" Name="$ID/Process Black" Angle="45" ConvertToProcess="false" '
            'Frequency="70" NeutralDensity="1.7" PrintInk="true" TrapOrder="4" InkType="Normal"/>'
            '<Swatch Self="Swatch/None" Name="None" ColorEditable="false" ColorRemovable="false" Visible="true" '
            'SwatchCreatorID="7937"/>'
            '<StrokeStyle Self="StrokeStyle/$ID/Solid" Name="$ID/Solid"/>'
            '</idPkg:Graphic>\n')


def fonts_xml():
    fonts = []
    fam = new_id()
    for style, ps in (("Regular", "ArialMT"), ("Bold", "Arial-BoldMT"),
                      ("Italic", "Arial-ItalicMT"), ("Bold Italic", "Arial-BoldItalicMT")):
        fonts.append(f'<Font Self="{fam}Fontn{escape("Arial " + style)}" FontFamily="Arial" Name="Arial {style}" '
                     f'PostScriptName="{ps}" Status="Installed" FontStyleName="{style}" FontType="TrueType" '
                     f'WritingScript="0" FullName="Arial {style}" FullNameNative="Arial {style}" '
                     f'FontStyleNameNative="{style}" PlatformName="$ID/" Version="$ID/" TypekitID="$ID/"/>')
    return (XML_DECL +
            f'<idPkg:Fonts xmlns:idPkg="{PKG_NS}" DOMVersion="{DOM}">'
            f'<FontFamily Self="{fam}" Name="Arial">' + "".join(fonts) + '</FontFamily>'
            '</idPkg:Fonts>\n')


def preferences_xml():
    return (XML_DECL +
            f'<idPkg:Preferences xmlns:idPkg="{PKG_NS}" DOMVersion="{DOM}">'
            f'<DocumentPreference PageHeight="{PAGE_H:g}" PageWidth="{PAGE_W:g}" PagesPerDocument="3" '
            'FacingPages="false" DocumentBleedTopOffset="0" DocumentBleedBottomOffset="0" '
            'DocumentBleedInsideOrLeftOffset="0" DocumentBleedOutsideOrRightOffset="0" '
            'DocumentBleedUniformSize="true" SlugTopOffset="0" SlugBottomOffset="0" '
            'SlugInsideOrLeftOffset="0" SlugRightOrOutsideOffset="0" DocumentSlugUniformSize="false" '
            'PreserveLayoutWhenShuffling="true" AllowPageShuffle="true" OverprintBlack="true" '
            'PageBinding="LeftToRight" ColumnDirection="Horizontal" Intent="PrintIntent"/>'
            '<MarginPreference ColumnCount="1" ColumnGutter="12" Top="48" Bottom="48" Left="48" Right="48" '
            'ColumnDirection="Horizontal" ColumnsPositions="0 516"/>'
            '<TextFramePreference TextColumnCount="1" TextColumnGutter="12" UseFixedColumnWidth="false" '
            'FirstBaselineOffset="AscentOffset" VerticalJustification="TopAlign"/>'
            '<StoryPreference OpticalMarginAlignment="false" OpticalMarginSize="12" FrameType="TextFrameType" '
            'StoryOrientation="Horizontal" StoryDirection="LeftToRightDirection"/>'
            '<ViewPreference HorizontalMeasurementUnits="Points" VerticalMeasurementUnits="Points"/>'
            '</idPkg:Preferences>\n')


# ---------------------------------------------------------------- geometry

def to_spread(x, y):
    """Page coordinates (origin top-left of the page) -> spread coordinates
    (origin at the centre of a single-page spread)."""
    return x - PAGE_W / 2, y - PAGE_H / 2


def path_geometry(x1, y1, x2, y2):
    pts = []
    for (px, py) in ((x1, y1), (x1, y2), (x2, y2), (x2, y1)):
        sx, sy = to_spread(px, py)
        a = f"{sx:g} {sy:g}"
        pts.append(f'<PathPointType Anchor="{a}" LeftDirection="{a}" RightDirection="{a}"/>')
    return ('<Properties><PathGeometry><GeometryPathType PathOpen="false"><PathPointArray>'
            + "".join(pts) + '</PathPointArray></GeometryPathType></PathGeometry></Properties>')


def text_frame(story, box, prev="n", nxt="n", self_id=None, fill="Swatch/None", stroke="Swatch/None",
               stroke_weight=0, inset=0, layer=None):
    x1, y1, x2, y2 = box
    fid = self_id or new_id()
    usable = (x2 - x1) - 2 * inset
    insets = "".join(f'<ListItem type="unit">{inset:g}</ListItem>' for _ in range(4))
    return (f'<TextFrame Self="{fid}" ParentStory="{STORY_IDS[story]}" PreviousTextFrame="{prev}" '
            f'NextTextFrame="{nxt}" ContentType="TextType" ItemLayer="{layer}" Visible="true" Locked="false" '
            f'AppliedObjectStyle="ObjectStyle/$ID/[Normal Text Frame]" FillColor="{fill}" '
            f'StrokeColor="{stroke}" StrokeWeight="{stroke_weight:g}" ItemTransform="1 0 0 1 0 0">'
            + path_geometry(x1, y1, x2, y2) +
            f'<TextFramePreference TextColumnCount="1" TextColumnGutter="12" TextColumnFixedWidth="{usable:g}" '
            f'UseFixedColumnWidth="false" FirstBaselineOffset="AscentOffset" VerticalJustification="TopAlign">'
            f'<Properties><InsetSpacing type="list">{insets}</InsetSpacing></Properties></TextFramePreference>'
            '</TextFrame>'), fid


def image_frame(box, link_name, px_size, layer):
    x1, y1, x2, y2 = box
    w_pt = px_size[0] * 72 / IMAGE_DPI
    h_pt = px_size[1] * 72 / IMAGE_DPI
    sx, sy = to_spread(x1, y1)
    size = (OUT_DIR / "Links" / link_name).stat().st_size
    return (f'<Rectangle Self="{new_id()}" ContentType="GraphicType" ItemLayer="{layer}" Visible="true" '
            f'Locked="false" StrokeWeight="0" FillColor="Swatch/None" StrokeColor="Swatch/None" '
            f'AppliedObjectStyle="ObjectStyle/$ID/[Normal Graphics Frame]" ItemTransform="1 0 0 1 0 0">'
            + path_geometry(x1, y1, x2, y2) +
            f'<Image Self="{new_id()}" Space="$ID/#Links_RGB" ActualPpi="{IMAGE_DPI} {IMAGE_DPI}" '
            f'EffectivePpi="{IMAGE_DPI} {IMAGE_DPI}" ImageRenderingIntent="UseColorSettings" '
            f'ImageTypeName="$ID/Portable Network Graphics (PNG)" Visible="true" '
            f'ItemTransform="1 0 0 1 {sx:g} {sy:g}">'
            f'<Properties><Profile type="string">$ID/None</Profile>'
            f'<GraphicBounds Left="0" Top="0" Right="{w_pt:g}" Bottom="{h_pt:g}"/></Properties>'
            f'<Link Self="{new_id()}" AssetURL="$ID/" AssetID="$ID/" LinkResourceURI="file:Links/{link_name}" '
            f'LinkResourceFormat="$ID/Portable Network Graphics (PNG)" StoredState="Normal" LinkClassID="35906" '
            f'LinkClientID="257" LinkResourceModified="false" LinkObjectModified="false" ShowInUI="true" '
            f'CanEmbed="true" CanUnembed="true" CanPackage="true" ImportPolicy="NoAutoImport" '
            f'ExportPolicy="NoAutoExport" LinkImportStamp="file 0 0" '
            f'LinkImportModificationTime="2026-01-01T00:00:00" LinkImportTime="2026-01-01T00:00:00" '
            f'LinkResourceSize="0~{size:x}"/>'
            '</Image></Rectangle>')


def page_elem(page_self, name, master):
    sx, sy = to_spread(0, 0)
    return (f'<Page Self="{page_self}" Name="{name}" AppliedTrapPreset="TrapPreset/$ID/kDefaultTrapStyleName" '
            f'AppliedMaster="{master}" OverrideList="" TabOrder="" GridStartingPoint="TopOutside" '
            f'UseMasterGrid="true" GeometricBounds="0 0 {PAGE_H:g} {PAGE_W:g}" '
            f'ItemTransform="1 0 0 1 {sx:g} {sy:g}" MasterPageTransform="1 0 0 1 0 0">'
            '<Properties><PageColor type="enumeration">UseMasterColor</PageColor></Properties>'
            '<MarginPreference ColumnCount="1" ColumnGutter="12" Top="48" Bottom="48" Left="48" Right="48" '
            'ColumnDirection="Horizontal" ColumnsPositions="0 516"/></Page>')


def spread_xml(spread_self, page_xml, items_xml):
    return (XML_DECL +
            f'<idPkg:Spread xmlns:idPkg="{PKG_NS}" DOMVersion="{DOM}">'
            f'<Spread Self="{spread_self}" PageTransitionType="None" PageTransitionDirection="NotApplicable" '
            f'PageTransitionDuration="Medium" ShowMasterItems="true" PageCount="1" BindingLocation="0" '
            f'AllowPageShuffle="true" ItemTransform="1 0 0 1 0 0" FlattenerOverride="Default">'
            '<FlattenerPreference LineArtAndTextResolution="300" GradientAndMeshResolution="150" '
            'ClipComplexRegions="false" ConvertAllStrokesToOutlines="false" ConvertAllTextToOutlines="false"/>'
            + page_xml + items_xml +
            '</Spread></idPkg:Spread>\n')


# ---------------------------------------------------------------- images (stdlib PNG writer)

class Canvas:
    """A tiny RGB raster with just enough drawing to make lesson art."""

    def __init__(self, w, h, bg=RGB["white"]):
        self.w, self.h = w, h
        self.px = bytearray(bytes(bg) * (w * h))

    def rect(self, x1, y1, x2, y2, color):
        x1, x2 = max(0, int(x1)), min(self.w, int(x2))
        y1, y2 = max(0, int(y1)), min(self.h, int(y2))
        row = bytes(color) * (x2 - x1)
        for y in range(y1, y2):
            i = (y * self.w + x1) * 3
            self.px[i:i + len(row)] = row

    def outline(self, x1, y1, x2, y2, color, t):
        self.rect(x1, y1, x2, y1 + t, color)
        self.rect(x1, y2 - t, x2, y2, color)
        self.rect(x1, y1, x1 + t, y2, color)
        self.rect(x2 - t, y1, x2, y2, color)

    def disc(self, cx, cy, r, color, shade_fn=None):
        """Filled circle; shade_fn(dx, dy) -> colour or None lets callers draw sectors."""
        for y in range(max(0, int(cy - r)), min(self.h, int(cy + r) + 1)):
            for x in range(max(0, int(cx - r)), min(self.w, int(cx + r) + 1)):
                dx, dy = x - cx, y - cy
                if dx * dx + dy * dy <= r * r:
                    c = shade_fn(dx, dy) if shade_fn else color
                    if c is not None:
                        i = (y * self.w + x) * 3
                        self.px[i:i + 3] = bytes(c)

    def png(self, dpi=IMAGE_DPI):
        raw = b"".join(b"\x00" + bytes(self.px[y * self.w * 3:(y + 1) * self.w * 3]) for y in range(self.h))

        def chunk(tag, data):
            return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

        ppm = round(dpi / 0.0254)
        return (b"\x89PNG\r\n\x1a\n"
                + chunk(b"IHDR", struct.pack(">IIBBBBB", self.w, self.h, 8, 2, 0, 0, 0))
                + chunk(b"pHYs", struct.pack(">IIB", ppm, ppm, 1))
                + chunk(b"IDAT", zlib.compress(raw, 9))
                + chunk(b"IEND", b""))


def px(pt):
    return round(pt * IMAGE_DPI / 72)


def draw_fraction_bars(w_pt, h_pt):
    """Three bars split into 2, 4 and 8 equal parts with half of each shaded."""
    c = Canvas(px(w_pt), px(h_pt))
    pad = px(4)
    gap = px(8)
    bar_h = (c.h - 2 * pad - 2 * gap) // 3
    t = px(1.2)
    for i, parts in enumerate((2, 4, 8)):
        y1 = pad + i * (bar_h + gap)
        x1, x2 = pad, c.w - pad
        seg = (x2 - x1) / parts
        for k in range(parts):
            sx1 = x1 + k * seg
            col = RGB["blue"] if k < parts // 2 else RGB["blue_tint"]
            c.rect(sx1, y1, sx1 + seg, y1 + bar_h, col)
            c.outline(sx1, y1, sx1 + seg + t, y1 + bar_h, RGB["ink"], t)
    return c


def draw_number_line(w_pt, h_pt):
    """A 0-to-1 number line with ticks at halves, fourths and eighths and a dot at one half."""
    c = Canvas(px(w_pt), px(h_pt))
    pad = px(16)
    y = c.h // 2
    x1, x2 = pad, c.w - pad
    c.rect(x1, y - px(1), x2, y + px(1), RGB["ink"])
    for k in range(9):
        x = x1 + (x2 - x1) * k / 8
        tall = px(16) if k in (0, 8) else (px(12) if k % 4 == 0 else (px(9) if k % 2 == 0 else px(6)))
        c.rect(x - px(0.8), y - tall, x + px(0.8), y + tall, RGB["ink"])
    # three rows of coloured arcs-as-bars above the line show 1/2, 2/4, 4/8 landing together
    for row, parts in enumerate((2, 4, 8)):
        yy = y - px(22) - row * px(9)
        for k in range(parts // 2):
            sx1 = x1 + (x2 - x1) * k / parts
            sx2 = x1 + (x2 - x1) * (k + 1) / parts
            c.rect(sx1 + px(1.5), yy - px(2.5), sx2 - px(1.5), yy + px(2.5),
                   (RGB["blue"], RGB["orange"], RGB["grid"])[row])
    cx = x1 + (x2 - x1) / 2
    c.disc(cx, y, px(6), RGB["orange"])
    return c


def draw_fraction_circles(w_pt, h_pt):
    """Circles cut into 3, 6 and 9 equal sectors with one third of each shaded."""
    import math
    c = Canvas(px(w_pt), px(h_pt))
    n = 3
    r = min(c.w / (n * 2.3), c.h / 2.4)
    for i, parts in enumerate((3, 6, 9)):
        cx = c.w * (i + 0.5) / n
        cy = c.h / 2
        border = px(1.2)

        def shade(dx, dy, parts=parts, r=r, border=border):
            dist = math.hypot(dx, dy)
            if dist > r - border:
                return RGB["ink"]
            ang = (math.atan2(dy, dx) + math.pi / 2) % (2 * math.pi)
            sector = ang / (2 * math.pi) * parts
            frac = sector - int(sector)
            # sector boundaries drawn as thin spokes
            if min(frac, 1 - frac) * (2 * math.pi / parts) * dist < border * 0.8:
                return RGB["ink"]
            return RGB["blue"] if int(sector) < parts // 3 else RGB["blue_tint"]

        c.disc(cx, cy, r, None, shade)
    return c


# ---------------------------------------------------------------- assembly

def build():
    links = OUT_DIR / "Links"
    links.mkdir(parents=True, exist_ok=True)

    layer = new_id()
    master = new_id()

    # Page layout boxes (page coordinates, points): x1, y1, x2, y2
    L, R = 48, PAGE_W - 48
    boxes = {
        "kicker": (L, 48, R, 62),
        "title": (L, 66, L + 300, 102),
        "body_1": (L, 118, 372, 520),
        "remember": (392, 118, R, 330),
        "fig1": (L, 536, 372, 650),
        "caption1": (L, 656, 372, 684),
        "body_2": (L, 48, R, 520),
        "fig2": (L, 540, R, 620),
        "caption2": (L, 626, R, 656),
        "practice": (L, 48, R, 470),
        "challenge": (L, 500, 340, 700),
        "fig3": (360, 520, R, 680),
        "footer": (L, 752, R, 766),
    }

    art = {
        "fraction_bars.png": (draw_fraction_bars, boxes["fig1"]),
        "number_line.png": (draw_number_line, boxes["fig2"]),
        "fraction_circles.png": (draw_fraction_circles, boxes["fig3"]),
    }
    sizes = {}
    for name, (fn, (x1, y1, x2, y2)) in art.items():
        canvas = fn(x2 - x1, y2 - y1)
        (links / name).write_bytes(canvas.png())
        sizes[name] = (canvas.w, canvas.h)

    blue, yellow = "Color/Lesson Blue", "Color/Callout Yellow"
    body1_id, body2_id = new_id(), new_id()

    spreads = []
    pages = []
    # --- page 1
    items = []
    for story in ("kicker", "title"):
        items.append(text_frame(story, boxes[story], layer=layer)[0])
    items.append(text_frame("body", boxes["body_1"], nxt=body2_id, self_id=body1_id, layer=layer)[0])
    items.append(text_frame("remember", boxes["remember"], fill=yellow, stroke=blue, stroke_weight=1,
                            inset=10, layer=layer)[0])
    items.append(image_frame(boxes["fig1"], "fraction_bars.png", sizes["fraction_bars.png"], layer))
    items.append(text_frame("caption1", boxes["caption1"], layer=layer)[0])
    pages.append([items])
    # --- page 2
    items = [text_frame("body", boxes["body_2"], prev=body1_id, self_id=body2_id, layer=layer)[0],
             image_frame(boxes["fig2"], "number_line.png", sizes["number_line.png"], layer),
             text_frame("caption2", boxes["caption2"], layer=layer)[0]]
    pages.append([items])
    # --- page 3
    items = [text_frame("practice", boxes["practice"], layer=layer)[0],
             text_frame("challenge", boxes["challenge"], fill=yellow, stroke=blue, stroke_weight=1,
                        inset=10, layer=layer)[0],
             image_frame(boxes["fig3"], "fraction_circles.png", sizes["fraction_circles.png"], layer)]
    pages.append([items])

    files = {}
    page_ids = []
    for n, (items,) in enumerate(pages, start=1):
        sid, pid = new_id(), new_id()
        page_ids.append(pid)
        files[f"Spreads/Spread_{sid}.xml"] = spread_xml(sid, page_elem(pid, str(n), master), "".join(items))
        spreads.append(sid)

    # Master spread: footer with an automatic page number.
    mpage = new_id()
    footer_frame = text_frame("footer", boxes["footer"], layer=layer)[0]
    files[f"MasterSpreads/MasterSpread_{master}.xml"] = (
        XML_DECL + f'<idPkg:MasterSpread xmlns:idPkg="{PKG_NS}" DOMVersion="{DOM}">'
        f'<MasterSpread Self="{master}" ItemTransform="1 0 0 1 0 0" OverriddenPageItemProps="" '
        f'PrimaryTextFrame="n" Name="A-Master" NamePrefix="A" BaseName="Master" ShowMasterItems="true" '
        f'PageCount="1" PageColor="UseMasterColor">'
        + page_elem(mpage, "A", "n").replace(' AppliedMaster="n"', '') + footer_frame +
        '</MasterSpread></idPkg:MasterSpread>\n')

    for name, paragraphs in STORIES.items():
        files[f"Stories/Story_{STORY_IDS[name]}.xml"] = render_story(STORY_IDS[name], paragraphs)

    files["Resources/Graphic.xml"] = graphic_xml()
    files["Resources/Fonts.xml"] = fonts_xml()
    files["Resources/Styles.xml"] = styles_xml()
    files["Resources/Preferences.xml"] = preferences_xml()
    files["XML/Tags.xml"] = (XML_DECL + f'<idPkg:Tags xmlns:idPkg="{PKG_NS}" DOMVersion="{DOM}">'
                             '<XMLTag Self="XMLTag/Root" Name="Root"><Properties>'
                             '<TagColor type="enumeration">LightBlue</TagColor></Properties></XMLTag>'
                             '</idPkg:Tags>\n')
    files["XML/BackingStory.xml"] = (XML_DECL + f'<idPkg:BackingStory xmlns:idPkg="{PKG_NS}" DOMVersion="{DOM}">'
                                     f'<XmlStory Self="{new_id()}" UserText="true" IsEndnoteStory="false" '
                                     'AppliedTOCStyle="n" TrackChanges="false" StoryTitle="$ID/" AppliedNamedGrid="n">'
                                     '<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/$ID/NormalParagraphStyle">'
                                     '<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/$ID/[No character style]"/>'
                                     '</ParagraphStyleRange></XmlStory></idPkg:BackingStory>\n')
    files["META-INF/container.xml"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="designmap.xml" media-type="text/xml"/></rootfiles></container>\n')

    story_list = " ".join(STORY_IDS.values())
    designmap = (
        XML_DECL +
        f'<?aid style="50" type="document" readerVersion="6.0" featureSet="257" product="{DOM}(0)" ?>\n'
        f'<Document xmlns:idPkg="{PKG_NS}" DOMVersion="{DOM}" Self="d" StoryList="{story_list}" '
        f'Name="fractions_lesson.indd" ZeroPoint="0 0" ActiveLayer="{layer}" '
        f'CMYKProfile="U.S. Web Coated (SWOP) v2" RGBProfile="sRGB IEC61966-2.1" SolidColorIntent="UseColorSettings" '
        f'AfterBlendingIntent="UseColorSettings" DefaultImageIntent="UseColorSettings" '
        f'RGBPolicy="PreserveEmbeddedProfiles" CMYKPolicy="CombinationOfPreserveAndSafeCmyk" AccurateLABSpots="false">'
        '<idPkg:Graphic src="Resources/Graphic.xml"/>'
        '<idPkg:Fonts src="Resources/Fonts.xml"/>'
        '<idPkg:Styles src="Resources/Styles.xml"/>'
        '<idPkg:Preferences src="Resources/Preferences.xml"/>'
        '<idPkg:Tags src="XML/Tags.xml"/>'
        f'<Layer Self="{layer}" Name="Layer 1" Visible="true" Locked="false" IgnoreWrap="false" '
        'ShowGuides="true" LockGuides="false" UI="true" Expendable="true" Printable="true">'
        '<Properties><LayerColor type="enumeration">LightBlue</LayerColor></Properties></Layer>'
        f'<idPkg:MasterSpread src="MasterSpreads/MasterSpread_{master}.xml"/>'
        + "".join(f'<idPkg:Spread src="Spreads/Spread_{s}.xml"/>' for s in spreads) +
        f'<Section Self="{new_id()}" Length="3" Name="" ContinueNumbering="true" IncludeSectionPrefix="false" '
        f'PageNumberStyle="Arabic" PageStart="{page_ids[0]}" SectionPrefix=""/>'
        '<idPkg:BackingStory src="XML/BackingStory.xml"/>'
        + "".join(f'<idPkg:Story src="Stories/Story_{s}.xml"/>' for s in STORY_IDS.values()) +
        '</Document>\n')
    files["designmap.xml"] = designmap

    # --- write the .idml (mimetype first, stored)
    idml_path = OUT_DIR / IDML_NAME
    write_zip(idml_path, [("mimetype", b"application/vnd.adobe.indesign-idml-package", zipfile.ZIP_STORED)]
              + [(name, files[name].encode("utf-8"), zipfile.ZIP_DEFLATED) for name in sorted(files)])

    # --- the ready-to-upload bundle: folder with the .idml and its Links/
    bundle = [(f"fractions_lesson/{IDML_NAME}", idml_path.read_bytes(), zipfile.ZIP_DEFLATED)]
    for link in sorted(links.iterdir()):
        bundle.append((f"fractions_lesson/Links/{link.name}", link.read_bytes(), zipfile.ZIP_DEFLATED))
    write_zip(ZIP_PATH, bundle)
    return idml_path


def write_zip(path, entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data, method in entries:
            info = zipfile.ZipInfo(name, date_time=FIXED_DATE)
            info.compress_type = method
            info.external_attr = 0o644 << 16
            zf.writestr(info, data)
    path.write_bytes(buf.getvalue())


if __name__ == "__main__":
    out = build()
    print(f"Wrote {out.relative_to(HERE.parent)}")
    print(f"Wrote {ZIP_PATH.relative_to(HERE.parent)}")
