const NJ_GEOJSON_URL =
  "https://raw.githubusercontent.com/OpenDataDE/State-zip-code-GeoJSON/master/nj_new_jersey_zip_codes_geo.min.json";

const map = L.map("map", { zoomControl: true }).setView([40.0583, -74.4057], 8);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 18,
  attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);

const infoEl        = document.getElementById("info");
const zipSearchEl   = document.getElementById("zipSearch");
const searchBtnEl   = document.getElementById("searchBtn");
const yearSelectEl  = document.getElementById("yearSelect");

const layerByZip  = new Map();
let selectedLayer = null;
let zipDetails    = {};
let selectedZip   = null;
let availableYears = [];
let lmpRange      = { min: 0, max: 100 };
let legendControl = null;

// ─── Color scale (blue → yellow → red) ───────────────────────────────────────
const COLOR_STOPS = [
  [0,   [68,  170, 213]],
  [0.5, [255, 209, 102]],
  [1,   [239, 71,  111]],
];

function lerpColor(t) {
  t = Math.max(0, Math.min(1, t));
  let lo = COLOR_STOPS[0], hi = COLOR_STOPS[COLOR_STOPS.length - 1];
  for (let i = 0; i < COLOR_STOPS.length - 1; i++) {
    if (t <= COLOR_STOPS[i + 1][0]) { lo = COLOR_STOPS[i]; hi = COLOR_STOPS[i + 1]; break; }
  }
  const s = (t - lo[0]) / (hi[0] - lo[0]);
  const ch = (idx) => Math.round(lo[1][idx] + s * (hi[1][idx] - lo[1][idx]));
  return `rgb(${ch(0)},${ch(1)},${ch(2)})`;
}

function computeLmpRange(year) {
  const vals = Object.values(zipDetails)
    .map((d) => d?.yearly_lmp?.[year] ?? d?.[`avg_lmp_${year}`])
    .filter((v) => v !== null && v !== undefined && Number.isFinite(Number(v)))
    .map(Number);
  if (!vals.length) return { min: 0, max: 100 };
  return { min: Math.min(...vals), max: Math.max(...vals) };
}

function getLmpColor(zip, year) {
  const d = zipDetails[zip];
  const val = d?.yearly_lmp?.[year] ?? d?.[`avg_lmp_${year}`];
  if (val == null || !Number.isFinite(Number(val))) return "#cccccc";
  const { min, max } = lmpRange;
  return lerpColor(max > min ? (Number(val) - min) / (max - min) : 0.5);
}

// ─── Utilities ────────────────────────────────────────────────────────────────
function safeNum(v) {
  if (v == null || Number.isNaN(Number(v))) return "N/A";
  return Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function currentYear() {
  return String(yearSelectEl.value || availableYears[availableYears.length - 1] || "2025");
}

// ─── Year selector ────────────────────────────────────────────────────────────
function populateYearSelect() {
  const years = new Set();
  Object.values(zipDetails).forEach((d) => {
    if (d?.yearly_lmp) Object.keys(d.yearly_lmp).forEach((y) => years.add(y));
    if (d) Object.keys(d).forEach((k) => { const m = k.match(/^avg_lmp_(\d{4})$/); if (m) years.add(m[1]); });
  });
  if (!years.size) ["2020","2021","2022","2023","2024","2025"].forEach((y) => years.add(y));

  availableYears = Array.from(years).sort((a, b) => Number(a) - Number(b));
  yearSelectEl.innerHTML = "";
  availableYears.forEach((yr) => {
    const opt = document.createElement("option");
    opt.value = yr; opt.textContent = yr;
    yearSelectEl.appendChild(opt);
  });
  if (availableYears.length) yearSelectEl.value = availableYears[availableYears.length - 1];
}

// ─── Sparkline ────────────────────────────────────────────────────────────────
function buildSparkline(yearly, selectedYr) {
  const yrs  = availableYears.filter((y) => yearly[y] != null);
  if (yrs.length < 2) return "";

  const vals = yrs.map((y) => Number(yearly[y]));
  const lo   = Math.min(...vals), hi = Math.max(...vals);
  const W = 220, H = 44, px = 6, py = 6;
  const iw = W - px * 2, ih = H - py * 2;

  const xs = yrs.map((_, i) => px + (i / (yrs.length - 1)) * iw);
  const ys = vals.map((v) => H - py - (hi > lo ? ((v - lo) / (hi - lo)) * ih : ih / 2));

  const path  = xs.map((x, i) => `${i ? "L" : "M"}${x.toFixed(1)},${ys[i].toFixed(1)}`).join(" ");
  const dots  = xs.map((x, i) => {
    const isSelected = yrs[i] === selectedYr;
    return `<circle cx="${x.toFixed(1)}" cy="${ys[i].toFixed(1)}" r="${isSelected ? 4 : 2.5}"
      fill="${isSelected ? "var(--accent)" : "var(--accent)"}" opacity="${isSelected ? 1 : 0.6}"/>`;
  }).join("");
  const lbls = [0, yrs.length - 1].map((i) =>
    `<text x="${xs[i].toFixed(1)}" y="${H + 12}" text-anchor="${i ? "end" : "start"}" font-size="9" fill="#6b7280">${yrs[i]}</text>`
  ).join("");

  return `<div class="sparkline-wrap">
    <div class="sparkline-label">LMP trend ($/MWh)</div>
    <svg viewBox="0 0 ${W} ${H + 14}" width="${W}" height="${H + 14}" class="sparkline">
      <path d="${path}" fill="none" stroke="var(--accent)" stroke-width="1.5" stroke-linejoin="round"/>
      ${dots}${lbls}
    </svg>
  </div>`;
}

// ─── Info panel ───────────────────────────────────────────────────────────────
function renderZipInfo(zip) {
  const d = zipDetails[zip];
  if (!d) {
    infoEl.innerHTML = `<h2>ZIP ${zip}</h2><p>No data loaded for this ZIP.</p>`;
    return;
  }

  const yr      = currentYear();
  const baseYr  = availableYears[0] || "2020";
  const yearly  = d.yearly_lmp || {};
  const curVal  = yearly[yr]     ?? d[`avg_lmp_${yr}`];
  const baseVal = yearly[baseYr] ?? d[`avg_lmp_${baseYr}`];

  let delta = null;
  if (Number(baseVal) > 0 && Number.isFinite(Number(curVal))) {
    delta = ((Number(curVal) - Number(baseVal)) / Number(baseVal)) * 100;
  }
  const deltaStr   = delta == null ? "N/A" : `${delta >= 0 ? "+" : ""}${delta.toFixed(1)}%`;
  const deltaClass = delta == null ? "" : delta >= 0 ? "delta-up" : "delta-down";

  infoEl.innerHTML = `
    <h2>ZIP ${zip}</h2>
    <div class="info-row"><strong>County:</strong> ${d.county || "N/A"}</div>
    <div class="info-row"><strong>LMP ${yr}:</strong> $${safeNum(curVal)}/MWh</div>
    <div class="info-row"><strong>LMP ${baseYr}:</strong> $${safeNum(baseVal)}/MWh</div>
    <div class="info-row"><strong>Change ${baseYr}→${yr}:</strong> <span class="${deltaClass}">${deltaStr}</span></div>
    <div class="info-row"><strong>Node:</strong> ${d.nearest_node || "N/A"} (${d.node_zone || "N/A"})</div>
    <div class="info-row"><strong>Distance:</strong> ${d.dist_miles != null ? d.dist_miles + " mi" : "N/A"}</div>
    ${buildSparkline(yearly, yr)}
  `;
}

// ─── Choropleth ───────────────────────────────────────────────────────────────
function refreshChoropleth() {
  const yr = currentYear();
  lmpRange = computeLmpRange(yr);
  layerByZip.forEach((layer, zip) => {
    const isSelected = zip === selectedZip;
    layer.setStyle({
      color:       isSelected ? "#003049" : "#3b4f62",
      weight:      isSelected ? 2 : 0.8,
      fillColor:   getLmpColor(zip, yr),
      fillOpacity: isSelected ? 0.88 : 0.68,
    });
  });
  updateLegend();
}

// ─── Legend ───────────────────────────────────────────────────────────────────
function updateLegend() {
  if (legendControl) map.removeControl(legendControl);
  const { min, max } = lmpRange;

  legendControl = L.control({ position: "bottomright" });
  legendControl.onAdd = () => {
    const div = L.DomUtil.create("div", "legend");
    div.innerHTML = `
      <div class="legend-title">Avg DA LMP ($/MWh)</div>
      <div class="legend-bar"></div>
      <div class="legend-labels">
        <span>$${min.toFixed(1)}</span>
        <span>$${((min + max) / 2).toFixed(1)}</span>
        <span>$${max.toFixed(1)}</span>
      </div>
      <div class="legend-na"><span class="legend-swatch"></span>No data</div>
    `;
    return div;
  };
  legendControl.addTo(map);
}

// ─── Loading overlay ──────────────────────────────────────────────────────────
function showLoader(msg) {
  let el = document.getElementById("loader");
  if (!el) { el = document.createElement("div"); el.id = "loader"; document.body.appendChild(el); }
  el.textContent = msg;
  el.style.display = "flex";
}

function hideLoader() {
  const el = document.getElementById("loader");
  if (el) el.style.display = "none";
}

// ─── Layer helpers ────────────────────────────────────────────────────────────
function zipStyle(zip, isSelected = false) {
  return {
    color:       isSelected ? "#003049" : "#3b4f62",
    weight:      isSelected ? 2 : 0.8,
    fillColor:   getLmpColor(zip, currentYear()),
    fillOpacity: isSelected ? 0.88 : 0.68,
  };
}

function selectLayer(layer, zip) {
  if (selectedLayer && selectedZip) {
    selectedLayer.setStyle(zipStyle(selectedZip, false));
  }
  selectedLayer = layer;
  selectedZip   = zip;
  layer.setStyle(zipStyle(zip, true));

  const d = zipDetails[zip];
  if (d?.selected_year) yearSelectEl.value = String(d.selected_year);
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

async function buildZipLayer() {
  showLoader("Loading ZIP boundaries…");
  const response = await fetch(NJ_GEOJSON_URL);
  const geo = await response.json();

  const layer = L.geoJSON(geo, {
    style: (feature) => zipStyle(String(feature.properties.ZCTA5CE10 || "")),
    onEachFeature: (feature, featureLayer) => {
      const zip = String(feature.properties.ZCTA5CE10 || "");
      layerByZip.set(zip, featureLayer);

      featureLayer.bindTooltip(
        () => {
          const val = zipDetails[zip]?.yearly_lmp?.[currentYear()];
          return `<strong>ZIP ${zip}</strong>${val != null ? `<br>$${Number(val).toFixed(2)}/MWh` : ""}`;
        },
        { className: "zip-label", sticky: true }
      );

      featureLayer.on("click", () => selectLayer(featureLayer, zip));
    },
  });

  layer.addTo(map);
  map.fitBounds(layer.getBounds());
  hideLoader();
}

// ─── Search ───────────────────────────────────────────────────────────────────
function setupSearch() {
  function goToZip() {
    const zip    = zipSearchEl.value.trim();
    const target = layerByZip.get(zip);
    if (!target) {
      infoEl.innerHTML = `<h2>ZIP not found</h2><p>No shape for ZIP ${zip || "(blank)"}.</p>`;
      return;
    }
    map.fitBounds(target.getBounds(), { maxZoom: 11 });
    selectLayer(target, zip);
  }

  searchBtnEl.addEventListener("click", goToZip);
  zipSearchEl.addEventListener("keydown", (e) => { if (e.key === "Enter") goToZip(); });

  yearSelectEl.addEventListener("change", () => {
    refreshChoropleth();
    if (selectedZip) renderZipInfo(selectedZip);
  });
}

// ─── Init ─────────────────────────────────────────────────────────────────────
(async function init() {
  await loadZipDetails();
  populateYearSelect();
  lmpRange = computeLmpRange(currentYear());
  await buildZipLayer();
  updateLegend();
  setupSearch();
})();
