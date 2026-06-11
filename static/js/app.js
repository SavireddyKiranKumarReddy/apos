/* pdfsmith frontend: renders the tool grid from /api/tools, runs tools via
   multipart POST, and adds the niceties — drag-drop, pdf.js page thumbnails
   with click-select / drag-reorder, theme toggle, toasts. */

import {
  collectEditor,
  editorActive,
  openEditor,
  resetEditor,
  wireEditor,
} from "./editor.js";
import {
  initWorkflows,
  renderWorkflowsGrid,
  setWorkflowToast,
} from "./workflows.js";

const $ = (selector) => document.querySelector(selector);

const EDITOR_TOOLS = { edit: "elements", redact: "regions" };

const state = {
  tools: [],
  tool: null,
  files: [],
  pageOrder: [],      // organize: current thumbnail order (1-based page numbers)
  selectedPages: new Set(), // split/rotate: clicked pages
  pdfjs: null,
  tab: "all",
};

const CATEGORIES = [
  ["organize", "Organize PDF"],
  ["optimize", "Optimize PDF"],
  ["convert", "Convert PDF"],
  ["edit", "Edit PDF"],
  ["secure", "PDF Security"],
  ["intelligence", "PDF Intelligence"],
];

const TABS = [
  ["all", "All"],
  ["workflows", "Workflows"],
  ...CATEGORIES,
];

const CONVERT_TO_PDF = ["images_to_pdf", "office_to_pdf", "html_to_pdf"];
const CONVERT_FROM_PDF = [
  "pdf_to_images", "pdf_to_word", "pdf_to_powerpoint", "pdf_to_excel", "pdf_to_pdfa",
];

/* ---------- boot ---------- */

init();

async function init() {
  setupTheme();
  try {
    const response = await fetch("/api/tools");
    const payload = await response.json();
    state.tools = payload.tools;
    renderTabs();
    renderGrid();
    renderNavMenus();
    setWorkflowToast(toast);
    initWorkflows(state.tools, { onExit: showHome });
    $("#availability-note").textContent = availabilityNote(payload.tools);
  } catch {
    toast("Could not reach the pdfsmith API — is the server running?", "error");
  }
  $("#search").addEventListener("input", () => {
    if (state.tab === "workflows") setTab("all");
    renderGrid();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "/" && document.activeElement !== $("#search")) {
      event.preventDefault();
      $("#search").focus();
    }
    if (event.key === "Escape" && state.tool) showHome();
  });
  $("#back").addEventListener("click", showHome);
  $("#brand").addEventListener("click", (event) => { event.preventDefault(); showHome(); });
  $("#again").addEventListener("click", () => openTool(state.tool.name));
  $("#run").addEventListener("click", runTool);
  setupDropzone();
  wireEditor();
}

function availabilityNote(tools) {
  const missing = tools.filter((tool) => !tool.available).map((tool) => tool.label);
  return missing.length
    ? `Greyed out here (Docker image has them): ${missing.join(", ")}`
    : "All tools available on this server.";
}

/* ---------- theme ---------- */

function setupTheme() {
  const stored = localStorage.getItem("pdfsmith-theme");
  if (stored) document.documentElement.dataset.theme = stored;
  else if (matchMedia("(prefers-color-scheme: dark)").matches) {
    document.documentElement.dataset.theme = "dark";
  }
  $("#theme-toggle").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("pdfsmith-theme", next);
  });
}

/* ---------- tabs + nav ---------- */

function renderTabs() {
  const bar = $("#tabs");
  bar.innerHTML = "";
  for (const [key, label] of TABS) {
    const button = document.createElement("button");
    button.className = "tab" + (state.tab === key ? " active" : "");
    button.textContent = label;
    button.setAttribute("role", "tab");
    button.addEventListener("click", () => setTab(key));
    bar.appendChild(button);
  }
}

function setTab(key) {
  state.tab = key;
  renderTabs();
  const isWorkflows = key === "workflows";
  $("#grid").hidden = isWorkflows;
  $("#workflows-panel").hidden = !isWorkflows;
  if (isWorkflows) renderWorkflowsGrid($("#workflows-grid"), toast);
  else renderGrid();
}

function renderNavMenus() {
  const convertMenu = $("#convert-menu");
  convertMenu.innerHTML = "";
  for (const [title, names] of [["Convert to PDF", CONVERT_TO_PDF],
                                ["Convert from PDF", CONVERT_FROM_PDF]]) {
    const column = document.createElement("div");
    column.className = "menu-col";
    const heading = document.createElement("h4");
    heading.textContent = title;
    column.appendChild(heading);
    for (const name of names) {
      const tool = state.tools.find((entry) => entry.name === name);
      if (tool) column.appendChild(menuItem(tool));
    }
    convertMenu.appendChild(column);
  }

  const mega = $("#mega-menu");
  mega.innerHTML = "";
  for (const [key, title] of CATEGORIES) {
    const tools = state.tools.filter((tool) => tool.category === key);
    if (!tools.length) continue;
    const column = document.createElement("div");
    column.className = "menu-col";
    const heading = document.createElement("h4");
    heading.textContent = title;
    column.appendChild(heading);
    for (const tool of tools) column.appendChild(menuItem(tool));
    mega.appendChild(column);
  }

  for (const drop of document.querySelectorAll(".nav-drop")) {
    const button = drop.querySelector("button");
    const menu = drop.querySelector(".menu");
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const wasHidden = menu.hidden;
      closeMenus();
      menu.hidden = !wasHidden;
      button.setAttribute("aria-expanded", String(!menu.hidden));
    });
  }
  document.addEventListener("click", closeMenus);
  for (const quick of document.querySelectorAll("[data-open-tool]")) {
    quick.addEventListener("click", () => openTool(quick.dataset.openTool));
  }
}

function closeMenus() {
  for (const menu of document.querySelectorAll(".nav-drop .menu")) menu.hidden = true;
  for (const button of document.querySelectorAll(".nav-drop button")) {
    button.setAttribute("aria-expanded", "false");
  }
}

function menuItem(tool) {
  const item = document.createElement("button");
  item.className = "menu-item" + (tool.available ? "" : " unavailable");
  item.innerHTML = `<span>${tool.icon}</span> ${tool.label}`;
  if (tool.available) {
    item.addEventListener("click", () => {
      closeMenus();
      openTool(tool.name);
    });
  } else {
    item.title = tool.unavailable_hint;
  }
  return item;
}

/* ---------- home grid ---------- */

function renderGrid() {
  const query = $("#search").value.trim().toLowerCase();
  const grid = $("#grid");
  grid.innerHTML = "";
  const categories =
    state.tab === "all" ? CATEGORIES : CATEGORIES.filter(([key]) => key === state.tab);
  for (const [key, title] of categories) {
    const tools = state.tools.filter(
      (tool) =>
        tool.category === key &&
        (tool.label + " " + tool.description).toLowerCase().includes(query)
    );
    if (!tools.length) continue;
    const heading = document.createElement("div");
    heading.className = "cat-title";
    heading.textContent = title;
    grid.appendChild(heading);
    for (const tool of tools) grid.appendChild(card(tool));
  }
}

function card(tool) {
  const button = document.createElement("button");
  button.className = "card" + (tool.available ? "" : " unavailable");
  button.innerHTML = `
    <span class="icon">${tool.icon}</span>
    <h3>${tool.label}</h3>
    <p>${tool.description}</p>
    ${tool.available ? "" : `<span class="badge">${tool.unavailable_hint}</span>`}`;
  if (tool.available) button.addEventListener("click", () => openTool(tool.name));
  else button.title = tool.unavailable_hint;
  return button;
}

/* ---------- tool view ---------- */

function showHome() {
  state.tool = null;
  $("#tool").hidden = true;
  $("#workflow-editor").hidden = true;
  $("#home").hidden = false;
}

function openTool(name) {
  const tool = state.tools.find((entry) => entry.name === name);
  state.tool = tool;
  state.files = [];
  state.pageOrder = [];
  state.selectedPages = new Set();

  $("#home").hidden = true;
  $("#workflow-editor").hidden = true;
  $("#tool").hidden = false;
  $("#tool-icon").textContent = tool.icon;
  $("#tool-title").textContent = tool.label;
  $("#tool-desc").textContent = tool.description;
  $("#result").hidden = true;
  $("#run").disabled = false;
  $("#run").classList.remove("working");
  $("#thumbs").hidden = true;
  $("#thumbs").innerHTML = "";
  resetEditor();
  $("#form-fields").hidden = true;
  $("#form-fields").innerHTML = "";
  $("#hint").textContent =
    tool.name === "sign" ? "add the PDF — and optionally a .p12/.pfx certificate"
    : tool.multiple ? "add as many files as you like" : "";

  const input = $("#file-input");
  input.accept = tool.accepts;
  input.multiple = tool.multiple;
  renderFileList();
  renderOptions(tool);
}

const PROGRAMMATIC_OPTIONS = new Set(["elements", "regions", "fields"]);

function renderOptions(tool) {
  const form = $("#options");
  form.innerHTML = "";
  for (const option of tool.options) {
    if (PROGRAMMATIC_OPTIONS.has(option.name) &&
        (EDITOR_TOOLS[tool.name] || tool.name === "form_fill")) {
      const hidden = document.createElement("input");
      hidden.type = "hidden";
      hidden.name = option.name;
      form.appendChild(hidden);
      continue;
    }
    const field = document.createElement("div");
    field.className = "field" + (option.kind === "checkbox" ? " check" : "");
    const id = `opt-${option.name}`;
    let control;
    if (option.kind === "select") {
      control = document.createElement("select");
      for (const choice of option.choices) {
        const entry = document.createElement("option");
        entry.value = choice.value;
        entry.textContent = choice.label;
        if (choice.value === String(option.default)) entry.selected = true;
        control.appendChild(entry);
      }
    } else if (option.kind === "checkbox") {
      control = document.createElement("input");
      control.type = "checkbox";
      control.checked = Boolean(option.default);
    } else {
      control = document.createElement("input");
      control.type = option.kind === "number" ? "number" : option.kind;
      if (option.default !== null && option.default !== undefined) control.value = option.default;
    }
    control.id = id;
    control.name = option.name;

    const label = document.createElement("label");
    label.htmlFor = id;
    label.textContent = option.label;

    if (option.kind === "checkbox") {
      field.append(control, label);
    } else {
      field.append(label, control);
    }
    if (option.help) {
      const help = document.createElement("span");
      help.className = "help";
      help.textContent = option.help;
      field.appendChild(help);
    }
    form.appendChild(field);
  }
}

/* ---------- files ---------- */

function setupDropzone() {
  const zone = $("#dropzone");
  const input = $("#file-input");
  zone.addEventListener("click", () => input.click());
  zone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") input.click();
  });
  input.addEventListener("change", () => addFiles([...input.files]));
  for (const name of ["dragenter", "dragover"]) {
    zone.addEventListener(name, (event) => {
      event.preventDefault();
      zone.classList.add("drag");
    });
  }
  for (const name of ["dragleave", "drop"]) {
    zone.addEventListener(name, (event) => {
      event.preventDefault();
      zone.classList.remove("drag");
    });
  }
  zone.addEventListener("drop", (event) => addFiles([...event.dataTransfer.files]));
}

function addFiles(files) {
  if (!state.tool || !files.length) return;
  if (!state.tool.multiple || EDITOR_TOOLS[state.tool.name]) {
    state.files = files.slice(0, 1);
  } else {
    state.files.push(...files);
  }
  $("#file-input").value = "";
  renderFileList();
  if (EDITOR_TOOLS[state.tool.name] && state.files.length === 1) {
    openEditor(state.files[0], state.tool.name, loadPdfjs);
  } else if (state.tool.name === "form_fill" && state.files.length === 1) {
    loadFormFields(state.files[0]);
  } else if (state.tool.wants_pages && state.files.length === 1) {
    renderThumbnails(state.files[0]);
  }
}

async function loadFormFields(file) {
  const container = $("#form-fields");
  container.hidden = false;
  container.innerHTML = "<span class='hint'>reading form fields…</span>";
  const body = new FormData();
  body.append("file", file, file.name);
  try {
    const response = await fetch("/api/inspect/form-fields", { method: "POST", body });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "could not read the form");
    if (!payload.fields.length) {
      container.innerHTML = "<span class='hint'>this PDF has no fillable fields</span>";
      return;
    }
    container.innerHTML = "";
    for (const field of payload.fields) {
      const wrap = document.createElement("div");
      wrap.className = "field" + (field.type === "checkbox" ? " check" : "");
      let control;
      if (field.type === "checkbox") {
        control = document.createElement("input");
        control.type = "checkbox";
        control.checked = Boolean(field.value) && field.value !== "/Off";
        control.dataset.onState =
          (field.states || []).find((stateName) => stateName !== "/Off") || "/Yes";
      } else if (field.type === "choice" && field.states?.length) {
        control = document.createElement("select");
        for (const stateName of field.states) {
          const entry = document.createElement("option");
          entry.value = stateName;
          entry.textContent = stateName;
          if (stateName === field.value) entry.selected = true;
          control.appendChild(entry);
        }
      } else {
        control = document.createElement("input");
        control.type = "text";
        control.value = field.value;
      }
      control.dataset.formField = field.name;
      const label = document.createElement("label");
      label.textContent = field.name;
      if (field.type === "checkbox") wrap.append(control, label);
      else wrap.append(label, control);
      container.appendChild(wrap);
    }
  } catch (error) {
    container.hidden = true;
    toast(error.message, "error");
  }
}

function renderFileList() {
  const list = $("#file-list");
  list.innerHTML = "";
  state.files.forEach((file, index) => {
    const item = document.createElement("li");
    item.innerHTML = `<span>📄 ${file.name}</span><span class="size">${prettySize(file.size)}</span>`;
    const remove = document.createElement("button");
    remove.className = "remove";
    remove.textContent = "✕";
    remove.title = "Remove";
    remove.addEventListener("click", () => {
      state.files.splice(index, 1);
      renderFileList();
      if (!state.files.length) {
        $("#thumbs").hidden = true;
        $("#thumbs").innerHTML = "";
      }
    });
    item.appendChild(remove);
    list.appendChild(item);
  });
}

function prettySize(bytes) {
  if (bytes > 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + " MB";
  if (bytes > 1024) return (bytes / 1024).toFixed(0) + " KB";
  return bytes + " B";
}

/* ---------- pdf.js thumbnails ---------- */

async function loadPdfjs() {
  if (state.pdfjs) return state.pdfjs;
  const lib = await import("https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/build/pdf.min.mjs");
  lib.GlobalWorkerOptions.workerSrc =
    "https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/build/pdf.worker.min.mjs";
  state.pdfjs = lib;
  return lib;
}

async function renderThumbnails(file) {
  const container = $("#thumbs");
  container.hidden = false;
  container.innerHTML = "<span class='hint'>rendering pages…</span>";
  let pdf;
  try {
    const pdfjs = await loadPdfjs();
    pdf = await pdfjs.getDocument({ data: await file.arrayBuffer() }).promise;
  } catch {
    container.innerHTML =
      "<span class='hint'>page preview unavailable — type page numbers in the options instead</span>";
    return;
  }

  container.innerHTML = "";
  state.pageOrder = [...Array(pdf.numPages)].map((_, index) => index + 1);
  const mode = state.tool.name === "organize" ? "reorder" : "select";

  for (let number = 1; number <= pdf.numPages; number++) {
    const page = await pdf.getPage(number);
    const viewport = page.getViewport({ scale: 0.35 });
    const canvas = document.createElement("canvas");
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;

    const thumb = document.createElement("div");
    thumb.className = "thumb";
    thumb.dataset.page = number;
    thumb.appendChild(canvas);
    const tag = document.createElement("span");
    tag.className = "num";
    tag.textContent = number;
    thumb.appendChild(tag);

    if (mode === "select") {
      thumb.addEventListener("click", () => {
        const pageNumber = Number(thumb.dataset.page);
        if (state.selectedPages.has(pageNumber)) state.selectedPages.delete(pageNumber);
        else state.selectedPages.add(pageNumber);
        thumb.classList.toggle("selected");
        syncSelectionIntoOptions();
      });
    } else {
      thumb.draggable = true;
      thumb.addEventListener("dragstart", () => thumb.classList.add("dragging"));
      thumb.addEventListener("dragend", () => {
        thumb.classList.remove("dragging");
        syncOrderIntoOptions();
      });
      thumb.addEventListener("dragover", (event) => {
        event.preventDefault();
        const dragging = container.querySelector(".dragging");
        if (dragging && dragging !== thumb) {
          const after = event.offsetX > thumb.offsetWidth / 2;
          container.insertBefore(dragging, after ? thumb.nextSibling : thumb);
        }
      });
    }
    container.appendChild(thumb);
  }
  if (mode === "reorder") {
    $("#hint").textContent = "drag pages to reorder — the order box updates live";
    syncOrderIntoOptions();
  } else {
    $("#hint").textContent = "click pages to select them";
  }
}

function syncSelectionIntoOptions() {
  const input = document.querySelector("#options [name=pages]");
  if (input) input.value = [...state.selectedPages].sort((a, b) => a - b).join(",");
}

function syncOrderIntoOptions() {
  const input = document.querySelector("#options [name=order]");
  if (!input) return;
  const order = [...$("#thumbs").querySelectorAll(".thumb")].map((thumb) => thumb.dataset.page);
  input.value = order.join(",");
}

/* ---------- run ---------- */

async function runTool() {
  const tool = state.tool;
  if (!tool) return;
  if (state.files.length < tool.min_files) {
    toast(`${tool.label} needs at least ${tool.min_files} file(s)`, "error");
    return;
  }
  let extraFiles = [];
  if (EDITOR_TOOLS[tool.name]) {
    if (!editorActive()) {
      toast("add a PDF first", "error");
      return;
    }
    const { elements, images } = collectEditor();
    const payload = tool.name === "redact"
      ? elements.filter((e) => e.type === "rect")
          .map(({ page, x, y, w, h }) => ({ page, x, y, w, h }))
      : elements;
    if (!payload.length) {
      toast("place at least one element on the page first", "error");
      return;
    }
    document.querySelector(`#options [name=${EDITOR_TOOLS[tool.name]}]`).value =
      JSON.stringify(payload);
    if (tool.name === "edit") extraFiles = images;
  }
  if (tool.name === "form_fill") {
    const values = {};
    for (const control of $("#form-fields").querySelectorAll("[data-form-field]")) {
      if (control.type === "checkbox") {
        if (control.checked) values[control.dataset.formField] = control.dataset.onState;
      } else if (control.value !== "") {
        values[control.dataset.formField] = control.value;
      }
    }
    if (!Object.keys(values).length) {
      toast("fill in at least one field", "error");
      return;
    }
    document.querySelector("#options [name=fields]").value = JSON.stringify(values);
  }

  const body = new FormData();
  for (const file of state.files) body.append("files", file, file.name);
  for (const file of extraFiles) body.append("files", file, file.name);
  for (const element of $("#options").elements) {
    if (!element.name) continue;
    body.append(element.name, element.type === "checkbox" ? element.checked : element.value);
  }

  const button = $("#run");
  button.disabled = true;
  button.classList.add("working");
  const uploadedBytes = state.files.reduce((sum, file) => sum + file.size, 0);

  try {
    const response = await fetch(`/api/tools/${tool.name}`, { method: "POST", body });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || `the server answered ${response.status}`);
    }
    const blob = await response.blob();
    const disposition = response.headers.get("Content-Disposition") || "";
    const match = /filename="([^"]+)"/.exec(disposition);
    const filename = decodeURIComponent(match ? match[1] : "result");

    const url = URL.createObjectURL(blob);
    const download = $("#download");
    download.href = url;
    download.download = filename;
    $("#result-name").textContent = filename;
    $("#result-meta").textContent = resultMeta(uploadedBytes, blob.size);
    $("#result").hidden = false;
    $("#result").scrollIntoView({ behavior: "smooth", block: "nearest" });
    toast("Done — your file is ready", "ok");
  } catch (error) {
    toast(error.message, "error");
  } finally {
    button.disabled = false;
    button.classList.remove("working");
  }
}

function resultMeta(before, after) {
  const text = `${prettySize(after)}`;
  if (state.tool.name === "compress" && before > 0) {
    const saved = Math.max(0, 100 - (after / before) * 100);
    return `${text} — ${saved.toFixed(0)}% smaller than the ${prettySize(before)} you uploaded`;
  }
  return text;
}

/* ---------- toasts ---------- */

function toast(message, kind = "") {
  const element = document.createElement("div");
  element.className = `toast ${kind}`;
  element.textContent = message;
  $("#toasts").appendChild(element);
  setTimeout(() => element.remove(), 5200);
}
