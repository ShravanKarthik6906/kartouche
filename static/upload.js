// Landing page: drag-and-drop, inline validation and upload progress.
// Plain JS, no build step. Without JS the form still posts normally.
(function () {
  "use strict";
  const script = document.currentScript;
  const maxBytes = Number(script.dataset.maxBytes) || 50 * 1024 * 1024;

  const form = document.getElementById("upload-form");
  const input = document.getElementById("document-input");
  const zone = document.getElementById("dropzone");
  const fileLabel = document.getElementById("dz-file");
  const docError = document.getElementById("document-error");
  const langError = document.getElementById("langs-error");
  const submitBtn = document.getElementById("submit-button");
  const sampleBtn = document.getElementById("sample-button");
  const progress = document.getElementById("upload-progress");
  const bar = document.getElementById("upload-bar");
  const status = document.getElementById("upload-status");
  if (!form) return;

  function fmtSize(n) {
    return n >= 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB";
  }

  function showError(el, msg) {
    el.textContent = msg || "";
    el.hidden = !msg;
  }

  function validateFile() {
    const f = input.files && input.files[0];
    zone.classList.remove("is-invalid");
    if (!f) return "Choose an .idml or .zip file to upload.";
    const name = f.name.toLowerCase();
    let msg = null;
    if (name.endsWith(".indd")) {
      msg = "Rosetta needs an .idml file, not .indd. In InDesign choose File › Export… › InDesign Markup (IDML).";
    } else if (!name.endsWith(".idml") && !name.endsWith(".zip")) {
      msg = "Please choose an .idml file, or a .zip containing one.";
    } else if (f.size > maxBytes) {
      msg = "That file is " + fmtSize(f.size) + ", over the " + fmtSize(maxBytes) + " limit.";
    }
    if (msg) zone.classList.add("is-invalid");
    return msg;
  }

  function selectedLangs() {
    return Array.from(form.querySelectorAll('input[name="langs"]:checked')).map((i) => i.value);
  }

  function updateFile() {
    const f = input.files && input.files[0];
    if (f) {
      fileLabel.textContent = f.name + " · " + fmtSize(f.size);
      fileLabel.hidden = false;
      zone.classList.add("has-file");
      showError(docError, validateFile());
    } else {
      fileLabel.hidden = true;
      zone.classList.remove("has-file");
    }
  }

  input.addEventListener("change", updateFile);
  ["dragenter", "dragover"].forEach((ev) =>
    zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.add("is-over"); }));
  ["dragleave", "dragend", "drop"].forEach((ev) =>
    zone.addEventListener(ev, () => zone.classList.remove("is-over")));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    if (e.dataTransfer && e.dataTransfer.files.length) {
      input.files = e.dataTransfer.files;
      updateFile();
    }
  });
  // Dropping a file anywhere else on the page shouldn't navigate away.
  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("drop", (e) => e.preventDefault());

  form.addEventListener("change", (e) => {
    if (e.target.name === "langs" && selectedLangs().length) showError(langError, null);
  });

  function setBusy(busy, label) {
    [submitBtn, sampleBtn].forEach((b) => { if (b) { b.disabled = busy; b.setAttribute("aria-busy", busy ? "true" : "false"); } });
    progress.hidden = !busy;
    if (label) status.textContent = label;
  }

  form.addEventListener("submit", (e) => {
    const isSample = e.submitter && e.submitter.name === "sample";
    let ok = true;
    if (!selectedLangs().length) {
      showError(langError, "Choose at least one language.");
      ok = false;
    }
    if (!isSample) {
      const msg = validateFile();
      showError(docError, msg);
      if (msg) ok = false;
    }
    e.preventDefault();
    if (!ok) {
      const firstErr = form.querySelector(".field-error:not([hidden])");
      if (firstErr) firstErr.scrollIntoView({ block: "center", behavior: "smooth" });
      if (isSample && sampleBtn) document.getElementById("lang-chips").scrollIntoView({ block: "center" });
      return;
    }

    const data = new FormData();
    selectedLangs().forEach((l) => data.append("langs", l));
    if (isSample) data.append("sample", "1");
    else data.append("document", input.files[0]);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", form.action);
    xhr.setRequestHeader("X-Requested-With", "fetch");
    xhr.setRequestHeader("Accept", "application/json");
    bar.style.width = "0%";
    setBusy(true, isSample ? "Starting the sample…" : "Uploading…");
    if (isSample) bar.style.width = "100%";

    xhr.upload.addEventListener("progress", (ev) => {
      if (!isSample && ev.lengthComputable) {
        const pct = Math.round((ev.loaded / ev.total) * 100);
        bar.style.width = pct + "%";
        status.textContent = pct < 100 ? "Uploading… " + pct + "%" : "Checking your file…";
      }
    });
    xhr.addEventListener("load", () => {
      let body = {};
      try { body = JSON.parse(xhr.responseText); } catch (err) { /* not JSON */ }
      if (xhr.status >= 200 && xhr.status < 300 && body.job_url) {
        status.textContent = "Starting…";
        window.location.assign(body.job_url);
        return;
      }
      setBusy(false);
      const msg = body.error || (xhr.status === 413
        ? "That file is too large to upload."
        : "Something went wrong (" + xhr.status + "). Please try again.");
      if (body.field === "langs") showError(langError, msg);
      else {
        showError(docError, msg);
        if (body.field === "document") zone.classList.add("is-invalid");
        docError.scrollIntoView({ block: "center", behavior: "smooth" });
      }
    });
    xhr.addEventListener("error", () => {
      setBusy(false);
      showError(docError, "The upload didn't reach the server. Check your connection and try again.");
    });
    xhr.send(data);
  });
})();
