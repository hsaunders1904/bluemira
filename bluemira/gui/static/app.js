/**
 * Bluemira Interactive Parameter Twiddler, 2D Preview, 3D CAD & Sweep Studio.
 */

// Application state
let state = {
  schema: [],
  diff: {},
  activeComponent: "all",
  searchQuery: "",
  activeView: "2d", // "2d" or "3d"
  plasmaShape: null,
  cadMesh: null,
  cutawayDeg: 90,
  visibility: {
    plasma: true,
    blanket: true,
    vacuum_vessel: true,
    tf_coils: true,
  },
  wireframe: false,
  lastScanData: null,
};

// 3D Viewport camera state
const camera3D = {
  rotX: -0.4,
  rotY: 0.6,
  distance: 36,
  isDragging: false,
  lastMouseX: 0,
  lastMouseY: 0,
};

// DOM references
const dom = {
  componentNav: document.getElementById("componentNav"),
  paramsGrid: document.getElementById("paramsGrid"),
  searchInput: document.getElementById("searchInput"),
  clearSearch: document.getElementById("clearSearch"),
  paramCountDisplay: document.getElementById("paramCountDisplay"),
  diffBadge: document.getElementById("diffBadge"),
  diffCountText: document.getElementById("diffCountText"),
  btnResetAll: document.getElementById("btnResetAll"),
  btnToggleDiff: document.getElementById("btnToggleDiff"),
  diffDrawer: document.getElementById("diffDrawer"),
  btnCloseDiff: document.getElementById("btnCloseDiff"),
  diffList: document.getElementById("diffList"),
  tab2D: document.getElementById("tab2D"),
  tab3D: document.getElementById("tab3D"),
  container2D: document.getElementById("container2D"),
  container3D: document.getElementById("container3D"),
  canvas2D: document.getElementById("poloidalCanvas"),
  canvas3D: document.getElementById("cad3dCanvas"),
  coordsOverlay: document.getElementById("coordsOverlay"),
  metricAspect: document.getElementById("metricAspect"),
  metricKappa: document.getElementById("metricKappa"),
  metricDelta: document.getElementById("metricDelta"),
  cutawaySlider: document.getElementById("cutawaySlider"),
  cutawayVal: document.getElementById("cutawayVal"),
  togglePlasma: document.getElementById("togglePlasma"),
  toggleBlanket: document.getElementById("toggleBlanket"),
  toggleVV: document.getElementById("toggleVV"),
  toggleTF: document.getElementById("toggleTF"),
  toggleWireframe: document.getElementById("toggleWireframe"),
  // Sweep Studio Modal
  btnOpenScan: document.getElementById("btnOpenScan"),
  btnCloseScan: document.getElementById("btnCloseScan"),
  scanModal: document.getElementById("scanModal"),
  scanParamSelect: document.getElementById("scanParamSelect"),
  scanMin: document.getElementById("scanMin"),
  scanMax: document.getElementById("scanMax"),
  scanSteps: document.getElementById("scanSteps"),
  btnRunSweep: document.getElementById("btnRunSweep"),
  scanExportControls: document.getElementById("scanExportControls"),
  scanChartCanvas: document.getElementById("scanChartCanvas"),
  scanTableBody: document.getElementById("scanTableBody"),
  chartLegend: document.getElementById("chartLegend"),
};

// Initialize
document.addEventListener("DOMContentLoaded", async () => {
  setupEventListeners();
  await loadSchema();
  await update2DPreview();
  await update3DPreview();
});

function setupEventListeners() {
  // Tab switching
  dom.tab2D.addEventListener("click", () => switchView("2d"));
  dom.tab3D.addEventListener("click", () => switchView("3d"));

  // Search & Filter
  dom.searchInput.addEventListener("input", (e) => {
    state.searchQuery = e.target.value.toLowerCase();
    renderCards();
  });

  dom.clearSearch.addEventListener("click", () => {
    dom.searchInput.value = "";
    state.searchQuery = "";
    renderCards();
  });

  // Diff drawer
  dom.btnToggleDiff.addEventListener("click", () => {
    dom.diffDrawer.classList.toggle("open");
  });

  dom.btnCloseDiff.addEventListener("click", () => {
    dom.diffDrawer.classList.remove("open");
  });

  // Reset All
  dom.btnResetAll.addEventListener("click", async () => {
    if (confirm("Reset all modified parameters back to baseline values?")) {
      const res = await fetch("/api/reset_all", { method: "POST" });
      if (res.ok) {
        await loadSchema();
        await update2DPreview();
        await update3DPreview();
      }
    }
  });

  // Sweep Studio Modal
  dom.btnOpenScan.addEventListener("click", () => {
    populateScanParams();
    dom.scanModal.classList.add("open");
  });

  dom.btnCloseScan.addEventListener("click", () => {
    dom.scanModal.classList.remove("open");
  });

  dom.btnRunSweep.addEventListener("click", async () => {
    await runParameterSweep();
  });

  // Track 2D cursor
  dom.canvas2D.addEventListener("mousemove", (e) => {
    const rect = dom.canvas2D.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const coords = canvasToPhysicalCoords(x, y);
    dom.coordsOverlay.textContent = `R: ${coords.r.toFixed(2)} m | Z: ${coords.z.toFixed(2)} m`;
  });

  // 3D Canvas Orbit Controls
  dom.canvas3D.addEventListener("mousedown", (e) => {
    camera3D.isDragging = true;
    camera3D.lastMouseX = e.clientX;
    camera3D.lastMouseY = e.clientY;
  });

  window.addEventListener("mouseup", () => {
    camera3D.isDragging = false;
  });

  dom.canvas3D.addEventListener("mousemove", (e) => {
    if (!camera3D.isDragging) return;
    const dx = e.clientX - camera3D.lastMouseX;
    const dy = e.clientY - camera3D.lastMouseY;
    camera3D.rotY += dx * 0.01;
    camera3D.rotX += dy * 0.01;
    camera3D.rotX = Math.max(-Math.PI / 2 + 0.1, Math.min(Math.PI / 2 - 0.1, camera3D.rotX));
    camera3D.lastMouseX = e.clientX;
    camera3D.lastMouseY = e.clientY;
    render3DCanvas();
  });

  dom.canvas3D.addEventListener("wheel", (e) => {
    e.preventDefault();
    camera3D.distance += e.deltaY * 0.03;
    camera3D.distance = Math.max(12, Math.min(80, camera3D.distance));
    render3DCanvas();
  }, { passive: false });

  // 3D Controls
  dom.cutawaySlider.addEventListener("input", (e) => {
    state.cutawayDeg = parseFloat(e.target.value);
    dom.cutawayVal.textContent = `${state.cutawayDeg}°`;
    debounced3DUpdate();
  });

  dom.togglePlasma.addEventListener("change", (e) => {
    state.visibility.plasma = e.target.checked;
    render3DCanvas();
  });
  dom.toggleBlanket.addEventListener("change", (e) => {
    state.visibility.blanket = e.target.checked;
    render3DCanvas();
  });
  dom.toggleVV.addEventListener("change", (e) => {
    state.visibility.vacuum_vessel = e.target.checked;
    render3DCanvas();
  });
  dom.toggleTF.addEventListener("change", (e) => {
    state.visibility.tf_coils = e.target.checked;
    render3DCanvas();
  });
  dom.toggleWireframe.addEventListener("change", (e) => {
    state.wireframe = e.target.checked;
    render3DCanvas();
  });
}

function switchView(view) {
  state.activeView = view;
  if (view === "2d") {
    dom.tab2D.classList.add("active");
    dom.tab3D.classList.remove("active");
    dom.container2D.classList.add("active");
    dom.container3D.classList.remove("active");
    renderCanvas();
  } else {
    dom.tab3D.classList.add("active");
    dom.tab2D.classList.remove("active");
    dom.container3D.classList.add("active");
    dom.container2D.classList.remove("active");
    render3DCanvas();
  }
}

async function loadSchema() {
  try {
    const res = await fetch("/api/schema");
    const data = await res.json();
    state.schema = data.schema || [];
    state.diff = data.diff || {};
    updateDiffBadge();
    renderSidebar();
    renderCards();
    renderDiffDrawer();
  } catch (err) {
    console.error("Failed to load configuration schema:", err);
  }
}

function populateScanParams() {
  dom.scanParamSelect.innerHTML = "";
  const numericParams = state.schema.filter((p) => typeof p.value === "number");
  numericParams.forEach((p) => {
    const opt = document.createElement("option");
    opt.value = p.path;
    opt.textContent = `${p.path} (${p.value}${p.unit ? ' ' + p.unit : ''})`;
    if (p.path.includes("r_0") || p.path.includes("major_radius")) {
      opt.selected = true;
    }
    dom.scanParamSelect.appendChild(opt);
  });
}

async function runParameterSweep() {
  const path = dom.scanParamSelect.value;
  const min = parseFloat(dom.scanMin.value);
  const max = parseFloat(dom.scanMax.value);
  const steps = parseInt(dom.scanSteps.value, 10);

  if (isNaN(min) || isNaN(max) || isNaN(steps) || steps < 2) {
    alert("Please enter valid range and step numbers.");
    return;
  }

  // Generate sequence of values
  const values = [];
  const stepSize = (max - min) / (steps - 1);
  for (let i = 0; i < steps; i++) {
    values.push(parseFloat((min + i * stepSize).toFixed(4)));
  }

  dom.btnRunSweep.textContent = "⏳ Running...";
  dom.btnRunSweep.disabled = true;

  try {
    const res = await fetch("/api/scan/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        variables: [{ name: path, values }],
      }),
    });

    if (res.ok) {
      const scanResult = await res.json();
      state.lastScanData = scanResult;
      renderScanResults(scanResult, path);
      dom.scanExportControls.style.display = "flex";
    } else {
      const err = await res.json();
      alert(`Sweep failed: ${err.error || 'Unknown error'}`);
    }
  } catch (err) {
    console.error("Error executing scan:", err);
    alert(`Sweep error: ${err.message}`);
  } finally {
    dom.btnRunSweep.textContent = "▶ Run Sweep";
    dom.btnRunSweep.disabled = false;
  }
}

function renderScanResults(result, paramName) {
  const points = result.points || [];
  dom.scanTableBody.innerHTML = "";

  if (points.length === 0) {
    dom.scanTableBody.innerHTML = `<tr><td colspan="6" class="table-empty">No results generated</td></tr>`;
    return;
  }

  // Populate Table
  points.forEach((p, idx) => {
    const val = p.variables[paramName];
    const aspect = p.metrics.aspect_ratio || "-";
    const vol = p.metrics.plasma_volume || "-";

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${idx + 1}</td>
      <td><span class="live-pill" style="font-size: 0.65rem;">${p.status}</span></td>
      <td>${val}</td>
      <td>${aspect}</td>
      <td>${vol}</td>
      <td><button class="btn-table-apply" data-index="${idx}">Apply</button></td>
    `;

    tr.querySelector(".btn-table-apply").addEventListener("click", async () => {
      await applyScanPoint(idx);
    });

    dom.scanTableBody.appendChild(tr);
  });

  // Render Sensitivity Chart
  renderScanChart(points, paramName);
}

async function applyScanPoint(pointIndex) {
  try {
    const res = await fetch("/api/scan/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ point_index: pointIndex }),
    });

    if (res.ok) {
      const data = await res.json();
      state.diff = data.diff || {};
      state.schema = data.schema || [];
      updateDiffBadge();
      renderCards();
      renderDiffDrawer();
      await update2DPreview();
      await update3DPreview();
      alert(`Applied scan point #${pointIndex + 1} to working configuration.`);
    }
  } catch (err) {
    console.error("Error applying scan point:", err);
  }
}

function renderScanChart(points, paramName) {
  const canvas = dom.scanChartCanvas;
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;

  ctx.clearRect(0, 0, w, h);

  const xVals = points.map((p) => p.variables[paramName]);
  const yAspect = points.map((p) => p.metrics.aspect_ratio || 0);
  const yVol = points.map((p) => p.metrics.plasma_volume || 0);

  const xMin = Math.min(...xVals);
  const xMax = Math.max(...xVals);
  const yAspectMin = Math.min(...yAspect);
  const yAspectMax = Math.max(...yAspect);

  const padding = { left: 45, right: 45, top: 25, bottom: 35 };
  const plotW = w - padding.left - padding.right;
  const plotH = h - padding.top - padding.bottom;

  // Gridlines
  ctx.strokeStyle = "#1c2738";
  ctx.lineWidth = 1;

  for (let i = 0; i <= 4; i++) {
    const y = padding.top + (i / 4) * plotH;
    ctx.beginPath();
    ctx.moveTo(padding.left, y);
    ctx.lineTo(w - padding.right, y);
    ctx.stroke();

    const val = (yAspectMax - (i / 4) * (yAspectMax - yAspectMin)).toFixed(2);
    ctx.fillStyle = "#00e5ff";
    ctx.font = "10px JetBrains Mono";
    ctx.textAlign = "right";
    ctx.fillText(val, padding.left - 6, y + 3);
  }

  // Plot aspect ratio line
  ctx.strokeStyle = "#00e5ff";
  ctx.lineWidth = 2.5;
  ctx.beginPath();

  points.forEach((p, i) => {
    const x = padding.left + ((xVals[i] - xMin) / (xMax - xMin || 1)) * plotW;
    const y = padding.top + (1 - (yAspect[i] - yAspectMin) / (yAspectMax - yAspectMin || 1)) * plotH;

    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  // Plot points
  points.forEach((p, i) => {
    const x = padding.left + ((xVals[i] - xMin) / (xMax - xMin || 1)) * plotW;
    const y = padding.top + (1 - (yAspect[i] - yAspectMin) / (yAspectMax - yAspectMin || 1)) * plotH;

    ctx.fillStyle = "#ffffff";
    ctx.beginPath();
    ctx.arc(x, y, 4, 0, 2 * Math.PI);
    ctx.fill();

    // X axis labels
    ctx.fillStyle = "#8fa2b7";
    ctx.font = "10px JetBrains Mono";
    ctx.textAlign = "center";
    ctx.fillText(xVals[i].toFixed(2), x, h - 12);
  });

  dom.chartLegend.innerHTML = `
    <span style="color: #00e5ff;">― Aspect Ratio (left axis)</span>
  `;
}

function updateDiffBadge() {
  const count = Object.keys(state.diff).length;
  dom.diffCountText.textContent = `${count} modified`;
  if (count > 0) {
    dom.diffBadge.classList.remove("synced");
  } else {
    dom.diffBadge.classList.add("synced");
  }
}

function renderSidebar() {
  const components = new Set();
  state.schema.forEach((item) => {
    if (item.component) components.add(item.component);
  });

  dom.componentNav.innerHTML = `
    <li class="nav-item ${state.activeComponent === 'all' ? 'active' : ''}" data-component="all">
      <span class="nav-icon">▤</span> All Parameters
    </li>
  `;

  Array.from(components).sort().forEach((comp) => {
    const li = document.createElement("li");
    li.className = `nav-item ${state.activeComponent === comp ? 'active' : ''}`;
    li.dataset.component = comp;
    li.innerHTML = `<span class="nav-icon">◈</span> ${formatTitle(comp)}`;
    li.addEventListener("click", () => {
      document.querySelectorAll(".nav-item").forEach((el) => el.classList.remove("active"));
      li.classList.add("active");
      state.activeComponent = comp;
      renderCards();
    });
    dom.componentNav.appendChild(li);
  });

  dom.componentNav.firstElementChild.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach((el) => el.classList.remove("active"));
    dom.componentNav.firstElementChild.classList.add("active");
    state.activeComponent = "all";
    renderCards();
  });
}

function renderCards() {
  const filtered = state.schema.filter((p) => {
    const matchComp = state.activeComponent === "all" || p.component === state.activeComponent;
    const matchQuery =
      !state.searchQuery ||
      p.path.toLowerCase().includes(state.searchQuery) ||
      p.name.toLowerCase().includes(state.searchQuery) ||
      (p.description && p.description.toLowerCase().includes(state.searchQuery));
    return matchComp && matchQuery;
  });

  dom.paramCountDisplay.textContent = `Showing ${filtered.length} of ${state.schema.length} parameters`;
  dom.paramsGrid.innerHTML = "";

  filtered.forEach((param) => {
    const isModified = !!state.diff[param.path];
    const card = document.createElement("div");
    card.className = `param-card ${isModified ? 'modified' : ''}`;
    card.id = `card-${param.path.replace(/\./g, '-')}`;

    const val = param.value !== null && param.value !== undefined ? param.value : 0;
    const isNumeric = typeof val === "number";

    let min = 0;
    let max = 100;
    let step = 0.05;
    if (isNumeric) {
      if (val === 0) {
        min = -10;
        max = 10;
        step = 0.1;
      } else if (val > 0) {
        min = Math.max(0, Number((val * 0.2).toFixed(2)));
        max = Number((val * 2.0).toFixed(2));
        step = Number(((max - min) / 100).toFixed(3)) || 0.01;
      } else {
        min = Number((val * 2.0).toFixed(2));
        max = Number((val * 0.2).toFixed(2));
        step = Number(((max - min) / 100).toFixed(3)) || 0.01;
      }
    }

    card.innerHTML = `
      <div class="card-top">
        <div class="card-title-group">
          <span class="card-path">${param.path}</span>
          <span class="card-name">${formatTitle(param.name)}</span>
        </div>
        <div style="display: flex; gap: 6px; align-items: center;">
          <button class="btn-card-reset" data-path="${param.path}" title="Reset to baseline">↺ Reset</button>
          ${param.unit ? `<span class="card-unit">${param.unit}</span>` : ''}
        </div>
      </div>
      ${param.description ? `<p class="card-desc">${param.description}</p>` : ''}
      <div class="card-controls">
        <div class="input-row">
          <input type="${isNumeric ? 'number' : 'text'}" 
                 class="num-input" 
                 value="${val}" 
                 step="${step}"
                 data-path="${param.path}" />
        </div>
        ${isNumeric ? `
          <div class="slider-row">
            <input type="range" 
                   class="param-slider" 
                   min="${min}" 
                   max="${max}" 
                   step="${step}" 
                   value="${val}" 
                   data-path="${param.path}" />
          </div>
        ` : ''}
      </div>
    `;

    const numInput = card.querySelector(".num-input");
    const slider = card.querySelector(".param-slider");
    const resetBtn = card.querySelector(".btn-card-reset");

    if (slider) {
      slider.addEventListener("input", (e) => {
        const newVal = parseFloat(e.target.value);
        numInput.value = newVal;
        param.value = newVal;
        predictAndRenderCanvas(param.path, newVal);
        debouncedUpdate(param.path, newVal, param.unit, card);
      });
    }

    numInput.addEventListener("change", (e) => {
      const newVal = isNumeric ? parseFloat(e.target.value) : e.target.value;
      if (slider) slider.value = newVal;
      param.value = newVal;
      predictAndRenderCanvas(param.path, newVal);
      sendParamUpdate(param.path, newVal, param.unit, card);
    });

    resetBtn.addEventListener("click", async () => {
      await resetParam(param.path, card);
    });

    dom.paramsGrid.appendChild(card);
  });
}

let debounceTimer = null;
function debouncedUpdate(path, value, unit, card) {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    sendParamUpdate(path, value, unit, card);
  }, 120);
}

let debounce3DTimer = null;
function debounced3DUpdate() {
  clearTimeout(debounce3DTimer);
  debounce3DTimer = setTimeout(() => {
    update3DPreview();
  }, 150);
}

async function sendParamUpdate(path, value, unit, card) {
  try {
    const res = await fetch("/api/param", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, value, unit }),
    });
    if (res.ok) {
      const data = await res.json();
      state.diff = data.diff || {};
      if (card) {
        if (data.is_modified) {
          card.classList.add("modified");
        } else {
          card.classList.remove("modified");
        }
      }
      updateDiffBadge();
      renderDiffDrawer();
      await update2DPreview();
      if (state.activeView === "3d") {
        await update3DPreview();
      }
    }
  } catch (err) {
    console.error("Error updating parameter:", err);
  }
}

async function resetParam(path, card) {
  try {
    const res = await fetch("/api/reset_param", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    if (res.ok) {
      const data = await res.json();
      state.diff = data.diff || {};
      const param = state.schema.find((p) => p.path === path);
      if (param) param.value = data.value;
      if (card) {
        card.classList.remove("modified");
        const numInput = card.querySelector(".num-input");
        const slider = card.querySelector(".param-slider");
        if (numInput) numInput.value = data.value;
        if (slider) slider.value = data.value;
      }
      updateDiffBadge();
      renderDiffDrawer();
      await update2DPreview();
      if (state.activeView === "3d") {
        await update3DPreview();
      }
    }
  } catch (err) {
    console.error("Error resetting parameter:", err);
  }
}

function renderDiffDrawer() {
  const paths = Object.keys(state.diff);
  if (paths.length === 0) {
    dom.diffList.innerHTML = `<p class="diff-empty">No modified parameters. Twiddle any slider to see diffs.</p>`;
    return;
  }

  dom.diffList.innerHTML = "";
  paths.forEach((p) => {
    const item = state.diff[p];
    const el = document.createElement("div");
    el.className = "diff-item";
    el.innerHTML = `
      <div class="diff-item-path">${p}</div>
      <div class="diff-item-values">
        <span class="diff-old">${item.baseline !== null ? item.baseline : 'None'}</span>
        <span>→</span>
        <span class="diff-new">${item.current}</span>
        ${item.unit ? `<span class="card-unit">${item.unit}</span>` : ''}
      </div>
    `;
    dom.diffList.appendChild(el);
  });
}

// 2D Poloidal Cross-Section Canvas Preview
async function update2DPreview() {
  try {
    const res = await fetch("/api/preview/2d?num_points=120");
    if (res.ok) {
      state.plasmaShape = await res.json();
      renderCanvas();
      updateMetricDisplays();
    }
  } catch (err) {
    console.error("Error loading 2D preview:", err);
  }
}

function updateMetricDisplays() {
  if (!state.plasmaShape) return;
  const { r0, a, kappa, delta } = state.plasmaShape;
  if (r0 && a && a !== 0) {
    dom.metricAspect.textContent = (r0 / a).toFixed(2);
  }
  dom.metricKappa.textContent = kappa ? kappa.toFixed(2) : "-";
  dom.metricDelta.textContent = delta ? delta.toFixed(2) : "-";
}

function predictAndRenderCanvas(path, value) {
  if (!state.plasmaShape) return;
  const pLower = path.toLowerCase();
  if (pLower.includes("r_0") || pLower.includes("major_radius")) {
    state.plasmaShape.r0 = value;
  } else if (pLower.includes("minor_radius") || pLower.includes(".a")) {
    state.plasmaShape.a = value;
  } else if (pLower.includes("elongation") || pLower.includes("kappa")) {
    state.plasmaShape.kappa = value;
  } else if (pLower.includes("triangularity") || pLower.includes("delta")) {
    state.plasmaShape.delta = value;
  }

  const { r0, a, kappa, delta } = state.plasmaShape;
  const num = 120;
  const rPlasma = [];
  const zPlasma = [];
  const rBlanket = [];
  const zBlanket = [];
  const rVV = [];
  const zVV = [];

  const asinDelta = Math.asin(Math.max(-0.95, Math.min(0.95, delta || 0.35)));
  for (let i = 0; i <= num; i++) {
    const theta = (i / num) * 2 * Math.PI;
    const r = r0 + a * Math.cos(theta + asinDelta * Math.sin(theta));
    const z = a * kappa * Math.sin(theta);
    rPlasma.push(r);
    zPlasma.push(z);

    const rB = r0 + (a + 0.8) * Math.cos(theta + asinDelta * Math.sin(theta));
    const zB = (a + 0.8) * kappa * Math.sin(theta);
    rBlanket.push(rB);
    zBlanket.push(zB);

    const rV = r0 + (a + 1.2) * Math.cos(theta + asinDelta * Math.sin(theta));
    const zV = (a + 1.2) * kappa * Math.sin(theta);
    rVV.push(rV);
    zVV.push(zV);
  }

  state.plasmaShape.plasma = { r: rPlasma, z: zPlasma };
  state.plasmaShape.blanket = { r: rBlanket, z: zBlanket };
  state.plasmaShape.vacuum_vessel = { r: rVV, z: zVV };

  renderCanvas();
  updateMetricDisplays();
}

let viewTransform = { scale: 30, offsetX: 60, offsetY: 260 };

function canvasToPhysicalCoords(cx, cy) {
  const r = (cx - viewTransform.offsetX) / viewTransform.scale;
  const z = -(cy - viewTransform.offsetY) / viewTransform.scale;
  return { r: Math.max(0, r), z };
}

function physicalToCanvasCoords(r, z) {
  const cx = viewTransform.offsetX + r * viewTransform.scale;
  const cy = viewTransform.offsetY - z * viewTransform.scale;
  return { cx, cy };
}

function renderCanvas() {
  const ctx = dom.canvas2D.getContext("2d");
  const w = dom.canvas2D.width;
  const h = dom.canvas2D.height;

  ctx.clearRect(0, 0, w, h);

  if (!state.plasmaShape || !state.plasmaShape.plasma) {
    ctx.fillStyle = "#8fa2b7";
    ctx.font = "14px Inter";
    ctx.textAlign = "center";
    ctx.fillText("No geometry available", w / 2, h / 2);
    return;
  }

  const rMax = Math.max(...state.plasmaShape.vacuum_vessel.r, 14.0);
  const zMax = Math.max(...state.plasmaShape.vacuum_vessel.z.map(Math.abs), 8.0);

  const scaleR = (w - 100) / rMax;
  const scaleZ = (h - 80) / (2 * zMax);
  viewTransform.scale = Math.min(scaleR, scaleZ);
  viewTransform.offsetX = 50;
  viewTransform.offsetY = h / 2;

  // Grid
  ctx.strokeStyle = "#1c2738";
  ctx.lineWidth = 1;
  const gridStep = 2.0;

  for (let r = 0; r <= rMax + 2; r += gridStep) {
    const { cx } = physicalToCanvasCoords(r, 0);
    ctx.beginPath();
    ctx.moveTo(cx, 0);
    ctx.lineTo(cx, h);
    ctx.stroke();

    ctx.fillStyle = "#486581";
    ctx.font = "10px JetBrains Mono";
    ctx.textAlign = "center";
    ctx.fillText(`${r}m`, cx, h - 10);
  }

  for (let z = -zMax; z <= zMax; z += gridStep) {
    const { cy } = physicalToCanvasCoords(0, z);
    ctx.beginPath();
    ctx.moveTo(0, cy);
    ctx.lineTo(w, cy);
    ctx.stroke();

    ctx.fillStyle = "#486581";
    ctx.font = "10px JetBrains Mono";
    ctx.textAlign = "right";
    ctx.fillText(`${z}m`, 40, cy + 3);
  }

  // Machine Axis
  const axisP = physicalToCanvasCoords(0, 0);
  ctx.strokeStyle = "#00e5ff";
  ctx.lineWidth = 2;
  ctx.setLineDash([6, 4]);
  ctx.beginPath();
  ctx.moveTo(axisP.cx, 10);
  ctx.lineTo(axisP.cx, h - 25);
  ctx.stroke();
  ctx.setLineDash([]);

  ctx.fillStyle = "#00e5ff";
  ctx.font = "10px JetBrains Mono";
  ctx.textAlign = "center";
  ctx.fillText("R = 0 (Axis)", axisP.cx, 20);

  function drawShape(coords, strokeColor, fillColor, lineWidth = 2) {
    if (!coords || !coords.r || coords.r.length === 0) return;
    ctx.beginPath();
    const p0 = physicalToCanvasCoords(coords.r[0], coords.z[0]);
    ctx.moveTo(p0.cx, p0.cy);
    for (let i = 1; i < coords.r.length; i++) {
      const p = physicalToCanvasCoords(coords.r[i], coords.z[i]);
      ctx.lineTo(p.cx, p.cy);
    }
    ctx.closePath();
    if (fillColor) {
      ctx.fillStyle = fillColor;
      ctx.fill();
    }
    if (strokeColor) {
      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = lineWidth;
      ctx.stroke();
    }
  }

  drawShape(state.plasmaShape.vacuum_vessel, "#00e5ff", "rgba(0, 229, 255, 0.05)", 2);
  drawShape(state.plasmaShape.blanket, "#ffd600", "rgba(255, 214, 0, 0.08)", 2);
  drawShape(state.plasmaShape.plasma, "#ff3d00", "rgba(255, 61, 0, 0.35)", 2.5);

  const { r0 } = state.plasmaShape;
  if (r0) {
    const pCenter = physicalToCanvasCoords(r0, 0);
    ctx.fillStyle = "#ffffff";
    ctx.beginPath();
    ctx.arc(pCenter.cx, pCenter.cy, 3, 0, 2 * Math.PI);
    ctx.fill();
  }
}

// 3D CAD WebGL / Canvas Renderer
async function update3DPreview() {
  try {
    const res = await fetch(`/api/cad/mesh?cutaway=${state.cutawayDeg}`);
    if (res.ok) {
      state.cadMesh = await res.json();
      render3DCanvas();
    }
  } catch (err) {
    console.error("Error loading 3D CAD mesh:", err);
  }
}

function render3DCanvas() {
  const canvas = dom.canvas3D;
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;

  ctx.clearRect(0, 0, w, h);

  if (!state.cadMesh) {
    ctx.fillStyle = "#8fa2b7";
    ctx.font = "14px Inter";
    ctx.textAlign = "center";
    ctx.fillText("Generating 3D CAD Mesh...", w / 2, h / 2);
    return;
  }

  // Precompute 3D Camera Rotation Matrix
  const cosX = Math.cos(camera3D.rotX);
  const sinX = Math.sin(camera3D.rotX);
  const cosY = Math.cos(camera3D.rotY);
  const sinY = Math.sin(camera3D.rotY);

  // Project 3D point (x, y, z) to screen coordinates
  function project3D(x, y, z) {
    const x1 = x * cosY + y * sinY;
    const y1 = -x * sinY + y * cosY;
    const z1 = z;

    const x2 = x1;
    const y2 = y1 * cosX - z1 * sinX;
    const z2 = y1 * sinX + z1 * cosX;

    const fov = 380;
    const depth = camera3D.distance + y2;
    if (depth <= 0.5) return null;

    const sx = w / 2 + (x2 * fov) / depth;
    const sy = h / 2 - (z2 * fov) / depth;
    return { sx, sy, depth };
  }

  const triangles = [];
  const lightDir = { x: 0.577, y: 0.577, z: 0.577 };

  for (const [compName, comp] of Object.entries(state.cadMesh)) {
    if (!state.visibility[compName]) continue;

    const verts = comp.vertices;
    const normals = comp.normals;
    const indices = comp.indices;
    const color = comp.color;
    const opacity = comp.opacity || 0.8;

    for (let i = 0; i < indices.length; i += 3) {
      const idx0 = indices[i] * 3;
      const idx1 = indices[i + 1] * 3;
      const idx2 = indices[i + 2] * 3;

      const p0 = project3D(verts[idx0], verts[idx0 + 1], verts[idx0 + 2]);
      const p1 = project3D(verts[idx1], verts[idx1 + 1], verts[idx1 + 2]);
      const p2 = project3D(verts[idx2], verts[idx2 + 1], verts[idx2 + 2]);

      if (!p0 || !p1 || !p2) continue;

      const nx = normals[idx0] || 0;
      const ny = normals[idx0 + 1] || 0;
      const nz = normals[idx0 + 2] || 1;
      const dot = Math.max(0.15, nx * lightDir.x + ny * lightDir.y + nz * lightDir.z);
      const avgDepth = (p0.depth + p1.depth + p2.depth) / 3;

      triangles.push({
        p0, p1, p2,
        depth: avgDepth,
        color,
        intensity: dot,
        opacity,
      });
    }
  }

  triangles.sort((a, b) => b.depth - a.depth);

  for (const tri of triangles) {
    ctx.beginPath();
    ctx.moveTo(tri.p0.sx, tri.p0.sy);
    ctx.lineTo(tri.p1.sx, tri.p1.sy);
    ctx.lineTo(tri.p2.sx, tri.p2.sy);
    ctx.closePath();

    if (!state.wireframe) {
      ctx.fillStyle = shadeColor(tri.color, tri.intensity, tri.opacity);
      ctx.fill();
    }
    ctx.strokeStyle = state.wireframe ? tri.color : "rgba(0,0,0,0.15)";
    ctx.lineWidth = 0.5;
    ctx.stroke();
  }
}

function shadeColor(hex, intensity, alpha) {
  let c = hex.replace("#", "");
  if (c.length === 3) c = c.split("").map((x) => x + x).join("");
  const num = parseInt(c, 16);
  const r = Math.min(255, Math.floor(((num >> 16) & 255) * (0.4 + 0.6 * intensity)));
  const g = Math.min(255, Math.floor(((num >> 8) & 255) * (0.4 + 0.6 * intensity)));
  const b = Math.min(255, Math.floor((num & 255) * (0.4 + 0.6 * intensity)));
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function formatTitle(str) {
  if (!str) return "";
  return str
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
