const NJ_GEOJSON_URL =
  "https://raw.githubusercontent.com/OpenDataDE/State-zip-code-GeoJSON/master/nj_new_jersey_zip_codes_geo.min.json";

const MONTH_NAMES = [
  "January","February","March","April","May","June",
  "July","August","September","October","November","December"
];

const map = L.map("map", {
  zoomControl: true,
}).setView([40.0583, -74.4057], 8);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 18,
  attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);

// Dedicated pane so data-center markers always render above ZIP polygons.
map.createPane("dcPane");
map.getPane("dcPane").style.zIndex = 650;

const infoEl          = document.getElementById("info");
const zipSearchEl     = document.getElementById("zipSearch");
const searchBtnEl     = document.getElementById("searchBtn");
const yearSelectEl    = document.getElementById("yearSelect");
const monthSliderEl   = document.getElementById("monthSlider");
const monthLabelEl    = document.getElementById("monthLabel");
const heatmapToggleEl = document.getElementById("heatmapToggle");
const dcToggleEl      = document.getElementById("dcToggle");

const layerByZip = new Map();
let selectedLayer = null;
let zipDetails = {};
let selectedZip = null;
let heatmapEnabled = false;
let legendControl = null;
let dataCenters = [];
let dcLayerGroup = null;

// ─── Helpers ──────────────────────────────────────────────────────────────────

function safeNum(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "N/A";
  }
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function monthKey(year, month) {
  return `${year}-${String(month).padStart(2, "0")}`;
}

function getMonthLmp(zip, year, month) {
  const d = zipDetails[zip];
  if (!d) return null;
  const v = d.monthly_lmp?.[monthKey(year, month)];
  return v !== null && v !== undefined && Number.isFinite(Number(v)) ? Number(v) : null;
}

function collectAvailableYears() {
  const years = new Set();
  Object.values(zipDetails).forEach((d) => {
    if (d?.monthly_lmp) {
      Object.keys(d.monthly_lmp).forEach((k) => years.add(k.slice(0, 4)));
    }
  });
  if (years.size === 0) {
    ["2020","2021","2022","2023","2024","2025"].forEach((y) => years.add(y));
  }
  return Array.from(years).sort();
}

function populateYearSelect() {
  const years = collectAvailableYears();
  yearSelectEl.innerHTML = "";
  years.forEach((year) => {
    const opt = document.createElement("option");
    opt.value = year;
    opt.textContent = year;
    yearSelectEl.appendChild(opt);
  });
  if (years.length > 0) yearSelectEl.value = years[years.length - 1];
}

function updateMonthLabel() {
  monthLabelEl.textContent = MONTH_NAMES[Number(monthSliderEl.value) - 1];
}

// ─── Info card ────────────────────────────────────────────────────────────────

function buildSparkline(monthly_lmp, year) {
  const W = 270, H = 56, PAD = 4;
  const values = Array.from({ length: 12 }, (_, i) => {
    const v = monthly_lmp?.[monthKey(year, i + 1)];
    return v !== undefined && v !== null ? Number(v) : null;
  });

  const present = values.filter((v) => v !== null);
  if (present.length < 2) return "";

  const min = Math.min(...present);
  const max = Math.max(...present);
  const range = max - min || 1;

  const xOf = (i) => PAD + (i / 11) * (W - PAD * 2);
  const yOf = (v) => H - PAD - ((v - min) / range) * (H - PAD * 2);

  // Build polyline segments (split on nulls)
  const segments = [];
  let seg = [];
  values.forEach((v, i) => {
    if (v !== null) {
      seg.push(`${xOf(i).toFixed(1)},${yOf(v).toFixed(1)}`);
    } else if (seg.length) {
      segments.push(seg);
      seg = [];
    }
  });
  if (seg.length) segments.push(seg);

  const lines = segments
    .map((s) => `<polyline points="${s.join(" ")}" fill="none" stroke="var(--accent)" stroke-width="1.8" stroke-linejoin="round"/>`)
    .join("");

  const dots = values
    .map((v, i) => v !== null
      ? `<circle cx="${xOf(i).toFixed(1)}" cy="${yOf(v).toFixed(1)}" r="2.5" fill="var(--accent)"/>`
      : "")
    .join("");

  const selectedMonth = Number(monthSliderEl.value);
  const sv = values[selectedMonth - 1];
  const highlight = sv !== null
    ? `<circle cx="${xOf(selectedMonth - 1).toFixed(1)}" cy="${yOf(sv).toFixed(1)}" r="4" fill="var(--accent)" stroke="#fff" stroke-width="1.5"/>`
    : "";

  return `
    <div class="sparkline-wrap">
      <div class="sparkline-label">Monthly DA LMP ${year} ($/MWh)</div>
      <svg class="sparkline" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
        ${lines}${dots}${highlight}
      </svg>
      <div class="spark-axis">
        <span>Jan</span><span>Jun</span><span>Dec</span>
      </div>
    </div>`;
}

function renderZipInfo(zip) {
  const details = zipDetails[zip];
  if (!details) {
    infoEl.innerHTML = `<h2>ZIP ${zip}</h2><p class="info-empty">No data loaded for this ZIP.</p>`;
    return;
  }

  const year  = yearSelectEl.value;
  const month = Number(monthSliderEl.value);
  const key   = monthKey(year, month);

  const currentVal = details.monthly_lmp?.[key] ?? null;

  // Same month, first available year for baseline
  const allYears  = collectAvailableYears();
  const baseYear  = allYears[0] ?? year;
  const baseKey   = monthKey(baseYear, month);
  const baseVal   = details.monthly_lmp?.[baseKey] ?? null;

  let pctVsBase = null;
  if (baseVal && currentVal && baseVal !== 0) {
    pctVsBase = ((currentVal - baseVal) / baseVal) * 100;
  }

  const deltaClass = pctVsBase === null ? "" : pctVsBase >= 0 ? "delta-up" : "delta-down";
  const deltaSign  = pctVsBase !== null && pctVsBase > 0 ? "+" : "";

  infoEl.innerHTML = `
    <h2>ZIP ${zip}</h2>
    <div class="info-row"><strong>County</strong> <span class="info-value">${details.county || "N/A"}</span></div>
    <div class="info-row"><strong>LMP ${MONTH_NAMES[month - 1]} ${year}</strong> <span class="info-value">$${safeNum(currentVal)}/MWh</span></div>
    <div class="info-row"><strong>LMP ${MONTH_NAMES[month - 1]} ${baseYear}</strong> <span class="info-value">$${safeNum(baseVal)}/MWh</span></div>
    <div class="info-row">
      <strong>vs ${baseYear}</strong>
      <span class="info-value ${deltaClass}">${pctVsBase !== null ? `${deltaSign}${pctVsBase.toFixed(1)}%` : "N/A"}</span>
    </div>
    <div class="info-row"><strong>Node</strong> <span class="info-value">${details.nearest_node || "N/A"} (${details.node_zone || "N/A"})</span></div>
    <div class="info-row"><strong>Nearest data center</strong> <span class="info-value">${
      details.nearest_dc
        ? `${details.nearest_dc.name} (${details.nearest_dc.miles.toFixed(1)} mi)`
        : "N/A"
    }</span></div>
    ${buildSparkline(details.monthly_lmp, year)}
  `;
}

// ─── Heatmap ──────────────────────────────────────────────────────────────────

function lmpColor(t) {
  const stops = [
    [68, 170, 213],
    [255, 209, 102],
    [239, 71, 111],
  ];
  const scaled = t * (stops.length - 1);
  const i = Math.min(Math.floor(scaled), stops.length - 2);
  const f = scaled - i;
  const [r1, g1, b1] = stops[i];
  const [r2, g2, b2] = stops[i + 1];
  return `rgb(${Math.round(r1 + f*(r2-r1))},${Math.round(g1 + f*(g2-g1))},${Math.round(b1 + f*(b2-b1))})`;
}

function computeMinMax(year, month) {
  let min = Infinity, max = -Infinity;
  for (const zip of layerByZip.keys()) {
    const v = getMonthLmp(zip, year, month);
    if (v !== null) { if (v < min) min = v; if (v > max) max = v; }
  }
  return min <= max ? { min, max } : { min: 0, max: 1 };
}

function applyHeatmap() {
  const year  = yearSelectEl.value;
  const month = Number(monthSliderEl.value);
  const { min, max } = computeMinMax(year, month);
  const range = max - min || 1;

  layerByZip.forEach((layer, zip) => {
    const v = getMonthLmp(zip, year, month);
    const style = v !== null
      ? { fillColor: lmpColor((v - min) / range), fillOpacity: 0.75, color: "#555", weight: 0.5 }
      : { fillColor: "#cccccc", fillOpacity: 0.45, color: "#555", weight: 0.5 };
    layer.setStyle(style);
  });
  if (selectedLayer) selectedLayer.setStyle({ ...selectedLayer.options, color: "#003049", weight: 2 });
  showLegend(min, max, year, month);
}

function clearHeatmap() {
  layerByZip.forEach((layer, zip) => {
    layer.setStyle(zip === selectedZip ? selectedStyle() : baseStyle());
  });
  if (legendControl) { legendControl.remove(); legendControl = null; }
}

function showLegend(min, max, year, month) {
  if (legendControl) legendControl.remove();
  legendControl = L.control({ position: "bottomright" });
  legendControl.onAdd = () => {
    const div = L.DomUtil.create("div", "legend");
    div.innerHTML = `
      <div class="legend-title">DA LMP ${MONTH_NAMES[month - 1]} ${year} ($/MWh)</div>
      <div class="legend-bar"></div>
      <div class="legend-labels">
        <span>${min.toFixed(1)}</span>
        <span>${((min + max) / 2).toFixed(1)}</span>
        <span>${max.toFixed(1)}</span>
      </div>
      <div class="legend-na"><span class="legend-swatch"></span> No data</div>
    `;
    return div;
  };
  legendControl.addTo(map);
}

// ─── Map styles ───────────────────────────────────────────────────────────────

function baseStyle() {
  return { color: "#3b4f62", weight: 1, fillColor: "#7cc6d4", fillOpacity: 0.35 };
}

function selectedStyle() {
  return { color: "#003049", weight: 2, fillColor: "#006d77", fillOpacity: 0.55 };
}

function selectLayer(layer, zip) {
  if (selectedLayer) {
    if (heatmapEnabled) {
      const year  = yearSelectEl.value;
      const month = Number(monthSliderEl.value);
      const { min, max } = computeMinMax(year, month);
      const v = getMonthLmp(selectedZip, year, month);
      selectedLayer.setStyle(v !== null
        ? { fillColor: lmpColor((v - min) / (max - min || 1)), fillOpacity: 0.75, color: "#555", weight: 0.5 }
        : { fillColor: "#cccccc", fillOpacity: 0.45, color: "#555", weight: 0.5 });
    } else {
      selectedLayer.setStyle(baseStyle());
    }
  }
  selectedLayer = layer;
  selectedLayer.setStyle(heatmapEnabled
    ? { ...selectedLayer.options, color: "#003049", weight: 2.5 }
    : selectedStyle());
  selectedZip = zip;
  renderZipInfo(zip);
}

// ─── Data loading ─────────────────────────────────────────────────────────────

async function loadZipDetails() {
  try {
    const res = await fetch("nj_zip_info.json");
    zipDetails = await res.json();
  } catch (err) {
    console.warn("Could not load nj_zip_info.json", err);
    zipDetails = {};
  }
}

async function loadDataCenters() {
  try {
    const res = await fetch("data_centers.json");
    dataCenters = await res.json();
  } catch (err) {
    console.warn("Could not load data_centers.json", err);
    dataCenters = [];
  }
}

const dcMarkers = []; // { marker, startYear }

function buildDcLayer() {
  dcLayerGroup = L.layerGroup();
  dataCenters.forEach((dc) => {
    const marker = L.circleMarker([dc.lat, dc.lon], {
      pane: "dcPane",
      radius: 8,
      color: "#1b1b1b",
      weight: 1.5,
      fillColor: "#ffb703",
      fillOpacity: 1,
    });
    const startYear = Number.isFinite(Number(dc.start_year)) ? Number(dc.start_year) : null;
    const startLine = startYear ? `<br/>Online since: ${startYear}` : "";
    const popup = `
      <div class="dc-popup">
        <strong>${dc.name || "(unnamed)"}</strong><br/>
        ${dc.operator ? `${dc.operator}<br/>` : ""}
        ${dc.address || ""}<br/>
        <em>${dc.status || ""}${dc.capacity ? " · " + dc.capacity : ""}</em>
        ${dc.hyperscaler && dc.hyperscaler !== "No" ? `<br/>Hyperscaler: ${dc.hyperscaler}` : ""}
        ${startLine}
      </div>`;
    marker.bindPopup(popup);
    marker.bindTooltip(dc.name || "Data center", { direction: "top" });
    dcMarkers.push({ marker, startYear });
  });
  updateDcVisibility();
}

function updateDcVisibility() {
  if (!dcLayerGroup) return;
  const year  = Number(yearSelectEl.value);
  const month = Number(monthSliderEl.value);
  // Only year-level precision available; treat start as January of start_year.
  const currentKey = year * 12 + month;
  dcMarkers.forEach(({ marker, startYear }) => {
    const visible = startYear === null || currentKey >= startYear * 12 + 1;
    const present = dcLayerGroup.hasLayer(marker);
    if (visible && !present) dcLayerGroup.addLayer(marker);
    else if (!visible && present) dcLayerGroup.removeLayer(marker);
  });
}

async function buildZipLayer() {
  const response = await fetch(NJ_GEOJSON_URL);
  const geo = await response.json();

  const layer = L.geoJSON(geo, {
    style: baseStyle,
    onEachFeature: (feature, featureLayer) => {
      const zip = String(feature.properties.ZCTA5CE10 || "");
      layerByZip.set(zip, featureLayer);
      featureLayer.bindTooltip(`ZIP ${zip}`, { className: "zip-label", sticky: true });
      featureLayer.on("click", () => selectLayer(featureLayer, zip));
    },
  });

  layer.addTo(map);
  map.fitBounds(layer.getBounds());
}

// ─── Controls ─────────────────────────────────────────────────────────────────

function setupSearch() {
  function goToZip() {
    const zip = zipSearchEl.value.trim();
    const target = layerByZip.get(zip);
    if (!target) {
      infoEl.innerHTML = `<h2>ZIP not found</h2><p>No shape found for ZIP ${zip || "(blank)"}.</p>`;
      return;
    }
    map.fitBounds(target.getBounds(), { maxZoom: 11 });
    selectLayer(target, zip);
  }

  searchBtnEl.addEventListener("click", goToZip);
  zipSearchEl.addEventListener("keydown", (e) => { if (e.key === "Enter") goToZip(); });

  yearSelectEl.addEventListener("change", () => {
    if (selectedZip) renderZipInfo(selectedZip);
    if (heatmapEnabled) applyHeatmap();
    updateDcVisibility();
  });

  monthSliderEl.addEventListener("input", () => {
    updateMonthLabel();
    if (selectedZip) renderZipInfo(selectedZip);
    if (heatmapEnabled) applyHeatmap();
    updateDcVisibility();
  });

  heatmapToggleEl.addEventListener("change", () => {
    heatmapEnabled = heatmapToggleEl.checked;
    if (heatmapEnabled) applyHeatmap();
    else clearHeatmap();
  });

  if (dcToggleEl) {
    dcToggleEl.addEventListener("change", () => {
      if (!dcLayerGroup) return;
      if (dcToggleEl.checked) dcLayerGroup.addTo(map);
      else map.removeLayer(dcLayerGroup);
    });
  }
}

// ─── Init ─────────────────────────────────────────────────────────────────────

(async function init() {
  await Promise.all([loadZipDetails(), loadDataCenters()]);
  populateYearSelect();
  updateMonthLabel();
  await buildZipLayer();
  buildDcLayer();
  if (dcLayerGroup) {
    dcLayerGroup.addTo(map);
    if (dcToggleEl) dcToggleEl.checked = true;
    console.log(`Rendered ${dataCenters.length} data center markers`);
  }
  setupSearch();

  // Fade out the loading overlay
  const loader = document.getElementById("loader");
  if (loader) {
    loader.classList.add("hidden");
    setTimeout(() => loader.remove(), 500);
  }
})();
