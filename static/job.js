// Job page: polls the job's status, then shows results and the marked proof.
// All document and translation text is inserted with textContent (never
// innerHTML), so it can't inject markup. Element IDs used here are the
// contract listed in the README ("Customising the UI").
(function () {
  "use strict";
  const root = document.getElementById("job");
  const jobId = root.dataset.jobId;
  const $ = (id) => document.getElementById(id);
  const SVG_NS = "http://www.w3.org/2000/svg";

  // Tiny element builder: h("div", {class: "x"}, "text", child, ...)
  function h(tag, attrs, ...children) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children.flat()) {
      if (c === null || c === undefined || c === false) continue;
      el.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return el;
  }

  // Small authored icons (one stroke weight, currentColor).
  const ICONS = {
    tick: "M4 10.5l4 4 8-9",
    caret: "M4 15l6-10 6 10",
    fit: "M3 8h10M3 8l3-3M3 8l3 3M13 8l-3-3M13 8l-3 3",
    review: "M8 3v6M8 12v.5",
    info: "M8 7v5M8 4.5v.5",
    pause: "M6 4v8M10 4v8",
  };
  function icon(name, size) {
    const s = document.createElementNS(SVG_NS, "svg");
    const box = (name === "tick" || name === "caret") ? "0 0 20 20" : "0 0 16 16";
    s.setAttribute("viewBox", box);
    s.setAttribute("width", size || 14);
    s.setAttribute("height", size || 14);
    s.setAttribute("aria-hidden", "true");
    if (name === "review" || name === "info") {
      const c = document.createElementNS(SVG_NS, "circle");
      c.setAttribute("cx", "8"); c.setAttribute("cy", "8"); c.setAttribute("r", "6.5");
      c.setAttribute("fill", "none"); c.setAttribute("stroke", "currentColor"); c.setAttribute("stroke-width", "1.5");
      s.append(c);
    }
    const p = document.createElementNS(SVG_NS, "path");
    p.setAttribute("d", ICONS[name]);
    p.setAttribute("fill", "none");
    p.setAttribute("stroke", "currentColor");
    p.setAttribute("stroke-width", (name === "tick" || name === "caret") ? "2.2" : "1.6");
    p.setAttribute("stroke-linecap", "round");
    p.setAttribute("stroke-linejoin", "round");
    s.append(p);
    return s;
  }

  function fmtDuration(sec) {
    if (sec < 60) return Math.max(1, Math.round(sec)) + " s";
    const m = Math.floor(sec / 60), s = Math.round(sec % 60);
    return m + " min" + (s ? " " + s + " s" : "");
  }

  function fmtEta(sec) {
    if (sec == null) return null;
    if (sec < 45) return "Less than a minute left";
    const m = Math.round(sec / 60);
    return "About " + m + " minute" + (m === 1 ? "" : "s") + " left";
  }

  function joinNames(names) {
    if (names.length <= 1) return names.join("");
    return names.slice(0, -1).join(", ") + " and " + names[names.length - 1];
  }

  // ------------------------------------------------------------------ progress

  const stepStates = {};

  function renderProgress(job) {
    const pct = Math.round(job.progress * 100);
    $("progress-fill").style.width = pct + "%";
    $("progress-pct").textContent = pct + "%";
    $("progress-bar").setAttribute("aria-valuenow", String(pct));

    let eta = fmtEta(job.eta_seconds);
    if (!eta) {
      const cur = job.steps.find((s) => s.state === "current");
      eta = job.status === "queued" ? "Waiting to start…" : cur ? cur.label + "…" : "Starting…";
    }
    $("eta").textContent = eta;

    // Update the checklist in place so a step's tick is drawn once, when it finishes.
    const list = $("checklist");
    job.steps.forEach((s) => {
      let li = list.querySelector('[data-step="' + s.key + '"]');
      if (!li) {
        li = h("li", { "data-step": s.key },
          h("span", { class: "icon", "aria-hidden": "true" }),
          h("span", { class: "label" }, h("span", { class: "name", text: s.label }),
            h("span", { class: "visually-hidden state" }), h("span", { class: "detail" })));
        list.append(li);
      }
      const prev = stepStates[s.key];
      if (prev !== s.state) {
        li.className = s.state + (prev && s.state === "done" ? " just-done" : "");
        const iconEl = li.querySelector(".icon");
        iconEl.replaceChildren(s.state === "done" ? icon("tick", 18) : s.state === "current" ? icon("caret", 18) : "");
        li.querySelector(".state").textContent = s.state === "done" ? " (done)" : s.state === "current" ? " (in progress)" : "";
        if (s.state === "current") li.setAttribute("aria-current", "step"); else li.removeAttribute("aria-current");
        stepStates[s.key] = s.state;
      }
      const detail = li.querySelector(".detail");
      detail.textContent = s.detail || "";
      detail.hidden = !s.detail;
    });
    $("wake-note").hidden = job.progress > 0.08;
  }

  function renderNotices(job) {
    $("notices").replaceChildren(...(job.notices || []).map((n) =>
      h("div", { class: "note " + (n.kind === "warning" ? "note-warn" : "note-info"), role: "status" },
        icon(n.kind === "warning" ? "review" : "info", 20), h("span", { text: n.text }))));
  }

  function renderError(job) {
    if (job.status === "interrupted") {
      $("error-title").textContent = "This translation was interrupted";
      $("error-message").textContent = "The server restarted while your document was being translated, so it " +
        "didn't finish. Nothing was lost on your side. Please run it again.";
    } else {
      const err = job.error || {};
      $("error-title").textContent = err.title || "Something went wrong";
      $("error-message").textContent = err.message || "Please try again.";
    }
    $("error-card").hidden = false;
    const note = document.querySelector(".job-ticket .hint");
    if (note) note.hidden = true;  // there are no results to come back to
  }

  function renderTech(job) {
    const u = job.usage || {};
    const rows = [
      ["Job", job.id],
      ["Model", u.model || "—"],
      ["API calls", (u.calls || 0) + (u.cached_calls ? " (+" + u.cached_calls + " answered from cache)" : "")],
      ["Tokens", (u.prompt_tokens || 0).toLocaleString() + " in / " + (u.completion_tokens || 0).toLocaleString() + " out"],
    ];
    if (job.cost && job.cost.available) rows.push(["Cost", "$" + job.cost.usd.toFixed(4)]);
    else if (job.cost && job.cost.note) rows.push(["Cost", job.cost.note]);
    if (job.error && job.error.detail) rows.push(["Error", job.error.code || ""]);
    $("tech-meta").replaceChildren(...rows.flatMap(([k, v]) => [h("dt", { text: k }), h("dd", { text: v })]));
    const lines = (job.log || []).slice();
    if (job.error && job.error.detail) lines.push("", job.error.detail);
    const log = $("log");
    const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 20;
    log.textContent = lines.join("\n");
    if (atBottom) log.scrollTop = log.scrollHeight;
  }

  // ------------------------------------------------------------------ results

  let previewData = null;
  let resultsRendered = false;

  async function loadPreview() {
    try {
      const res = await fetch("/api/job/" + jobId + "/preview");
      if (res.ok) previewData = await res.json();
    } catch (e) { /* preview is optional */ }
  }

  function costText(job) {
    const u = job.usage || {};
    if (job.cost && job.cost.available) {
      const usd = job.cost.usd;
      const cached = job.is_sample && !u.calls;
      return {
        value: usd < 0.01 && usd > 0 ? "under $0.01" : "$" + usd.toFixed(2),
        note: cached ? "The sample's translations are cached, so this run was free"
          : (job.langs.length > 1 ? "Whole job, all languages" : "Whole job"),
      };
    }
    return { value: "Not available", note: "No pricing is configured for this model" };
  }

  function signRow(label, value, note, cls) {
    return h("tr", {},
      h("th", { scope: "row", text: label }),
      h("td", { class: cls || null }, h("span", { class: "val" }, value), note ? h("small", { text: note }) : null));
  }

  function renderSignoff(job, lang, meta) {
    const r = job.results[lang];
    const s = r.summary;
    const rows = [];
    if (s) {
      const fixed = [];
      if (s.fit.shrunk) fixed.push(s.fit.shrunk + " made slightly smaller");
      if (s.fit.shortened) fixed.push(s.fit.shortened + " reworded shorter");
      const all = s.paragraphs_translated === s.paragraphs_total;
      rows.push(signRow("Paragraphs translated", s.paragraphs_translated + " of " + s.paragraphs_total,
        all ? "Everything was translated" : "Some text kept its original wording", all ? null : "attention"));
      rows.push(signRow("Fitted automatically", String(s.auto_fixed),
        fixed.length ? fixed.join(", ") : (s.fit.wrapped ? "Everything fit after re-wrapping lines" : "Everything fit as-is")));
      rows.push(signRow("Marked for your review", String(s.review_items),
        s.review_items ? "Highlighted in the proof below" : "Nothing was marked", s.review_items ? "attention" : null));
    }
    const cost = costText(job);
    rows.push(signRow("API cost", cost.value, cost.note));

    const table = h("table", { class: "signoff-table" },
      h("caption", { class: "caps", text: meta.name + " proof" }), h("tbody", {}, rows));

    const dl = h("div", { class: "downloads" },
      h("a", { class: "btn btn-primary btn-lg primary-dl", href: r.downloads.package, download: r.package_name || true },
        h("span", { class: "btn-text" }, h("span", { text: "Download for InDesign" }),
          h("span", { class: "sub", text: ".zip with the .idml, its Links" + (meta.rtl ? " and the Arabic font" : "") }))),
      h("div", { class: "secondary-links" },
        h("a", { href: r.downloads.idml, download: r.idml_name || true, text: "Just the .idml" }),
        h("a", { href: r.downloads.report, target: "_blank", rel: "noopener", text: "QA report" }),
        h("a", { href: r.downloads.report_json, download: true, text: "QA data (JSON)" })),
      h("ul", { class: "legend", "aria-label": "What the margin marks mean" },
        h("li", {}, h("strong", { class: "mnote fixed" }, h("b", { text: "Fixed to fit" })), "Re-wrapped or made slightly smaller. Nothing for you to do."),
        h("li", {}, h("strong", { class: "mnote review" }, h("b", { text: "Check this" })), "Highlighted in the proof. These are the items counted under review."),
        h("li", {}, h("strong", { class: "mnote info" }, h("b", { text: "Much longer or shorter" })), "Worth a glance in InDesign. Not counted as needing review.")));

    return h("section", { class: "sheet signoff-sheet", "aria-label": meta.name + " summary and downloads" },
      h("div", { class: "signoff" }, table, dl));
  }

  function runSpans(runs, texts, translated, markFlagged) {
    const out = [];
    for (const run of runs) {
      let text = run.text;
      let cls = "";
      if (translated && run.t) {
        const t = texts[String(run.id)];
        if (t == null) cls = "untranslated"; else text = t;
      }
      if (!text) continue;
      let node = document.createTextNode(text);
      if (run.i) node = h("em", {}, node);
      if (run.b) node = h("strong", {}, node);
      if (cls) node = h("span", { class: cls, title: "Not translated" }, node);
      out.push(node);
    }
    if (translated && markFlagged && out.length) return [h("span", { class: "mark-text" }, out)];
    return out;
  }

  function flagsFor(runs, flags) {
    const seen = new Map();
    for (const run of runs) {
      for (const f of flags[String(run.id)] || []) {
        if (!seen.has(f.label)) seen.set(f.label, f);
      }
    }
    return Array.from(seen.values());
  }

  const FLAG_ICON = { review: "review", fixed: "fit", info: "info" };

  function marginNotes(list) {
    return h("div", { class: "margin" }, list.map((f) =>
      h("p", { class: "mnote " + f.kind }, h("b", {}, icon(FLAG_ICON[f.kind] || "info"), f.label),
        f.detail ? f.detail : null)));
  }

  function rowClass(base, flagsList) {
    if (flagsList.some((f) => f.kind === "review")) return base + " flag-review";
    if (flagsList.some((f) => f.kind === "fixed")) return base + " flag-fixed";
    return base;
  }

  function renderPreview(job, lang, meta) {
    const L = previewData && previewData.langs[lang];
    if (!L) {
      return h("p", { class: "hint", text: "The preview isn't available for this translation, but the files above are ready." });
    }
    const dstAttrs = { class: "dst", lang: lang, dir: meta.rtl ? "rtl" : "ltr" };
    const container = h("div", { class: "preview-body" });
    let reviewCount = 0;

    for (const page of previewData.pages) {
      const other = page.name === "Other text";
      const sheet = h("section", { class: "sheet preview-sheet page-block", "aria-label": other ? "Master pages and other text" : "Page " + page.name },
        h("div", { class: "slug caps" },
          h("span", { text: job.source_name }),
          h("span", { text: other ? "Master pages & other text" : "Page " + page.name })),
        h("div", { class: "proof-cols caps", "aria-hidden": "true" },
          h("span", { text: "English" }), h("span", { text: meta.name }), h("span", { text: "Margin" })));
      let rows = 0;
      for (const story of page.stories) {
        let n = 0;
        for (const block of story.blocks) {
          if (block.type === "para") {
            const fl = flagsFor(block.runs, L.flags);
            const review = fl.some((f) => f.kind === "review");
            if (review) reviewCount++;
            n = block.list === "number" ? n + 1 : 0;
            const cls = rowClass("prow k-" + block.kind + (block.list ? " list list-" + block.list : ""), fl);
            sheet.append(h("div", { class: cls, "data-review": review ? "1" : null },
              h("div", { class: "src", lang: "en", "data-n": block.list === "number" ? n : null },
                h("span", { class: "lang-tag caps", text: "English" }), runSpans(block.runs, L.texts, false)),
              h("div", Object.assign({}, dstAttrs, { "data-n": block.list === "number" ? n : null }),
                h("span", { class: "lang-tag caps", text: meta.name }), runSpans(block.runs, L.texts, true, review)),
              marginNotes(fl)));
            rows++;
          } else if (block.type === "table") {
            const fl = flagsFor(block.rows.flat().flat(), L.flags);
            const review = fl.some((f) => f.kind === "review");
            if (review) reviewCount++;
            const table = (translated) => h("div", { class: "mtable-wrap" }, h("table", { class: "mtable" },
              h("tbody", {}, block.rows.map((row) => h("tr", {}, row.map((cell) => {
                const cf = flagsFor(cell, L.flags);
                return h("td", { class: translated && cf.some((f) => f.kind === "review") ? "flag-review" : null },
                  runSpans(cell, L.texts, translated));
              }))))));
            sheet.append(h("div", { class: rowClass("prow table-row", fl), "data-review": review ? "1" : null },
              h("div", { class: "src", lang: "en" }, h("span", { class: "lang-tag caps", text: "English" }), table(false)),
              h("div", dstAttrs, h("span", { class: "lang-tag caps", text: meta.name }), table(true)),
              marginNotes(fl)));
            rows++;
          }
        }
      }
      if (rows) container.append(sheet);
    }

    const empty = h("p", { class: "empty-filter", hidden: true, text: "Nothing is marked for review. Every paragraph was translated and fits." });
    container.append(empty);
    const toggle = h("input", {
      type: "checkbox", onchange: (e) => {
        const only = e.target.checked;
        container.querySelectorAll(".prow").forEach((r) => { r.hidden = only && !r.dataset.review; });
        container.querySelectorAll(".page-block").forEach((p) => { p.hidden = only && !p.querySelector(".prow:not([hidden])"); });
        empty.hidden = !(only && reviewCount === 0);
      },
    });
    return h("section", { class: "preview", "aria-label": "Marked proof: original and translation" },
      h("div", { class: "preview-head" },
        h("h3", { text: "Original and translation" }),
        h("label", { class: "toggle" }, toggle, "Only show items to review (" + reviewCount + ")")),
      container);
  }

  function renderResults(job) {
    if (resultsRendered) return;
    resultsRendered = true;
    const tabs = $("lang-tabs");
    const panels = $("lang-panels");
    const langs = job.langs;
    const firstOk = langs.find((l) => job.results[l]) || langs[0];

    langs.forEach((lang) => {
      const meta = job.languages[lang];
      const ok = !!job.results[lang];
      const tab = h("button", {
        class: "tab", role: "tab", id: "tab-" + lang, "aria-controls": "panel-" + lang,
        "aria-selected": lang === firstOk ? "true" : "false", tabindex: lang === firstOk ? "0" : "-1", type: "button",
      }, h("span", { class: "dot" + (ok ? "" : " failed"), "aria-hidden": "true" }), meta.name,
        ok ? null : h("span", { class: "visually-hidden", text: " (failed)" }));
      tabs.append(tab);

      const panel = h("div", { role: "tabpanel", id: "panel-" + lang, "aria-labelledby": "tab-" + lang, hidden: lang !== firstOk });
      if (ok) {
        panel.append(renderSignoff(job, lang, meta), renderPreview(job, lang, meta));
      } else {
        const err = meta.error || {};
        panel.append(h("div", { class: "sheet error-card lang-error" },
          icon("review", 40),
          h("h3", { text: meta.name + ": " + (err.title || "this language didn't finish") }),
          h("p", { text: err.message || "Please try again." })));
        panel.querySelector("svg").classList.add("pencil-ring");
      }
      panels.append(panel);
    });

    function select(lang) {
      tabs.querySelectorAll(".tab").forEach((t) => {
        const on = t.id === "tab-" + lang;
        t.setAttribute("aria-selected", on ? "true" : "false");
        t.tabIndex = on ? 0 : -1;
      });
      panels.querySelectorAll("[role=tabpanel]").forEach((p) => { p.hidden = p.id !== "panel-" + lang; });
    }
    tabs.addEventListener("click", (e) => {
      const t = e.target.closest(".tab");
      if (t) select(t.id.slice(4));
    });
    tabs.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      const all = Array.from(tabs.querySelectorAll(".tab"));
      const i = all.indexOf(document.activeElement);
      const next = all[(i + (e.key === "ArrowRight" ? 1 : -1) + all.length) % all.length];
      next.focus();
      select(next.id.slice(4));
    });
    if (langs.length < 2) tabs.hidden = true;
    $("results").hidden = false;
  }

  // ------------------------------------------------------------------ main loop

  let failures = 0;

  async function poll() {
    let job;
    try {
      const res = await fetch("/api/job/" + jobId, { cache: "no-store" });
      if (res.status === 404) {
        $("progress-card").hidden = true;
        $("error-title").textContent = "We couldn't find this translation";
        $("error-message").textContent = "Results are deleted after a while, so it may have expired. Please run it again.";
        $("error-card").hidden = false;
        return;
      }
      if (!res.ok) throw new Error("HTTP " + res.status);
      job = await res.json();
      failures = 0;
    } catch (e) {
      failures++;
      $("eta").textContent = "Reconnecting to the server…";
      setTimeout(poll, Math.min(10000, 1500 * failures));
      return;
    }

    renderNotices(job);
    renderTech(job);
    if (job.created_at) $("ticket-started").textContent = new Date(job.created_at * 1000).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
    const names = job.langs.map((l) => job.languages[l].name);

    if (job.status === "queued" || job.status === "running") {
      renderProgress(job);
      setTimeout(poll, 1200);
      return;
    }

    $("progress-card").hidden = true;
    if (job.status === "done") $("status-sheet").hidden = true;
    const took = job.finished_at && job.started_at ? ", finished in " + fmtDuration(job.finished_at - job.started_at) : "";
    if (job.status === "done") {
      const okNames = job.langs.filter((l) => job.results[l]).map((l) => job.languages[l].name);
      const failed = job.langs.filter((l) => !job.results[l]).map((l) => job.languages[l].name);
      $("job-sub").textContent = "Translated into " + joinNames(okNames) + took +
        (failed.length ? ". " + joinNames(failed) + (failed.length > 1 ? " didn't" : " didn't") + " finish: see the tab for why." : "");
      document.title = "Done: " + job.source_name + ": Kartouche";
      await loadPreview();
      renderResults(job);
    } else {
      $("job-sub").textContent = "Couldn't finish translating into " + joinNames(names);
      document.title = "Didn't finish: " + job.source_name + ": Kartouche";
      renderError(job);
    }
  }

  poll();
})();
