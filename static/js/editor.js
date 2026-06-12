/* The visual page editor used by the Edit and Redact tools, shown full-screen.

   Renders one page at a time with pdf.js and lets the user place elements on
   an overlay: text boxes, image stamps and rectangles (Edit), or black boxes
   (Redact). For Redact it also lays a clickable word layer over the page —
   every word the document exposes becomes a target you click to black it out,
   with likely-sensitive words (emails, phones, IDs…) pre-highlighted. Manual
   black boxes still work for anything that isn't selectable text (e.g. images).

   Everything is stored as page-relative fractions from the top-left, which is
   exactly what the server's overlay/redaction code expects. */

const $ = (selector) => document.querySelector(selector);

const editor = {
  pdf: null,
  mode: null,        // "edit" | "redact"
  placing: null,     // "text" | "image" | "box" while waiting for a click
  page: 1,
  pageCount: 0,
  elements: [],      // {type, page, x, y, w, h, text, size, color, file}
  images: [],        // File objects referenced by image elements
  pendingImage: null,
  scale: 1,          // css px per pdf point
  words: [],         // [{width,height,words:[{x,y,w,h,text,sensitive}]}] per page
  selectedWords: new Set(), // ids "page:index" the user marked for redaction
};

export function editorActive() {
  return editor.pdf !== null;
}

export function resetEditor() {
  editor.pdf = null;
  editor.elements = [];
  editor.images = [];
  editor.placing = null;
  editor.pendingImage = null;
  editor.words = [];
  editor.selectedWords = new Set();
  $("#editor").hidden = true;
  $("#editor-overlay").innerHTML = "";
}

export async function openEditor(file, mode, pdfjsLoader) {
  const panel = $("#editor");
  panel.hidden = false;
  $("#editor-status").textContent = "rendering…";
  try {
    const pdfjs = await pdfjsLoader();
    editor.pdf = await pdfjs.getDocument({ data: await file.arrayBuffer() }).promise;
  } catch {
    $("#editor-status").textContent =
      "preview unavailable — the editor needs the pdf.js CDN";
    return;
  }
  editor.mode = mode;
  editor.page = 1;
  editor.pageCount = editor.pdf.numPages;
  editor.elements = [];
  editor.images = [];
  editor.words = [];
  editor.selectedWords = new Set();

  $("#editor-tools").innerHTML = "";
  if (mode === "edit") {
    addToolButton("+ Text", "text");
    addToolButton("+ Image", "image");
    addToolButton("+ White box", "box");
  } else {
    addToolButton("+ Black box", "box");
    addActionButton("✨ Select sensitive", selectSensitive);
    addActionButton("Clear", clearSelection);
  }

  if (mode === "redact") loadWords(file);  // fire and forget; page renders meanwhile
  await renderPage();
}

function addToolButton(label, kind) {
  if (!label) return;
  const button = document.createElement("button");
  button.type = "button";
  button.className = "ghost small";
  button.textContent = label;
  button.addEventListener("click", () => {
    if (kind === "image") {
      $("#editor-image-input").click();
    } else {
      editor.placing = kind;
      setStatus(kind === "text" ? "click the page to place text"
                                : "drag on the page to draw the box");
    }
  });
  $("#editor-tools").appendChild(button);
}

function addActionButton(label, handler) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "ghost small";
  button.textContent = label;
  button.addEventListener("click", handler);
  $("#editor-tools").appendChild(button);
}

async function loadWords(file) {
  try {
    const body = new FormData();
    body.append("file", file, file.name);
    const response = await fetch("/api/inspect/words", { method: "POST", body });
    if (!response.ok) return;
    const payload = await response.json();
    editor.words = payload.pages || [];
    paintOverlay();
    const flagged = editor.words.reduce(
      (sum, page) => sum + page.words.filter((word) => word.sensitive).length, 0);
    if (flagged) {
      setStatus(`${flagged} likely-sensitive item(s) detected — click words to black `
              + `them out, or press “✨ Select sensitive”.`);
    } else {
      setStatus("click any word to black it out, or drag to draw a black box.");
    }
  } catch {
    /* word layer is a bonus; drawing boxes still works without it */
  }
}

function currentWords() {
  const page = editor.words[editor.page - 1];
  return page ? page.words : [];
}

function selectSensitive() {
  editor.words.forEach((page, pageIndex) => {
    page.words.forEach((word, index) => {
      if (word.sensitive) editor.selectedWords.add(`${pageIndex + 1}:${index}`);
    });
  });
  paintOverlay();
}

function clearSelection() {
  editor.selectedWords.clear();
  paintOverlay();
}

function setStatus(text) {
  $("#editor-status").textContent = text;
}

async function renderPage() {
  const page = await editor.pdf.getPage(editor.page);
  const container = $("#editor-canvas-wrap");
  const maxWidth = Math.min(container.clientWidth || 720, 820);
  const base = page.getViewport({ scale: 1 });
  editor.scale = maxWidth / base.width;
  const viewport = page.getViewport({ scale: editor.scale * (window.devicePixelRatio || 1) });

  const canvas = $("#editor-canvas");
  canvas.width = viewport.width;
  canvas.height = viewport.height;
  canvas.style.width = `${maxWidth}px`;
  canvas.style.height = `${(viewport.height / viewport.width) * maxWidth}px`;
  await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;

  $("#editor-pageno").textContent = `page ${editor.page} / ${editor.pageCount}`;
  if (editor.mode === "edit") {
    setStatus("add elements, drag to move, double-click to delete");
  } else if (!editor.words.length) {
    setStatus("draw black boxes over what must disappear");
  }
  paintOverlay();
}

export function wireEditor(onChange) {
  $("#editor-prev").addEventListener("click", () => flipPage(-1));
  $("#editor-next").addEventListener("click", () => flipPage(1));
  $("#editor-image-input").addEventListener("change", (event) => {
    const [file] = event.target.files;
    if (file) {
      editor.pendingImage = file;
      editor.placing = "image";
      setStatus("click the page to place the image");
    }
    event.target.value = "";
  });

  const overlay = $("#editor-overlay");
  let draft = null;

  overlay.addEventListener("pointerdown", (event) => {
    if (event.target !== overlay) return;  // clicks on words/elements handle themselves
    const position = relativePoint(event);
    if (editor.placing === "text") {
      addElement({ type: "text", page: editor.page, x: position.x, y: position.y,
                   size: 16, color: "#111111", text: "Type here" }, true);
      editor.placing = null;
    } else if (editor.placing === "image" && editor.pendingImage) {
      editor.images.push(editor.pendingImage);
      addElement({ type: "image", page: editor.page, x: position.x, y: position.y,
                   w: 0.25, h: 0.12, file: editor.images.length - 1,
                   _preview: URL.createObjectURL(editor.pendingImage) });
      editor.pendingImage = null;
      editor.placing = null;
    } else if (editor.placing === "box" || editor.mode === "redact") {
      draft = { start: position, div: document.createElement("div") };
      draft.div.className = "el rect " + (editor.mode === "redact" ? "black" : "white");
      overlay.appendChild(draft.div);
    }
    onChange?.();
  });

  overlay.addEventListener("pointermove", (event) => {
    if (!draft) return;
    const now = relativePoint(event);
    const box = normalizedBox(draft.start, now);
    positionDiv(draft.div, box);
  });

  overlay.addEventListener("pointerup", (event) => {
    if (!draft) return;
    const box = normalizedBox(draft.start, relativePoint(event));
    draft.div.remove();
    if (box.w > 0.005 && box.h > 0.005) {
      addElement({
        type: "rect",
        page: editor.page, ...box,
        color: editor.mode === "redact" ? "#000000" : "#ffffff",
        opacity: 1.0,
      });
    }
    draft = null;
    editor.placing = null;
    onChange?.();
  });
}

function relativePoint(event) {
  const rect = $("#editor-overlay").getBoundingClientRect();
  return {
    x: Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width)),
    y: Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height)),
  };
}

function normalizedBox(a, b) {
  return {
    x: Math.min(a.x, b.x), y: Math.min(a.y, b.y),
    w: Math.abs(a.x - b.x), h: Math.abs(a.y - b.y),
  };
}

function addElement(element, focus = false) {
  editor.elements.push(element);
  paintOverlay(focus ? element : null);
}

function paintOverlay(focusElement = null) {
  const overlay = $("#editor-overlay");
  overlay.innerHTML = "";
  const canvas = $("#editor-canvas");
  overlay.style.width = canvas.style.width;
  overlay.style.height = canvas.style.height;

  // Clickable word layer (redact only), painted under the placed elements.
  if (editor.mode === "redact") {
    currentWords().forEach((word, index) => {
      const id = `${editor.page}:${index}`;
      const box = document.createElement("div");
      box.className = "word"
        + (word.sensitive ? " sensitive" : "")
        + (editor.selectedWords.has(id) ? " selected" : "");
      positionDiv(box, word);
      box.title = editor.selectedWords.has(id) ? "click to un-redact" : `redact “${word.text}”`;
      box.addEventListener("click", (event) => {
        event.stopPropagation();
        if (editor.selectedWords.has(id)) editor.selectedWords.delete(id);
        else editor.selectedWords.add(id);
        paintOverlay();
      });
      overlay.appendChild(box);
    });
  }

  for (const element of editor.elements) {
    if (element.page !== editor.page) continue;
    const div = document.createElement("div");
    div.className = "el";
    if (element.type === "text") {
      div.classList.add("text");
      div.contentEditable = "plaintext-only";
      div.textContent = element.text;
      div.style.fontSize = `${element.size * editor.scale}px`;
      div.style.color = element.color;
      div.addEventListener("input", () => { element.text = div.textContent; });
      positionDiv(div, element, false);
    } else if (element.type === "image") {
      div.classList.add("image");
      const img = document.createElement("img");
      img.src = element._preview;
      div.appendChild(img);
      positionDiv(div, element);
    } else {
      div.classList.add("rect", element.color === "#000000" ? "black" : "white");
      positionDiv(div, element);
    }

    makeDraggable(div, element);
    div.addEventListener("dblclick", () => {
      editor.elements = editor.elements.filter((entry) => entry !== element);
      paintOverlay();
    });
    div.title = "drag to move · double-click to delete";
    overlay.appendChild(div);
    if (focusElement === element && element.type === "text") {
      div.focus();
      getSelection().selectAllChildren(div);
    }
  }
}

function positionDiv(div, box, sized = true) {
  div.style.left = `${box.x * 100}%`;
  div.style.top = `${box.y * 100}%`;
  if (sized && box.w !== undefined) {
    div.style.width = `${box.w * 100}%`;
    div.style.height = `${box.h * 100}%`;
  }
}

function makeDraggable(div, element) {
  div.addEventListener("pointerdown", (event) => {
    if (element.type === "text" && document.activeElement === div) return;
    event.stopPropagation();
    const startPoint = relativePoint(event);
    const origin = { x: element.x, y: element.y };
    const move = (moveEvent) => {
      const now = relativePoint(moveEvent);
      element.x = Math.min(1, Math.max(0, origin.x + now.x - startPoint.x));
      element.y = Math.min(1, Math.max(0, origin.y + now.y - startPoint.y));
      positionDiv(div, element, element.type !== "text");
    };
    const stop = () => {
      removeEventListener("pointermove", move);
      removeEventListener("pointerup", stop);
    };
    addEventListener("pointermove", move);
    addEventListener("pointerup", stop);
  });
}

async function flipPage(delta) {
  const next = editor.page + delta;
  if (next < 1 || next > editor.pageCount) return;
  editor.page = next;
  await renderPage();
}

export function collectEditor() {
  const elements = editor.elements.map(({ _preview, ...rest }) => rest);
  return { elements, images: editor.images };
}

/* Redactions = every selected word's box plus any hand-drawn black boxes. */
export function collectRedactions() {
  const regions = [];
  for (const id of editor.selectedWords) {
    const [page, index] = id.split(":").map(Number);
    const word = editor.words[page - 1]?.words[index];
    if (word) regions.push({ page, x: word.x, y: word.y, w: word.w, h: word.h });
  }
  for (const element of editor.elements) {
    if (element.type === "rect") {
      regions.push({ page: element.page, x: element.x, y: element.y,
                     w: element.w, h: element.h });
    }
  }
  return regions;
}

export function redactionCount() {
  return editor.selectedWords.size
    + editor.elements.filter((element) => element.type === "rect").length;
}
