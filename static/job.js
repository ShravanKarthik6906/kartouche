// Job page: polls the job's status, then shows results and the side-by-side
// preview. All text is inserted with textContent (never innerHTML), so
// document and translation text can't inject markup.
(function () {
  "use strict";
  const root = document.getElementById("job");
  const jobId = root.dataset.jobId;
  const $ = (id) => document.getElementById(id);

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

  function fmtDuration(sec) {
    if (sec < 60) return Math.max(1, Math.round(sec)) + "\u00a0s";
    const m = Math.floor(sec / 60), s = Math.round(sec % 60);
    return m + "\u00a0min" + (s ? " " + s + "\u00a0s" : "");
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

    const list = $("checklist");
    list.replaceChildren(...job.steps.map((s) =>
      h("li", { class: s.state, "aria-current": s.state === "current" ? "step" : null },
        h("span", { class: "icon", "aria-hidden": "true" }),
        h("span", {}, s.label,
          s.state === "done" ? h("span", { class: "visually-hidden", text: " (done)" }) : null,
          s.detail ? h("span", { class: "detail", text: s.detail }) : null))));
    $("wake-note").hidden = job.progress > 0.08;
  }

  function renderNotices(job) {
    $("notices").replaceChildren(...(job.notices || []).map((n) =>
      h("div", { class: "alert " + (n.kind === "warning" ? "alert-warning" : "alert-info"), role: "status" }, n.text)));
  }

  function renderError(job) {
    const card = $("error-card");
    if (job.status === "interrupted") {
      $("error-title").textContent = "This job was interrupted";
      $("error-message").textContent = "The server restarted while your document was being translated, so it " +
        "didn't finish. Nothing was lost on your side. Please run it again.";
    } else {
      const err = job.error || {};
      $("error-title").textContent = err.title || "Something went wrong";
      $("error-message").textContent = err.message || "Please try again.";
    }
    card.hidden = false;
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

  function costStat(job) {
    const u = job.usage || {};
    if (job.cost && job.cost.available) {
      const usd = job.cost.usd;
      const cached = job.is_sample && !u.calls;
      return { value: usd < 0.01 && usd > 0 ? "<$0.01" : "$" + usd.toFixed(2),
               note: cached ? "Sample results are cached, so this run was free" : (job.langs.length > 1 ? "Whole job, all languages" : "Whole job") };
    }
    return { value: "—", note: "Cost not available for this model" };
  }

  function stat(label, value, note, cls) {
    return h("div", { class: "stat " + (cls || "") },
      h("div", { class: "label", text: label }),
      h("div", { class: "value" }, value),
      note ? h("div", { class: "note", text: note }) : null);
  }

  function renderSummary(job, lang) {
    const r = job.results[lang];
    const s = r.summary;
    if (!s) return h("div");
    const fixedBits = [];
    if (s.fit.shrunk) fixedBits.push(s.fit.shrunk + " made slightly smaller");
    if (s.fit.shortened) fixedBits.push(s.fit.shortened + " reworded shorter");
    const cost = costStat(job);
    return h("div", { class: "summary-grid" },
      stat("Paragraphs translated",
        [String(s.paragraphs_translated), h("small", { text: " / " + s.paragraphs_total })],
        s.paragraphs_translated === s.paragraphs_total ? "Everything was translated" : "Some text kept its original wording",
        s.paragraphs_translated === s.paragraphs_total ? "good" : "attention"),
      stat("Auto-fixed to fit", String(s.auto_fixed),
        fixedBits.length ? fixedBits.join(" · ") : (s.fit.wrapped ? "Everything fit after re-wrapping" : "Everything fit as-is")),
      stat("Needs your review", String(s.review_items),
        s.review_items ? "Highlighted in the preview below" : "Nothing was flagged",
        s.review_items ? "attention" : "good"),
      stat("API cost", cost.value, cost.note));
  }

  function renderDownloads(job, lang, langMeta) {
    const r = job.results[lang];
    return h("div", { class: "downloads" },
      h("a", { class: "btn btn-primary btn-lg primary-dl", href: r.downloads.package, download: r.package_name || true },
        h("span", { text: "Download for InDesign" }),
        h("span", { class: "sub", text: "Open the .idml inside in Adobe InDesign · includes Links" + (langMeta.rtl ? " and Arabic font" : "") })),
      h("div", { class: "secondary-links" },
        h("a", { href: r.downloads.idml, download: r.idml_name || true, text: "Just the .idml" }),
        h("a", { href: r.downloads.report, target: "_blank", rel: "noopener", text: "QA report" }),
        h("a", { href: r.downloads.report_json, download: true, text: "QA data (JSON)" })));
  }

  function runSpans(runs, texts, translated) {
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

  function flagList(list) {
    if (!list.length) return null;
    return h("div", { class: "flags" }, list.map((f) =>
      h("div", { class: "flag " + f.kind }, h("span", { class: "pill", text: f.label }),
        f.detail ? h("span", { class: "why", text: f.detail }) : null)));
  }

  function rowClass(base, flagsList) {
    if (flagsList.some((f) => f.kind === "review")) return base + " flag-review";
    if (flagsList.some((f) => f.kind === "fixed")) return base + " flag-fixed";
    return base;
  }

  function renderPreview(job, lang, langMeta) {
    const L = previewData && previewData.langs[lang];
    if (!L) {
      return h("p", { class: "hint", text: "The preview isn't available for this job, but the files above are ready." });
    }
    const dstAttrs = { class: "dst", lang: lang, dir: langMeta.rtl ? "rtl" : "ltr" };
    const container = h("div", { class: "preview-body" });
    let reviewCount = 0;

    for (const page of previewData.pages) {
      const pageEl = h("section", { class: "page-block" },
        h("h4", { class: "page-label", text: page.name === "Other text" ? "Master pages & other text" : "Page " + page.name }));
      for (const story of page.stories) {
        const storyEl = h("div", { class: "story" });
        let n = 0;
        for (const block of story.blocks) {
          if (block.type === "para") {
            const fl = flagsFor(block.runs, L.flags);
            const review = fl.some((f) => f.kind === "review");
            if (review) reviewCount++;
            n = block.list === "number" ? n + 1 : 0;
            const cls = rowClass("row k-" + block.kind + (block.list ? " list list-" + block.list : ""), fl);
            storyEl.append(h("div", { class: cls, "data-review": review ? "1" : null },
              h("div", { class: "src", lang: "en", "data-n": block.list === "number" ? n : null },
                h("span", { class: "lang-tag", text: "English" }), runSpans(block.runs, L.texts, false)),
              h("div", Object.assign({}, dstAttrs, { "data-n": block.list === "number" ? n : null }),
                h("span", { class: "lang-tag", text: langMeta.name }), runSpans(block.runs, L.texts, true)),
              flagList(fl)));
          } else if (block.type === "table") {
            const allRuns = block.rows.flat().flat();
            const fl = flagsFor(allRuns, L.flags);
            const review = fl.some((f) => f.kind === "review");
            if (review) reviewCount++;
            const table = (translated) => h("div", { class: "mtable-wrap" }, h("table", { class: "mtable" },
              h("tbody", {}, block.rows.map((row) => h("tr", {}, row.map((cell) => {
                const cf = flagsFor(cell, L.flags);
                return h("td", { class: cf.some((f) => f.kind === "review") ? "flag-review" : null },
                  runSpans(cell, L.texts, translated));
              }))))));
            storyEl.append(h("div", { class: rowClass("row table-row", fl), "data-review": review ? "1" : null },
              h("div", { class: "src", lang: "en" }, h("span", { class: "lang-tag", text: "English" }), table(false)),
              h("div", dstAttrs, h("span", { class: "lang-tag", text: langMeta.name }), table(true)),
              flagList(fl)));
          }
        }
        if (storyEl.children.length) pageEl.append(storyEl);
      }
      container.append(pageEl);
    }

    const empty = h("p", { class: "empty-filter", hidden: true, text: "Nothing needs review. Every paragraph was translated and fits." });
    container.append(empty);
    const toggle = h("input", {
      type: "checkbox", onchange: (e) => {
        const only = e.target.checked;
        container.querySelectorAll(".row").forEach((r) => { r.hidden = only && !r.dataset.review; });
        container.querySelectorAll(".story").forEach((s) => { s.hidden = only && !s.querySelector(".row:not([hidden])"); });
        container.querySelectorAll(".page-block").forEach((p) => { p.hidden = only && !p.querySelector(".story:not([hidden])"); });
        empty.hidden = !(only && reviewCount === 0);
      },
    });
    return h("section", { class: "preview", "aria-label": "Side-by-side preview" },
      h("div", { class: "preview-head" },
        h("h3", { text: "Original and translation" }),
        h("label", { class: "toggle" }, toggle, "Only show items to review (" + reviewCount + ")")),
      h("div", { class: "preview-cols", "aria-hidden": "true" }, h("span", { text: "English" }), h("span", { text: langMeta.name })),
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
        panel.append(renderSummary(job, lang), renderDownloads(job, lang, meta), renderPreview(job, lang, meta));
      } else {
        const err = meta.error || {};
        panel.append(h("div", { class: "card error-card lang-error" },
          h("h3", { class: "card-title", text: meta.name + ": " + (err.title || "This language didn't finish") }),
          h("p", { text: err.message || "Please try again." })));
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
    const names = job.langs.map((l) => job.languages[l].name);

    if (job.status === "queued" || job.status === "running") {
      renderProgress(job);
      setTimeout(poll, 1200);
      return;
    }

    $("progress-card").hidden = true;
    const took = job.finished_at && job.started_at ? " · finished in " + fmtDuration(job.finished_at - job.started_at) : "";
    if (job.status === "done") {
      const okNames = job.langs.filter((l) => job.results[l]).map((l) => job.languages[l].name);
      $("job-sub").textContent = "Translated into " + joinNames(okNames) + took;
      document.title = "Done — " + job.source_name + " — Rosetta";
      await loadPreview();
      renderResults(job);
    } else {
      $("job-sub").textContent = "Couldn't finish translating into " + joinNames(names);
      document.title = "Didn't finish — " + job.source_name + " — Rosetta";
      renderError(job);
    }
  }

  poll();
})();
