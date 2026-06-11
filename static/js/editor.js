/* The visual page editor used by the Edit and Redact tools.

   Renders one page at a time with pdf.js and lets the user place elements on
   an overlay: text boxes, image stamps and rectangles (Edit), or black boxes
   (Redact). Everything is stored as page-relative fractions from the
   top-left, which is exactly what the server's overlay/redaction code
   expects. */

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
  $("#editor-tools").innerHTML = "";
  addToolButton(mode === "edit" ? "+ Text" : null, "text");
  addToolButton(mode === "edit" ? "+ Image" : null, "image");
  addToolButton(mode === "edit" ? "+ White box" : "+ Black box", "box");
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

function setStatus(text) {
  $("#editor-status").textContent = text;
}

async function renderPage() {
  const page = await editor.pdf.getPage(editor.page);
  const container = $("#editor-canvas-wrap");
  const maxWidth = Math.min(container.clientWidth || 720, 760);
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
  setStatus(editor.mode === "edit"
    ? "add elements, drag to move, double-click to delete"
    : "draw black boxes over what must disappear");
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
    if (event.target !== overlay) return;
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
    } else if (editor.placing === "box") {
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
        type: editor.mode === "redact" ? "rect" : "rect",
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
