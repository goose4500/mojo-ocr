"use strict";
const $ = (id) => document.getElementById(id);
let token = "",
  selected = null,
  result = null,
  edits = [],
  page = 0,
  busy = false;

function message(text, error = false) {
  if (error) {
    $("status").textContent = "Something needs your attention.";
    $("error").textContent = text;
    $("error").hidden = false;
  } else {
    $("status").textContent = text;
    $("error").hidden = true;
  }
}
function controls() {
  $("extract").disabled = busy || !token || !selected;
  $("clear").disabled = busy || (!result && !selected);
  for (const id of [
    "file",
    "example",
    "mode",
    "rotate",
    "dpi",
    "deskew",
    "adaptive",
  ])
    $(id).disabled = busy;
  $("status").classList.toggle("busy", busy);
  $("extract-label").textContent = busy
    ? "Reading your document…"
    : result
      ? "Extract again"
      : "Extract text";
  $("drop").setAttribute("aria-disabled", String(busy));
}
function select(file) {
  if (busy || !file) return;
  if (!/\.(png|jpe?g|webp|bmp|tiff?|pdf)$/i.test(file.name)) {
    message("Please choose an image or a PDF file.", true);
    return;
  }
  if (!file.size || file.size > 25 * 1024 * 1024) {
    message("Choose a non-empty file smaller than 25 MiB.", true);
    return;
  }
  if (
    result &&
    edits.some((text, i) => text !== result.pages[i].text) &&
    !confirm("Replacing this document discards your text edits. Continue?")
  )
    return;
  selected = file;
  result = null;
  edits = [];
  page = 0;
  $("result").hidden = true;
  $("empty").hidden = false;
  $("result-title").textContent = "Your text starts here";
  $("file-name").textContent = file.name;
  $("file-detail").textContent =
    `${(file.size / 1024).toLocaleString(undefined, { maximumFractionDigits: 0 })} KB · click to replace`;
  message("Ready when you are.");
  controls();
}
$("file").addEventListener("change", () => select($("file").files[0]));
$("drop").addEventListener("keydown", (event) => {
  if (!busy && ["Enter", " "].includes(event.key)) {
    event.preventDefault();
    $("file").click();
  }
});
for (const type of ["dragenter", "dragover"])
  $("drop").addEventListener(type, (event) => {
    event.preventDefault();
    if (!busy) $("drop").classList.add("dragging");
  });
for (const type of ["dragleave", "drop"])
  $("drop").addEventListener(type, (event) => {
    event.preventDefault();
    $("drop").classList.remove("dragging");
  });
$("drop").addEventListener("drop", (event) =>
  select(event.dataTransfer.files[0]),
);
// Avoid the browser navigating away when a file misses the drop target.
window.addEventListener("dragover", (event) => event.preventDefault());
window.addEventListener("drop", (event) => event.preventDefault());
window.addEventListener("paste", (event) => {
  if (busy || ["TEXTAREA", "INPUT"].includes(event.target.tagName)) return;
  const item = [...(event.clipboardData?.items || [])].find((item) =>
    item.type.startsWith("image/"),
  );
  if (item) {
    event.preventDefault();
    const blob = item.getAsFile();
    select(new File([blob], "pasted-image.png", { type: blob.type }));
  }
});
$("example").addEventListener("click", async () => {
  try {
    const response = await fetch("/example.png");
    if (!response.ok) throw Error("Example unavailable.");
    select(
      new File([await response.blob()], "example-note.png", {
        type: "image/png",
      }),
    );
  } catch (error) {
    message(error.message, true);
  }
});
function renderPage() {
  if (!result) return;
  const data = result.pages[page];
  $("text").value = edits[page];
  const image = $("boxes").checked ? data.overlay : data.preview;
  $("preview").src = image;
  $("preview-link").href = image;
  $("legend").hidden = !$("boxes").checked;
  $("metrics").textContent =
    `${data.uncertain_characters} low-confidence glyphs · ${(data.seconds * 1000).toFixed(0)} ms`;
  updateEdited();
}
function updateEdited() {
  $("character-count").textContent =
    `${$("text").value.length.toLocaleString()} characters`;
  $("edited").hidden = !result || edits[page] === result.pages[page].text;
}
$("page").addEventListener("change", () => {
  page = Number($("page").value);
  renderPage();
});
$("boxes").addEventListener("change", renderPage);
$("text").addEventListener("input", () => {
  edits[page] = $("text").value;
  updateEdited();
});
$("extract").addEventListener("click", async () => {
  if (busy || !selected) return;
  if (
    result &&
    edits.some((text, i) => text !== result.pages[i].text) &&
    !confirm("Extracting again replaces your text edits. Continue?")
  )
    return;
  busy = true;
  controls();
  message("Reading locally. Larger PDFs may take a little longer.");
  try {
    const params = new URLSearchParams({
      name: selected.name,
      mode: $("mode").value,
      dpi: $("dpi").value,
      rotate: $("rotate").value,
      deskew: $("deskew").checked ? "1" : "0",
      adaptive: $("adaptive").checked ? "1" : "0",
    });
    const response = await fetch("/api/ocr?" + params, {
      method: "POST",
      headers: {
        "Content-Type": "application/octet-stream",
        "X-OCR-Token": token,
      },
      body: selected,
    });
    const data = await response.json();
    if (!response.ok)
      throw Error(data.error || "OCR failed. Please try again.");
    if (!data.pages?.length) throw Error("No pages found in this document.");
    result = data;
    edits = data.pages.map((p) => p.text);
    page = 0;
    $("result-title").textContent = data.name;
    $("empty").hidden = true;
    $("result").hidden = false;
    $("page").replaceChildren(
      ...data.pages.map(
        (p, i) => new Option(`${i + 1} / ${data.pages.length}`, i),
      ),
    );
    $("download-pdf").href = data.pdf;
    $("download-json").href = data.json;
    renderPage();
    message(
      `Done. ${data.pages.length} page${data.pages.length === 1 ? "" : "s"} in ${data.seconds.toFixed(1)}s. Review before using.`,
    );
  } catch (error) {
    message(
      error.message || "Unable to connect. Is the local server still running?",
      true,
    );
  } finally {
    busy = false;
    controls();
  }
});
$("clear").addEventListener("click", async () => {
  if (
    result &&
    !confirm(
      "Clear this workspace and all temporary server results? Download anything you want to keep first.",
    )
  )
    return;
  busy = true;
  controls();
  try {
    const response = await fetch("/api/clear", {
      method: "POST",
      headers: { "X-OCR-Token": token },
    });
    if (!response.ok) throw Error("Could not clear results. Please try again.");
    result = null;
    selected = null;
    edits = [];
    page = 0;
    $("file").value = "";
    $("text").value = "";
    $("preview").removeAttribute("src");
    $("file-name").textContent = "Drop a file here";
    $("file-detail").textContent = "or click to browse";
    $("result-title").textContent = "Your text starts here";
    $("result").hidden = true;
    $("empty").hidden = false;
    message("Workspace cleared.");
  } catch (error) {
    message(error.message, true);
  } finally {
    busy = false;
    controls();
  }
});
$("copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("text").value);
    $("copy").textContent = "Copied!";
    setTimeout(() => {
      $("copy").textContent = "Copy text";
    }, 1800);
  } catch {
    $("text").focus();
    $("text").select();
    message("Text selected. Press Ctrl+C to copy.");
  }
});
$("download-text").addEventListener("click", () => {
  if (!result) return;
  const url = URL.createObjectURL(
    new Blob([edits.join("\n\f\n") + "\n"], {
      type: "text/plain;charset=utf-8",
    }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = result.name.replace(/\.[^.]+$/, "") + ".txt";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
window.addEventListener("beforeunload", (event) => {
  if (
    busy ||
    (result && edits.some((text, i) => text !== result.pages[i].text))
  ) {
    event.preventDefault();
    event.returnValue = "";
  }
});
(async () => {
  try {
    const response = await fetch("/api/status");
    if (!response.ok) throw Error("Server unavailable.");
    const data = await response.json();
    token = data.token;
    $("model-name").textContent = data.model;
    message("Model loaded. Everything stays on this machine.");
    controls();
  } catch {
    message(
      "Cannot reach the local OCR server. Start it with ./ocr serve, then reload this page.",
      true,
    );
  }
})();
