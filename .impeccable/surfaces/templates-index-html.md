---
version: 1
slug: "templates-index-html"
primary_target: "templates/index.html"
related_targets: ["templates/job.html","templates/missing.html","templates/base.html"]
---

# Rosetta web UI (home, job progress, results, error states)

Scope: every page the Flask app serves (templates/*.html, static/*). Home is Persuade (an evaluator decides to try it); the job and results screens are Operate (watch a run, check a translation, download). One visual world for all of them.

Audience and task: evaluators on a first visit, production/localization staff checking output repeatedly, InDesign designers finishing the layout. Action: try the sample or upload an .idml, then judge the result in the browser and download the InDesign package.

Constraints: Flask + Jinja + plain JS, strict CSP (no inline style or script), self-hosted open-licence fonts, Arabic-capable font for RTL, light and dark themes, WCAG AA, reduced motion, 375-1440px. JS hooks in the README's "Customising the UI" section must keep working. Only the synthetic sample lesson may appear; no invented claims.

## Direction contract

THESIS: Rosetta's output is a proof you check and sign off. Every screen is a press proof on the press table: the document sits on a sheet with crop marks and a slug line, and everything Rosetta changed or doubts is marked in the margin like a proofreader's pencil. It refuses the SaaS default: a gradient hero, a row of equal feature cards, and dashboard metric tiles.

OWN-WORLD: Neutral grey press-table ground, white proof sheets with corner crop marks, a CMYK control strip, a registration-target mark beside the Rosetta wordmark. Colour by process ink and job: K (ink black) for text and primary buttons, M-red pencil for "needs review" marks, C for measurements, links and fit fixes, Y highlighter behind flagged text. Archivo throughout: wide, heavy headlines; condensed caps for slug lines and labels; the document's own sans (Liberation/Arial) for document text in the preview.

STORY: The visitor sees the tool's actual output form (a marked proof) before reading a claim, learns that it translates the live text and fits it back into the frames, and acts: try the sample, or upload. On the job screens they watch the strip fill, then read the proof, check the marked items, and download.

FIRST VIEWPORT: Home at 1440: header (registration mark + wordmark, three links). One large proof sheet with crop marks and a slug line. Left two-thirds: wide black headline naming the category, a two-line lede, the solid "Try it with the sample lesson" button. Right third: the upload job ticket (dropzone, language chips, submit) as a ruled form on the same sheet. A CMYK control strip along the sheet's bottom edge. The next sheet's top edge is visible below.

FORM: Proof sheet; position 1 on my ordered list (the user chose it over the dealt direction, "measured specimen", position 4). seed:af788117b7f19538 (roll ran degraded: no challengers).

Signature interaction: progress is the CMYK control strip filling patch by patch, and each finished step gets a proofreader's tick drawn once. Motion grammar: crisp and short (press 160ms, ease-out), nothing on scroll, reduced motion keeps colour changes only.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
