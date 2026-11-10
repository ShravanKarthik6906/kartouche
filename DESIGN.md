---
name: Rosetta
description: A press proof for translated InDesign documents - sheets on a press table, marked like a proofreader would.
colors:
  press-table: "#d9dad6"
  proof-sheet: "#ffffff"
  sheet-sunk: "#f3f3f0"
  process-black: "#16171a"
  ink-secondary: "#393c43"
  ink-muted: "#5a5e66"
  rule: "#d6d8db"
  rule-strong: "#a9adb4"
  measure-cyan: "#005f99"
  measure-cyan-wash: "#e3f1fa"
  proof-pencil: "#b8102d"
  proof-pencil-wash: "#fcebee"
  highlighter: "#ffec8a"
  swatch-cyan: "#00a0de"
  swatch-magenta: "#e4007c"
  swatch-yellow: "#ffe000"
  dark-press-table: "#101113"
  dark-proof-sheet: "#1b1c20"
  dark-ink: "#eceef1"
  dark-measure-cyan: "#6cc3f2"
  dark-proof-pencil: "#ff7d8c"
typography:
  display:
    fontFamily: "Archivo, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "clamp(34px, 4.4vw, 62px)"
    fontWeight: 820
    lineHeight: 1
    letterSpacing: "-0.03em"
    fontVariation: "'wdth' 108"
  headline:
    fontFamily: "Archivo, sans-serif"
    fontSize: "clamp(22px, 2.2vw, 28px)"
    fontWeight: 800
    lineHeight: 1.12
    letterSpacing: "-0.02em"
    fontVariation: "'wdth' 110"
  title:
    fontFamily: "Archivo, sans-serif"
    fontSize: "19px"
    fontWeight: 800
    lineHeight: 1.12
  body:
    fontFamily: "Archivo, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: "Archivo, sans-serif"
    fontSize: "11px"
    fontWeight: 600
    letterSpacing: "0.07em"
    fontVariation: "'wdth' 78"
  document:
    fontFamily: "Arial, Liberation Sans, Helvetica, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.55
  arabic:
    fontFamily: "Noto Sans Arabic, Geeza Pro, Tahoma, sans-serif"
    fontSize: "15px"
    lineHeight: 1.8
rounded:
  sm: "3px"
  md: "5px"
  pill: "999px"
spacing:
  gutter: "clamp(16px, 3vw, 40px)"
  sheet-pad: "clamp(20px, 3.4vw, 48px)"
  sheet-gap: "44px"
  tap: "44px"
components:
  button-primary:
    backgroundColor: "{colors.process-black}"
    textColor: "{colors.proof-sheet}"
    rounded: "{rounded.md}"
    padding: "14px 26px"
    height: "54px"
  button-primary-hover:
    backgroundColor: "{colors.ink-secondary}"
    textColor: "{colors.proof-sheet}"
  button-secondary:
    backgroundColor: "{colors.proof-sheet}"
    textColor: "{colors.process-black}"
    rounded: "{rounded.md}"
    padding: "10px 20px"
    height: "44px"
  chip-language:
    backgroundColor: "{colors.proof-sheet}"
    textColor: "{colors.ink-secondary}"
    rounded: "{rounded.pill}"
    padding: "6px 14px"
    height: "40px"
  chip-language-selected:
    backgroundColor: "{colors.process-black}"
    textColor: "{colors.proof-sheet}"
    rounded: "{rounded.pill}"
  tab-selected:
    backgroundColor: "{colors.process-black}"
    textColor: "{colors.proof-sheet}"
    rounded: "{rounded.md}"
    padding: "8px 16px"
  dropzone:
    backgroundColor: "{colors.sheet-sunk}"
    textColor: "{colors.ink-secondary}"
    rounded: "{rounded.md}"
    padding: "18px"
---

# Design System: Rosetta

## Overview

**Creative North Star: "The Press Proof"**

Rosetta's output is a proof you check and sign off, so every screen is a press proof lying on the press table. Documents sit on white sheets with corner crop marks and a slug line; a CMYK control strip runs along the foot of the main sheet; whatever Rosetta changed or doubts is marked in the margin the way a proofreader marks a proof. The world is print-shop practical, not nostalgic: flat sheets, hairline rules, process inks used for their jobs, and one confident wide grotesque.

It refuses the generic SaaS template: no gradient hero, no row of equal icon cards, no dashboard metric tiles, no glow.

**Key Characteristics:**
- Sheets on a table: content lives on white (or, in dark mode, graphite) sheets with crop marks, never in nested cards.
- Ink by job: black for text and actions, cyan for measurement and automatic fixes, pencil red for anything a person must check, yellow highlighter behind flagged text.
- Slug lines in condensed caps carry file, page and status, as on a real proof.
- The document's own text is shown in the document's own sans; the interface speaks Archivo.

## Colors

The palette is restrained: neutral table and sheets, plus process-ink roles. Light and dark themes redefine the same tokens (see `static/styles.css`); dark values are listed in the frontmatter with a `dark-` prefix.

### Primary
- **Process Black** (process-black): body text, headings, primary buttons, selected chips and tabs. In dark mode it inverts to Dark Ink.

### Secondary
- **Measure Cyan** (measure-cyan): links, focus rings, measurements and automatic fit fixes ("Text size reduced 10% to fit"), the current-step caret.

### Tertiary
- **Proof Pencil** (proof-pencil): every "check this" mark, errors, rate-limit and paused notices, the error-sheet ring. Never decorative.
- **Highlighter** (highlighter): behind translated text a person must review, and as text selection.

### Neutral
- **Press Table** (press-table): the page ground every sheet lies on.
- **Proof Sheet** (proof-sheet) and **Sheet Sunk** (sheet-sunk): sheet surface; wells such as the dropzone and table heads.
- **Ink Secondary / Ink Muted**: supporting copy and labels; **Rule / Rule Strong**: hairlines and dashed outlines.
- **Control-strip swatches** (swatch-cyan, swatch-magenta, swatch-yellow, process-black) appear only in the control strip and the progress bar, never as text or UI colour.

**The Ink-by-Job Rule.** Each process colour has one job. Cyan never marks a problem, pencil red never decorates, and the swatch colours never leave the control strip.

**The Pencil Means a Person Rule.** If something is pencil red, a human has to look at it. Informational notes stay in ink.

## Typography

**Display / UI Font:** Archivo (variable weight and width, self-hosted WOFF2, SIL OFL)
**Document Font:** Arial / Liberation Sans, used only for document text in proofs
**Arabic Font:** Noto Sans Arabic (self-hosted WOFF2, SIL OFL)

Archivo's width axis does the expressive work: headlines are set wide and heavy, slug lines and field labels condensed and capitalised. Numerals are tabular everywhere.

### Hierarchy
- **Display** (820, wide 108%, clamp 34-62px, line-height 1.0): the one headline per page.
- **Headline** (800, wide 110%, 22-28px): section heads such as "Original and translation", error titles.
- **Title** (800, 19px): sheet titles such as "Translate your document", step names.
- **Body** (400, 16px, 1.55): copy, capped at about 62ch.
- **Label** (600, condensed 78%, 11px, caps, 0.07em): slug lines, field labels, column heads.
- **Document** (Arial 15px, 1.55): original and translated text inside proofs, so the preview reads like the document.

**The Document Speaks Its Own Font Rule.** Text that came from the user's document is shown in the document sans (or Noto Sans Arabic for Arabic), never in Archivo.

## Layout

One centred column (max 1280px, fluid gutter 16-40px). Sheets stack vertically with 44px between them, enough room for each sheet's crop marks. The home hero is one sheet split into the pitch (left, about 60%) and the upload job ticket (right), with the control strip along its foot; below 1080px the ticket stacks under the pitch. Proof rows are a three-column grid (English | translation | margin); below 900px the margin notes drop under the row, and below 640px each row stacks with small language labels. Status sheets pair the work (progress or error) with a ruled job-ticket column that stacks below on narrow screens. Every control is at least 44px tall.

**The Sheets-Don't-Nest Rule.** A sheet never contains another sheet. Related blocks inside a sheet are separated by rules, not boxes.

## Elevation & Depth

Flat. Sheets carry a single soft, offset shadow (1px contact plus an 8px/24px ambient) to read as paper lying on the table; nothing else is elevated. Depth inside a sheet comes from hairline rules (1px) and black rules (1.5px) that open tables and lists.

## Shapes

Small, practical radii: 3px for code and highlights, 5px for buttons, inputs, tabs and notes, full pills only for language chips. Sheets are square-cornered because paper is. Crop marks are 11px hairlines set 18px outside each corner.

## Components

### Buttons
Primary buttons are solid process black with white text (inverted in dark mode), 5px radius, 44-54px tall, bold Archivo; they darken slightly on hover and press to 97% scale in 160ms. Secondary buttons are outlined in ink. One primary action per zone.

### Chips (language toggles)
Pill toggles over real checkboxes. Unselected: white with a strong rule; selected: process black with a drawn tick. The native name sits beside the English name (Arabic set right to left in Noto Sans Arabic).

### Cards / Containers
There are no cards; there are sheets (see Layout). Notes inside sheets are ruled boxes: ink outline for information, pencil outline for warnings and errors, each with a small drawn icon.

### Inputs / Fields
The dropzone is a dashed well on Sheet Sunk that turns cyan on hover or drag and solid ink once a file is chosen; field labels are condensed caps; errors appear under their field in pencil red.

### Navigation
A bare header on the table: the registration-target mark and the Rosetta wordmark (Archivo, wide), and three text links with 44px targets.

### Control strip and progress
The CMYK control strip (100%, 50% and 25% tints of C, M, Y, K) runs along the foot of the main home sheet. On the job page the same strip is the progress bar: patches fill left to right as the job advances. Finished steps get a drawn tick once; the current step shows a cyan caret that pulses gently.

### Proof rows and margin marks
English and translation side by side in the document font. Fixes appear as cyan margin notes ("Text size reduced 10% to fit"); anything to review gets a yellow highlight on the translated text plus a pencil-red margin note; informational notes stay in ink. A legend beside the downloads explains the three kinds.

## Do's and Don'ts

### Do:
- **Do** put every new screen on sheets with crop marks and a slug line that says what the sheet is.
- **Do** use pencil red only for things a person must act on, and cyan only for measurements and automatic fixes.
- **Do** show document text in the document's font and Arabic right to left in Noto Sans Arabic.
- **Do** keep motion to press feedback, the progress strip and the one-time tick; respect reduced motion.
- **Do** define every new colour, size or duration as a token on `:root` and redefine it for dark mode.

### Don't:
- **Don't** nest sheets, or bring in cards, metric tiles, gradients, glass or glow; that is the SaaS template this product rejects.
- **Don't** add eyebrow labels above headings; slug lines carry facts, not taglines.
- **Don't** use the control-strip swatches as UI colours or text.
- **Don't** use spinners or decorative motion; progress is the strip.
- **Don't** add inline styles or inline scripts; the app's Content-Security-Policy forbids them.
