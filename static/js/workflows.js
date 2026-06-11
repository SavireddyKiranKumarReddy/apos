/* Workflows: chain tools into reusable pipelines.

   Saved workflows live in localStorage — consistent with pdfsmith's
   no-accounts, nothing-stored-server-side stance. Runs go to
   POST /api/workflows/run as files + a steps JSON array. */

const $ = (selector) => document.querySelector(selector);
const STORE_KEY = "pdfsmith-workflows";

const wf = {
  tools: [],          // chainable tool descriptors from /api/tools
  current: null,      // {id, name, steps: [{tool, options}]}
  files: [],
  onExit: null,
};

/* ---------- storage ---------- */

export function savedWorkflows() {
  try {
    return JSON.parse(localStorage.getItem(STORE_KEY)) || [];
  } catch {
    return [];
  }
}

function persist(list) {
  localStorage.setItem(STORE_KEY, JSON.stringify(list));
}

export function deleteWorkflow(id) {
  persist(savedWorkflows().filter((entry) => entry.id !== id));
}

/* ---------- wiring ---------- */

export function initWorkflows(allTools, { onExit }) {
  wf.tools = allTools.filter(
    (tool) => tool.available && !tool.interactive && tool.name !== "merge_noop"
  );
  wf.onExit = onExit;

  const picker = $("#wf-tool-pick");
  picker.innerHTML = "";
  for (const tool of wf.tools) {
    const option = document.createElement("option");
    option.value = tool.name;
    option.textContent = `${tool.icon} ${tool.label}`;
    picker.appendChild(option);
  }

  $("#wf-back").addEventListener("click", () => exitEditor());
  $("#wf-add-step").addEventListener("click", () => {
    addStep(picker.value);
  });
  $("#wf-save").addEventListener("click", saveCurrent);
  $("#wf-run").addEventListener("click", runCurrent);
  $("#wf-name-input").addEventListener("input", (event) => {
    wf.current.name = event.target.value;
  });

  const zone = $("#wf-dropzone");
  const input = $("#wf-file-input");
  zone.addEventListener("click", () => input.click());
  input.addEventListener("change", () => {
    wf.files.push(...input.files);
    input.value = "";
    renderFiles();
  });
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
  zone.addEventListener("drop", (event) => {
    wf.files.push(...event.dataTransfer.files);
    renderFiles();
  });
}

/* ---------- the workflows tab grid ---------- */

export function renderWorkflowsGrid(container, toast) {
  container.innerHTML = "";

  const create = document.createElement("button");
  create.className = "card wf-create";
  create.innerHTML = `<span class="icon">⚡</span><h3>Create a workflow</h3>
    <p>Chain your favorite tools, run them on any files, reuse anytime.
    Free and unlimited.</p>`;
  create.addEventListener("click", () => openEditor(null));
  container.appendChild(create);

  for (const saved of savedWorkflows()) {
    const card = document.createElement("div");
    card.className = "card wf-card";
    const stepsLine = saved.steps
      .map((step) => labelFor(step.tool))
      .join(" → ");
    card.innerHTML = `<span class="icon">🧰</span><h3>${escapeHtml(saved.name)}</h3>
      <p>${escapeHtml(stepsLine)}</p>`;
    const row = document.createElement("div");
    row.className = "wf-card-actions";
    const open = document.createElement("button");
    open.className = "ghost small";
    open.textContent = "Open";
    open.addEventListener("click", () => openEditor(saved));
    const remove = document.createElement("button");
    remove.className = "ghost small";
    remove.textContent = "Delete";
    remove.addEventListener("click", () => {
      deleteWorkflow(saved.id);
      renderWorkflowsGrid(container, toast);
      toast("Workflow deleted", "ok");
    });
    row.append(open, remove);
    card.appendChild(row);
    container.appendChild(card);
  }
}

function labelFor(name) {
  const tool = wf.tools.find((entry) => entry.name === name);
  return tool ? tool.label : name;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

/* ---------- editor ---------- */

export function openEditor(saved) {
  wf.current = saved
    ? structuredClone(saved)
    : { id: `wf-${Math.random().toString(36).slice(2, 10)}`, name: "", steps: [] };
  wf.files = [];
  $("#home").hidden = true;
  $("#tool").hidden = true;
  $("#workflow-editor").hidden = false;
  $("#wf-title").textContent = saved ? saved.name : "New workflow";
  $("#wf-name-input").value = wf.current.name;
  $("#wf-result").hidden = true;
  renderSteps();
  renderFiles();
}

function exitEditor() {
  $("#workflow-editor").hidden = true;
  wf.onExit?.();
}

function addStep(toolName) {
  const tool = wf.tools.find((entry) => entry.name === toolName);
  if (!tool) return;
  wf.current.steps.push({ tool: tool.name, options: defaults(tool) });
  renderSteps();
}

function defaults(tool) {
  const options = {};
  for (const option of tool.options) {
    if (option.default !== null && option.default !== undefined) {
      options[option.name] = String(option.default);
    }
  }
  return options;
}

function renderSteps() {
  const list = $("#wf-steps");
  list.innerHTML = "";
  if (!wf.current.steps.length) {
    list.innerHTML = "<li class='wf-empty'>No steps yet — pick a tool below.</li>";
  }
  wf.current.steps.forEach((step, index) => {
    const tool = wf.tools.find((entry) => entry.name === step.tool);
    const item = document.createElement("li");
    item.className = "wf-step";

    const head = document.createElement("div");
    head.className = "wf-step-head";
    head.innerHTML = `<span class="wf-step-num">${index + 1}</span>
      <span class="wf-step-label">${tool ? tool.icon + " " + tool.label : step.tool}</span>`;
    const controls = document.createElement("div");
    controls.className = "wf-step-controls";
    for (const [symbol, action] of [["↑", -1], ["↓", 1]]) {
      const button = document.createElement("button");
      button.className = "ghost small";
      button.textContent = symbol;
      button.title = action < 0 ? "Move up" : "Move down";
      button.addEventListener("click", () => {
        const target = index + action;
        if (target < 0 || target >= wf.current.steps.length) return;
        const [moved] = wf.current.steps.splice(index, 1);
        wf.current.steps.splice(target, 0, moved);
        renderSteps();
      });
      controls.appendChild(button);
    }
    const remove = document.createElement("button");
    remove.className = "ghost small";
    remove.textContent = "✕";
    remove.title = "Remove step";
    remove.addEventListener("click", () => {
      wf.current.steps.splice(index, 1);
      renderSteps();
    });
    controls.appendChild(remove);
    head.appendChild(controls);
    item.appendChild(head);

    if (tool?.options.length) {
      const optionsRow = document.createElement("div");
      optionsRow.className = "wf-step-options";
      for (const option of tool.options) {
        const wrap = document.createElement("label");
        wrap.className = "wf-opt";
        wrap.textContent = option.label;
        let control;
        if (option.kind === "select") {
          control = document.createElement("select");
          for (const choice of option.choices) {
            const entry = document.createElement("option");
            entry.value = choice.value;
            entry.textContent = choice.label;
            if (choice.value === step.options[option.name]) entry.selected = true;
            control.appendChild(entry);
          }
        } else if (option.kind === "checkbox") {
          control = document.createElement("input");
          control.type = "checkbox";
          control.checked = step.options[option.name] === "true";
        } else {
          control = document.createElement("input");
          control.type = option.kind === "number" ? "number" : "text";
          control.value = step.options[option.name] ?? "";
        }
        control.addEventListener("change", () => {
          step.options[option.name] =
            control.type === "checkbox" ? String(control.checked) : control.value;
        });
        wrap.appendChild(control);
        optionsRow.appendChild(wrap);
      }
      item.appendChild(optionsRow);
    }
    list.appendChild(item);
  });
  validateChain();
}

function validateChain() {
  const hint = $("#wf-hint");
  const steps = wf.current.steps;
  for (let index = 0; index < steps.length; index++) {
    const tool = wf.tools.find((entry) => entry.name === steps[index].tool);
    if (!tool) continue;
    if (index < steps.length - 1 && !tool.produces_pdf) {
      hint.textContent = `⚠ ${tool.label} doesn't produce a PDF — make it the last step`;
      return false;
    }
    if (index > 0 && !tool.accepts.includes(".pdf")) {
      hint.textContent = `⚠ ${tool.label} doesn't take PDF input — it can only be step 1`;
      return false;
    }
  }
  hint.textContent = steps.length
    ? "files flow top to bottom"
    : "";
  return true;
}

function renderFiles() {
  const list = $("#wf-file-list");
  list.innerHTML = "";
  wf.files.forEach((file, index) => {
    const item = document.createElement("li");
    item.innerHTML = `<span>📄 ${file.name}</span>`;
    const remove = document.createElement("button");
    remove.className = "remove";
    remove.textContent = "✕";
    remove.addEventListener("click", () => {
      wf.files.splice(index, 1);
      renderFiles();
    });
    item.appendChild(remove);
    list.appendChild(item);
  });
}

/* ---------- save & run ---------- */

let notify = () => {};
export function setWorkflowToast(fn) {
  notify = fn;
}

function saveCurrent() {
  if (!wf.current.name.trim()) {
    notify("Give the workflow a name first", "error");
    return;
  }
  if (!wf.current.steps.length) {
    notify("Add at least one step", "error");
    return;
  }
  const list = savedWorkflows().filter((entry) => entry.id !== wf.current.id);
  list.push(structuredClone(wf.current));
  persist(list);
  $("#wf-title").textContent = wf.current.name;
  notify("Workflow saved — find it under the Workflows tab", "ok");
}

async function runCurrent() {
  if (!wf.current.steps.length) {
    notify("Add at least one step", "error");
    return;
  }
  if (!wf.files.length) {
    notify("Add the files to run this on", "error");
    return;
  }
  if (!validateChain()) {
    notify("Fix the step order first", "error");
    return;
  }

  const body = new FormData();
  for (const file of wf.files) body.append("files", file, file.name);
  body.append("steps", JSON.stringify(wf.current.steps));

  const button = $("#wf-run");
  button.disabled = true;
  button.classList.add("working");
  try {
    const response = await fetch("/api/workflows/run", { method: "POST", body });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || `the server answered ${response.status}`);
    }
    const blob = await response.blob();
    const disposition = response.headers.get("Content-Disposition") || "";
    const match = /filename="([^"]+)"/.exec(disposition);
    const filename = decodeURIComponent(match ? match[1] : "workflow-result");
    const download = $("#wf-download");
    download.href = URL.createObjectURL(blob);
    download.download = filename;
    $("#wf-result-name").textContent = filename;
    $("#wf-result-meta").textContent =
      `${wf.current.steps.length} steps · ${wf.files.length} file(s) in`;
    $("#wf-result").hidden = false;
    notify("Workflow finished", "ok");
  } catch (error) {
    notify(error.message, "error");
  } finally {
    button.disabled = false;
    button.classList.remove("working");
  }
}
