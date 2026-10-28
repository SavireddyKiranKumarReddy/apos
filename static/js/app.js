/* Advanced Professional Suite - Frontend */
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const state = {
  tools: [],
  tool: null,
  files: [],
  result: null,
};

const CATEGORIES = [
  ["organize", "Merge & Split"],
  ["convert", "Convert"],
  ["optimize", "Optimize"],
  ["edit", "Edit & Create"],
  ["secure", "Security & Sign"],
  ["intelligence", "OCR & AI"],
];

async function init() {
  try {
    const response = await fetch("/api/tools");
    const payload = await response.json();
    state.tools = payload.tools || [];
    renderCategoryRows();
    setupEventListeners();
    setupDropzone();
    route();
  } catch (err) {
    console.error(err);
    toast("Failed to load tools. Please refresh the page.", "error");
  }
}

function renderCategoryRows() {
  const container = $("#category-rows");
  if (!container) return;
  container.innerHTML = "";
  
  for (const [catKey, catTitle] of CATEGORIES) {
    const tools = state.tools.filter(t => t.category === catKey && t.available);
    if (tools.length === 0) continue;
    
    const section = document.createElement("section");
    section.className = "category-section";
    section.innerHTML = `
      <div class="category-header">
        <h3 class="category-title">
          <span>${getCategoryIcon(catKey)}</span> ${catTitle}
        </h3>
      </div>
      <div class="tools-grid">
        ${tools.map(tool => `
          <a href="/tool/${tool.name}" class="tool-card" data-route="/tool/${tool.name}">
            <div class="tool-icon">${tool.icon}</div>
            <div class="tool-info">
              <div class="tool-name">${escapeHtml(tool.label)}</div>
              <div class="tool-desc">${escapeHtml(tool.description)}</div>
            </div>
          </a>
        `).join('')}
      </div>
    `;
    container.appendChild(section);
  }
  
  // Handle tool card clicks
  $$(".tool-card").forEach(card => {
    card.addEventListener("click", (e) => {
      e.preventDefault();
      const href = card.getAttribute("href");
      navigate(href);
    });
  });
}

function getCategoryIcon(cat) {
  const icons = {
    organize: "📁",
    convert: "🔄",
    optimize: "🗜️",
    edit: "✏️",
    secure: "🔐",
    intelligence: "🧠",
  };
  return icons[cat] || "🛠️";
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function setupEventListeners() {
  // Search
  $("#search")?.addEventListener("input", (e) => {
    const query = e.target.value.toLowerCase();
    if (query) {
      filterTools(query);
    } else {
      renderCategoryRows();
    }
  });
  
  // Quick tools
  $$("[data-open-tool]").forEach(btn => {
    btn.addEventListener("click", () => {
      navigate(`/tool/${btn.dataset.openTool}`);
    });
  });
  
  // Footer links
  $$("footer a[data-open-tool]").forEach(link => {
    link.addEventListener("click", (e) => {
      e.preventDefault();
      navigate(`/tool/${link.dataset.openTool}`);
    });
  });
  
  // Back button
  $("#back")?.addEventListener("click", () => navigate("/"));
  $("#again")?.addEventListener("click", () => {
    state.files = [];
    state.result = null;
    navigate("/tool/" + state.tool?.name);
  });
  $("#done-home")?.addEventListener("click", () => navigate("/"));
  
  // Run button
  $("#run")?.addEventListener("click", runTool);
  
  // Keyboard shortcut
  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && document.activeElement !== $("#search")) {
      e.preventDefault();
      $("#search")?.focus();
    }
    if (e.key === "Escape") {
      if ($("#tool") && !$("#tool").hidden) navigate("/");
    }
  });
}

function filterTools(query) {
  const container = $("#category-rows");
  if (!container) return;
  container.innerHTML = "";
  
  const matches = state.tools.filter(t => 
    t.available && (
      t.label.toLowerCase().includes(query) ||
      t.description.toLowerCase().includes(query)
    )
  );
  
  if (matches.length === 0) {
    container.innerHTML = '<p style="text-align: center; color: var(--text-secondary); padding: 40px;">No tools found</p>';
    return;
  }
  
  const section = document.createElement("section");
  section.className = "category-section";
  section.innerHTML = `
    <div class="category-header">
      <h3 class="category-title">Search Results</h3>
    </div>
    <div class="tools-grid">
      ${matches.map(tool => `
        <a href="/tool/${tool.name}" class="tool-card" data-route="/tool/${tool.name}">
          <div class="tool-icon">${tool.icon}</div>
          <div class="tool-info">
            <div class="tool-name">${escapeHtml(tool.label)}</div>
            <div class="tool-desc">${escapeHtml(tool.description)}</div>
          </div>
        </a>
      `).join('')}
    </div>
  `;
  container.appendChild(section);
  
  $$(".tool-card").forEach(card => {
    card.addEventListener("click", (e) => {
      e.preventDefault();
      navigate(card.getAttribute("href"));
    });
  });
}

function setupDropzone() {
  const dropzone = $("#dropzone");
  const input = $("#file-input");
  
  if (!dropzone || !input) return;
  
  dropzone.addEventListener("click", () => input.click());
  
  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.style.borderColor = "var(--red)";
    dropzone.style.background = "#fef7f7";
  });
  
  dropzone.addEventListener("dragleave", () => {
    dropzone.style.borderColor = "var(--border)";
    dropzone.style.background = "var(--bg-gray)";
  });
  
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.style.borderColor = "var(--border)";
    dropzone.style.background = "var(--bg-gray)";
    const files = Array.from(e.dataTransfer.files);
    addFiles(files);
  });
  
  input.addEventListener("change", (e) => {
    const files = Array.from(e.target.files);
    addFiles(files);
    input.value = "";
  });
}

function addFiles(files) {
  state.files = [...state.files, ...files];
  renderFileList();
}

function renderFileList() {
  const list = $("#file-list");
  if (!list) return;
  list.innerHTML = "";
  
  state.files.forEach((file, idx) => {
    const li = document.createElement("li");
    li.className = "file-item";
    li.innerHTML = `
      <span class="file-icon">📄</span>
      <span class="file-name">${escapeHtml(file.name)} (${formatSize(file.size)})</span>
      <button class="file-remove" onclick="removeFile(${idx})">×</button>
    `;
    list.appendChild(li);
  });
}

window.removeFile = function(idx) {
  state.files.splice(idx, 1);
  renderFileList();
};

function formatSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

function navigate(path) {
  history.pushState({}, "", path);
  route();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function route() {
  const path = location.pathname;
  
  if (path === "/" || path === "") {
    $("#home").hidden = false;
    $("#tool").hidden = true;
    $("#result-page").hidden = true;
    return;
  }
  
  if (path.startsWith("/tool/")) {
    const toolName = path.split("/tool/")[1].split("/")[0];
    const tool = state.tools.find(t => t.name === toolName);
    if (!tool) {
      toast("Tool not found", "error");
      navigate("/");
      return;
    }
    showToolPage(tool);
    return;
  }
  
  $("#home").hidden = false;
  $("#tool").hidden = true;
  $("#result-page").hidden = true;
}

function showToolPage(tool) {
  state.tool = tool;
  state.files = [];
  
  $("#home").hidden = true;
  $("#tool").hidden = false;
  $("#result-page").hidden = true;
  
  $("#tool-icon").textContent = tool.icon;
  $("#tool-title").textContent = tool.label;
  $("#tool-desc").textContent = tool.description;
  
  $("#file-list").innerHTML = "";
  $("#run").disabled = false;
  $("#run").textContent = "Process Files";
  $("#hint").textContent = "";
  
  // Handle file input accept
  const input = $("#file-input");
  if (input) {
    input.accept = tool.accepts || ".pdf";
    input.multiple = tool.multiple || false;
  }
}

async function runTool() {
  if (!state.tool) return;
  if (state.files.length < (state.tool.min_files || 1)) {
    toast(`Please select at least ${state.tool.min_files || 1} file(s)`, "error");
    return;
  }
  
  const formData = new FormData();
  state.files.forEach(f => formData.append("files", f));
  
  // Add options (empty for now, can be extended)
  const optionsForm = $("#options");
  if (optionsForm) {
    const inputs = optionsForm.querySelectorAll("input, select, textarea");
    inputs.forEach(input => {
      if (input.name && input.value) {
        formData.append(input.name, input.value);
      }
    });
  }
  
  const btn = $("#run");
  btn.disabled = true;
  btn.textContent = "Processing...";
  
  try {
    const response = await fetch(`/api/tools/${state.tool.name}`, {
      method: "POST",
      body: formData,
    });
    
    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.error || "Processing failed");
    }
    
    const blob = await response.blob();
    const contentDisposition = response.headers.get("Content-Disposition") || "";
    const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/);
    const filename = filenameMatch ? filenameMatch[1] : `${state.tool.name}_result.pdf`;
    
    showResult(blob, filename);
  } catch (err) {
    toast(err.message, "error");
    btn.disabled = false;
    btn.textContent = "Process Files";
  }
}

function showResult(blob, filename) {
  $("#home").hidden = true;
  $("#tool").hidden = true;
  $("#result-page").hidden = false;
  
  $("#done-title").textContent = "Your file is ready!";
  $("#done-meta").textContent = `Processed with ${state.tool.label}`;
  $("#done-name").textContent = filename;
  
  const url = URL.createObjectURL(blob);
  const downloadBtn = $("#download");
  downloadBtn.href = url;
  downloadBtn.download = filename;
  
  $("#run").disabled = false;
  $("#run").textContent = "Process Files";
}

function toast(message, type = "info") {
  const container = $("#toasts");
  if (!container) return;
  
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = message;
  container.appendChild(el);
  
  setTimeout(() => {
    el.style.opacity = "0";
    el.style.transition = "opacity 0.3s";
    setTimeout(() => el.remove(), 300);
  }, 3000);
}

// Mobile nav toggle
function setupMobileNav() {
  // Add mobile menu button if needed
}

// Initialize on DOM ready
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}

// Handle back/forward
window.addEventListener("popstate", route);
