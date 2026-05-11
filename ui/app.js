const NJ_GEOJSON_URL =
  "https://raw.githubusercontent.com/OpenDataDE/State-zip-code-GeoJSON/master/nj_new_jersey_zip_codes_geo.min.json";

const MONTH_NAMES = [
  "January","February","March","April","May","June",
  "July","August","September","October","November","December"
];

const map = L.map("map", {
  zoomControl: true,
}).setView([40.0583, -74.4057], 8);

L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
  maxZoom: 19,
  subdomains: "abcd",
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
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
const metricSelectEl  = document.getElementById("metricSelect");
const dcToggleEl      = document.getElementById("dcToggle");

// Metric definitions. `key` is the per-ZIP field in nj_zip_info.json.
const METRICS = {
  lmp:  { key: "monthly_lmp",  label: "Day-Ahead LMP",    unit: "$/MWh",   prefix: "$", decimals: 2 },
  rate: { key: "monthly_rate", label: "Residential rate", unit: "¢/kWh",   prefix: "",  decimals: 2 },
  bill: { key: "monthly_bill", label: "Residential bill", unit: "$/month", prefix: "$", decimals: 0 },
};

function currentMetric() {
  return METRICS[metricSelectEl?.value || "lmp"] || METRICS.lmp;
}

function fmtMetric(m, v) {
  if (v === null || v === undefined || !Number.isFinite(Number(v))) return "N/A";
  const n = Number(v).toFixed(m.decimals);
  return `${m.prefix}${n} ${m.unit}`;
}

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

function getMonthValue(zip, year, month, metric) {
  const m = metric || currentMetric();
  const d = zipDetails[zip];
  if (!d) return null;
  const v = d[m.key]?.[monthKey(year, month)];
  return v !== null && v !== undefined && Number.isFinite(Number(v)) ? Number(v) : null;
}

// Back-compat alias — LMP is the default everywhere else assumes it.
function getMonthLmp(zip, year, month) {
  return getMonthValue(zip, year, month, METRICS.lmp);
}

function collectAvailableYears() {
  const years = new Set();
  Object.values(zipDetails).forEach((d) => {
    ["monthly_lmp", "monthly_rate", "monthly_bill"].forEach((k) => {
      if (d?.[k]) Object.keys(d[k]).forEach((mk) => years.add(mk.slice(0, 4)));
    });
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

function yearsInSeries(seriesObj) {
  if (!seriesObj) return [];
  const set = new Set();
  Object.keys(seriesObj).forEach((k) => set.add(k.slice(0, 4)));
  return Array.from(set).sort();
}

// Segment polyline points split on null values.
function polySegments(values, xOf, yOf) {
  const segments = [];
  let seg = [];
  values.forEach((v, i) => {
    if (v !== null) {
      seg.push(`${xOf(i).toFixed(1)},${yOf(v).toFixed(1)}`);
    } else if (seg.length) { segments.push(seg); seg = []; }
  });
  if (seg.length) segments.push(seg);
  return segments;
}

// Per-metric color so each sparkline reads as distinct when stacked.
const METRIC_STROKE = {
  lmp:  "#fb923c",    // orange — LMP
  rate: "#2dd4bf",    // teal   — rate
  bill: "#fbbf24",    // amber  — bill
};

function metricKeyFromLabel(metric) {
  return Object.keys(METRICS).find((k) => METRICS[k] === metric) || "lmp";
}

function buildSparkline(seriesObj, year, metric) {
  const m   = metric || currentMetric();
  const mKey = metricKeyFromLabel(m);
  const stroke = METRIC_STROKE[mKey] || "var(--accent)";

  const W = 280, H = 88, PAD_L = 6, PAD_R = 4, PAD_T = 8, PAD_B = 6;

  const years = yearsInSeries(seriesObj);
  if (years.length === 0) return "";

  const byYear = {};
  let gmin = Infinity, gmax = -Infinity;
  years.forEach((y) => {
    const vals = Array.from({ length: 12 }, (_, i) => {
      const v = seriesObj[monthKey(y, i + 1)];
      return v !== undefined && v !== null ? Number(v) : null;
    });
    byYear[y] = vals;
    vals.forEach((v) => { if (v !== null) { if (v < gmin) gmin = v; if (v > gmax) gmax = v; } });
  });
  if (gmin === Infinity) return "";

  const range = gmax - gmin || 1;
  const xOf = (i) => PAD_L + (i / 11) * (W - PAD_L - PAD_R);
  const yOf = (v) => (H - PAD_B) - ((v - gmin) / range) * (H - PAD_T - PAD_B);

  // 4 horizontal gridlines (including top/bottom).
  const gridLines = [0, 0.33, 0.66, 1].map((t) => {
    const yy = PAD_T + t * (H - PAD_T - PAD_B);
    return `<line x1="${PAD_L}" y1="${yy.toFixed(1)}" x2="${W - PAD_R}" y2="${yy.toFixed(1)}" stroke="rgba(138,147,162,0.08)" stroke-width="1"/>`;
  }).join("");

  const selYear = String(year);
  const others  = years.filter((y) => y !== selYear);

  // Non-selected years: muted slate, opacity climbs toward newest year.
  const backLines = others.map((y) => {
    const idx = years.indexOf(y);
    const t   = years.length > 1 ? idx / (years.length - 1) : 0;
    const col = `rgba(138, 147, 162, ${0.12 + 0.24 * t})`;
    return polySegments(byYear[y], xOf, yOf)
      .map((s) => `<polyline points="${s.join(" ")}" fill="none" stroke="${col}" stroke-width="1.1" stroke-linejoin="round"/>`)
      .join("");
  }).join("");

  // Selected year: full accent color, thicker, with dots and glow.
  const selVals = byYear[selYear] || Array(12).fill(null);
  const frontLines = polySegments(selVals, xOf, yOf)
    .map((s) => `<polyline points="${s.join(" ")}" fill="none" stroke="${stroke}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>`)
    .join("");
  const frontDots = selVals
    .map((v, i) => v !== null
      ? `<circle cx="${xOf(i).toFixed(1)}" cy="${yOf(v).toFixed(1)}" r="2.4" fill="${stroke}"/>`
      : "")
    .join("");

  const selMonth = Number(monthSliderEl.value);
  const sv = selVals[selMonth - 1];
  const highlight = sv !== null && sv !== undefined
    ? `<g>
         <circle cx="${xOf(selMonth - 1).toFixed(1)}" cy="${yOf(sv).toFixed(1)}" r="7" fill="${stroke}" opacity="0.2"/>
         <circle cx="${xOf(selMonth - 1).toFixed(1)}" cy="${yOf(sv).toFixed(1)}" r="4" fill="${stroke}" stroke="#171c23" stroke-width="1.5"/>
       </g>`
    : "";

  // Tiny year labels at the bottom, tabular so they stay aligned.
  const legend = years.map((y) => {
    const idx = years.indexOf(y);
    const t   = years.length > 1 ? idx / (years.length - 1) : 0;
    const color = y === selYear ? stroke : `rgba(138, 147, 162, ${0.45 + 0.35 * t})`;
    const weight = y === selYear ? "600" : "400";
    return `<span style="color:${color};font-weight:${weight}">${y}</span>`;
  }).join("");

  const rangeLabel = `${m.prefix}${gmin.toFixed(m.decimals)}–${m.prefix}${gmax.toFixed(m.decimals)}`;

  return `
    <div class="sparkline-wrap">
      <div class="sparkline-label">
        <span>${m.label} · ${m.unit}</span>
        <span class="spark-range">${rangeLabel}</span>
      </div>
      <svg class="sparkline" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
        ${gridLines}${backLines}${frontLines}${frontDots}${highlight}
      </svg>
      <div class="spark-axis">
        <span>Jan</span><span>Apr</span><span>Jul</span><span>Oct</span><span>Dec</span>
      </div>
      <div class="spark-legend">${legend}</div>
    </div>`;
}

// Utility → dot color (matches the metric colors used in the heatmap legend).
const UTILITY_DOT = {
  "PSE&G":                  "#f97316",
  "JCP&L":                  "#2dd4bf",
  "Atlantic City Electric": "#fbbf24",
  "Rockland Electric":      "#a78bfa",
};

function formatMetricValue(metric, v) {
  if (v === null || v === undefined || !Number.isFinite(Number(v))) {
    return `<span class="metric-value">—<span class="unit">${metric.unit}</span></span>`;
  }
  const n = Number(v).toFixed(metric.decimals);
  return `<span class="metric-value">${metric.prefix}${n}<span class="unit">${metric.unit}</span></span>`;
}

function buildMetricCard(metric, metricKey, value, subText) {
  return `
    <div class="metric-card" data-metric="${metricKey}">
      <div class="metric-label">${metric.label}</div>
      ${formatMetricValue(metric, value)}
      ${subText ? `<div class="metric-sub">${subText}</div>` : ""}
    </div>`;
}

function pctDelta(cur, base) {
  if (!Number.isFinite(cur) || !Number.isFinite(base) || base === 0) return null;
  return ((cur - base) / base) * 100;
}

function deltaSpan(pct, baseLabel) {
  if (pct === null || pct === undefined) return `<span style="color:var(--muted-dim)">no baseline</span>`;
  const cls  = pct >= 0 ? "delta-up" : "delta-down";
  const sign = pct > 0 ? "+" : "";
  const arrow = pct >= 0 ? "▲" : "▼";
  return `<span class="${cls}">${arrow} ${sign}${pct.toFixed(1)}%</span> <span style="color:var(--muted-dim)">vs ${baseLabel}</span>`;
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
  const mon   = MONTH_NAMES[month - 1];

  const lmpVal  = details.monthly_lmp?.[key]  ?? null;
  const rateVal = details.monthly_rate?.[key] ?? null;
  const billVal = details.monthly_bill?.[key] ?? null;
  const kwhVal  = details.monthly_kwh?.[key]  ?? null;

  // Baselines: same month, earliest available year for each metric.
  const allYears  = collectAvailableYears();
  const baseYear  = allYears[0] ?? year;
  const bKey      = monthKey(baseYear, month);
  const lmpBase   = details.monthly_lmp?.[bKey]  ?? null;
  const rateBase  = details.monthly_rate?.[bKey] ?? null;
  const billBase  = details.monthly_bill?.[bKey] ?? null;

  const utilName = details.utility_name || "—";
  const dot = UTILITY_DOT[utilName] || "var(--muted-dim)";

  infoEl.innerHTML = `
    <h2>${zip} <span class="zip-hash">·</span> <span style="font-size:0.68em;font-weight:500;color:var(--muted)">${mon} ${year}</span></h2>
    <div class="info-meta-row">
      <span class="pill">${details.county || "—"}</span>
      <span class="pill"><span class="pill-dot" style="background:${dot}"></span>${utilName}</span>
    </div>

    <div class="metric-grid">
      ${buildMetricCard(METRICS.lmp,  "lmp",  lmpVal,
        deltaSpan(pctDelta(lmpVal,  lmpBase),  baseYear))}
      ${buildMetricCard(METRICS.rate, "rate", rateVal,
        deltaSpan(pctDelta(rateVal, rateBase), baseYear))}
      ${buildMetricCard(METRICS.bill, "bill", billVal,
        kwhVal !== null ? `${safeNum(kwhVal)} kWh used` : deltaSpan(pctDelta(billVal, billBase), baseYear))}
    </div>

    <div class="info-row"><strong>Node</strong> <span class="info-value">${details.nearest_node || "—"} · ${details.node_zone || "—"}</span></div>
    <div class="info-row"><strong>Nearest DC</strong> <span class="info-value">${
      details.nearest_dc
        ? `${details.nearest_dc.name} · ${details.nearest_dc.miles.toFixed(1)} mi`
        : "—"
    }</span></div>

    <div class="info-section-label">All years — monthly trend</div>
    ${buildSparkline(details.monthly_lmp,  year, METRICS.lmp)}
    ${buildSparkline(details.monthly_rate, year, METRICS.rate)}
    ${buildSparkline(details.monthly_bill, year, METRICS.bill)}
  `;
}

// ─── Provider comparison chart ────────────────────────────────────────────────

// Dedup utilities present in zipDetails — each utility's monthly_rate / monthly_bill
// is duplicated across every ZIP it serves, so one ZIP per utility is enough.
function collectUtilitySeries() {
  const utils = {};
  Object.values(zipDetails).forEach((d) => {
    if (!d?.utility_name || utils[d.utility_name]) return;
    utils[d.utility_name] = {
      monthly_rate: d.monthly_rate || {},
      monthly_bill: d.monthly_bill || {},
    };
  });
  return utils;
}

function buildProviderChart(metric) {
  const m = metric || currentMetric();
  const key = m.key;
  if (key !== "monthly_rate" && key !== "monthly_bill") return "";

  const utils = collectUtilitySeries();
  const names = Object.keys(utils).sort();
  if (!names.length) return "";

  const allMonths = new Set();
  names.forEach((n) => Object.keys(utils[n][key] || {}).forEach((k) => allMonths.add(k)));
  const months = Array.from(allMonths).sort();
  if (!months.length) return "";

  let gmin = Infinity, gmax = -Infinity;
  const seriesByUtil = {};
  names.forEach((n) => {
    const vals = months.map((mk) => {
      const v = utils[n][key]?.[mk];
      return v !== null && v !== undefined && Number.isFinite(Number(v)) ? Number(v) : null;
    });
    seriesByUtil[n] = vals;
    vals.forEach((v) => { if (v !== null) { if (v < gmin) gmin = v; if (v > gmax) gmax = v; } });
  });
  if (gmin === Infinity) return "";

  const yPad = (gmax - gmin || 1) * 0.08;
  const yMin = gmin - yPad;
  const yMax = gmax + yPad;

  const W = 322, H = 150;
  const PAD_L = 40, PAD_R = 8, PAD_T = 10, PAD_B = 24;

  const xOf = (i) => months.length === 1
    ? PAD_L + (W - PAD_L - PAD_R) / 2
    : PAD_L + (i / (months.length - 1)) * (W - PAD_L - PAD_R);
  const yOf = (v) => PAD_T + (1 - (v - yMin) / (yMax - yMin)) * (H - PAD_T - PAD_B);

  // 4 y-axis ticks with labels
  const tickCount = 4;
  const yAxisSvg = Array.from({ length: tickCount }, (_, i) => {
    const t = i / (tickCount - 1);
    const v = yMax - t * (yMax - yMin);
    const y = PAD_T + t * (H - PAD_T - PAD_B);
    return `<line x1="${PAD_L}" y1="${y.toFixed(1)}" x2="${W - PAD_R}" y2="${y.toFixed(1)}" stroke="rgba(138,147,162,0.12)" stroke-width="1"/>` +
           `<text x="${PAD_L - 5}" y="${(y + 3).toFixed(1)}" font-size="9" text-anchor="end" fill="#5e6773" font-family="ui-monospace, monospace">${m.prefix}${v.toFixed(m.decimals)}</text>`;
  }).join("");

  // X-axis year labels at year boundaries
  const years = Array.from(new Set(months.map((mk) => mk.slice(0, 4))));
  const xLabelsSvg = years.map((y) => {
    const firstIdx = months.findIndex((mk) => mk.startsWith(y));
    const x = xOf(firstIdx);
    return `<text x="${x.toFixed(1)}" y="${H - 8}" font-size="9" fill="#5e6773" font-family="ui-monospace, monospace">${y}</text>`;
  }).join("");

  const polylines = names.map((n) => {
    const stroke = UTILITY_DOT[n] || "#8a93a2";
    return polySegments(seriesByUtil[n], xOf, yOf)
      .map((s) => `<polyline points="${s.join(" ")}" fill="none" stroke="${stroke}" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round" opacity="0.92"/>`)
      .join("");
  }).join("");

  // Vertical guide at the currently-selected month
  const selYear  = yearSelectEl.value;
  const selMonth = Number(monthSliderEl.value);
  const selIdx   = months.indexOf(monthKey(selYear, selMonth));
  const selLine = selIdx >= 0
    ? `<line x1="${xOf(selIdx).toFixed(1)}" y1="${PAD_T}" x2="${xOf(selIdx).toFixed(1)}" y2="${H - PAD_B}" stroke="#f97316" stroke-width="1" stroke-dasharray="2,3" opacity="0.55"/>`
    : "";

  // Dots on each line at the selected month
  const selDots = selIdx >= 0 ? names.map((n) => {
    const v = seriesByUtil[n][selIdx];
    if (v === null) return "";
    const stroke = UTILITY_DOT[n] || "#8a93a2";
    return `<circle cx="${xOf(selIdx).toFixed(1)}" cy="${yOf(v).toFixed(1)}" r="2.6" fill="${stroke}" stroke="#171c23" stroke-width="1"/>`;
  }).join("") : "";

  return `
    <div class="provider-chart-wrap">
      <div class="provider-chart-label">
        <span>${m.label}</span>
        <span class="provider-chart-unit">${m.unit}</span>
      </div>
      <svg class="provider-chart" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
        ${yAxisSvg}${polylines}${selLine}${selDots}${xLabelsSvg}
      </svg>
    </div>
  `;
}

function renderProviderCharts() {
  const wrapEl = document.getElementById("providerCharts");
  if (!wrapEl) return;
  const utils = collectUtilitySeries();
  const names = Object.keys(utils).sort();
  if (!names.length) { wrapEl.innerHTML = ""; return; }

  const legend = names.map((n) => {
    const c = UTILITY_DOT[n] || "#8a93a2";
    return `<span class="provider-legend-item"><span class="provider-legend-dot" style="background:${c}"></span>${n}</span>`;
  }).join("");

  wrapEl.innerHTML =
    buildProviderChart(METRICS.rate) +
    buildProviderChart(METRICS.bill) +
    `<div class="provider-legend">${legend}</div>`;
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

function computeMinMax(year, month, metric) {
  const m = metric || currentMetric();
  let min = Infinity, max = -Infinity;
  for (const zip of layerByZip.keys()) {
    const v = getMonthValue(zip, year, month, m);
    if (v !== null) { if (v < min) min = v; if (v > max) max = v; }
  }
  return min <= max ? { min, max } : { min: 0, max: 1 };
}

function applyHeatmap() {
  const year   = yearSelectEl.value;
  const month  = Number(monthSliderEl.value);
  const metric = currentMetric();
  const { min, max } = computeMinMax(year, month, metric);
  const range = max - min || 1;

  layerByZip.forEach((layer, zip) => {
    const v = getMonthValue(zip, year, month, metric);
    const style = v !== null
      ? { fillColor: lmpColor((v - min) / range), fillOpacity: 0.75, color: "#555", weight: 0.5 }
      : { fillColor: "#cccccc", fillOpacity: 0.45, color: "#555", weight: 0.5 };
    layer.setStyle(style);
  });
  if (selectedLayer) selectedLayer.setStyle({ ...selectedLayer.options, color: "#003049", weight: 2 });
  showLegend(min, max, year, month, metric);
}

function clearHeatmap() {
  layerByZip.forEach((layer, zip) => {
    layer.setStyle(zip === selectedZip ? selectedStyle() : baseStyle());
  });
  if (legendControl) { legendControl.remove(); legendControl = null; }
}

function showLegend(min, max, year, month, metric) {
  const m = metric || currentMetric();
  if (legendControl) legendControl.remove();
  legendControl = L.control({ position: "bottomright" });
  legendControl.onAdd = () => {
    const div = L.DomUtil.create("div", "legend");
    div.innerHTML = `
      <div class="legend-title">${m.label} ${MONTH_NAMES[month - 1]} ${year} (${m.unit})</div>
      <div class="legend-bar"></div>
      <div class="legend-labels">
        <span>${min.toFixed(m.decimals)}</span>
        <span>${((min + max) / 2).toFixed(m.decimals)}</span>
        <span>${max.toFixed(m.decimals)}</span>
      </div>
      <div class="legend-na"><span class="legend-swatch"></span> No data</div>
    `;
    return div;
  };
  legendControl.addTo(map);
}

// ─── Map styles ───────────────────────────────────────────────────────────────

function baseStyle() {
  return { color: "#6b7280", weight: 0.6, fillColor: "#f97316", fillOpacity: 0.08 };
}

function selectedStyle() {
  return { color: "#f97316", weight: 2.2, fillColor: "#f97316", fillOpacity: 0.35 };
}

function selectLayer(layer, zip) {
  if (selectedLayer) {
    if (heatmapEnabled) {
      const year   = yearSelectEl.value;
      const month  = Number(monthSliderEl.value);
      const metric = currentMetric();
      const { min, max } = computeMinMax(year, month, metric);
      const v = getMonthValue(selectedZip, year, month, metric);
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
      radius: 7,
      color: "#171c23",
      weight: 1.5,
      fillColor: "#fbbf24",
      fillOpacity: 0.95,
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
    renderProviderCharts();
    updateDcVisibility();
  });

  monthSliderEl.addEventListener("input", () => {
    updateMonthLabel();
    if (selectedZip) renderZipInfo(selectedZip);
    if (heatmapEnabled) applyHeatmap();
    renderProviderCharts();
    updateDcVisibility();
  });

  heatmapToggleEl.addEventListener("change", () => {
    heatmapEnabled = heatmapToggleEl.checked;
    if (heatmapEnabled) applyHeatmap();
    else clearHeatmap();
  });

  if (metricSelectEl) {
    metricSelectEl.addEventListener("change", () => {
      if (heatmapEnabled) applyHeatmap();
      if (selectedZip) renderZipInfo(selectedZip);
    });
  }

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
  renderProviderCharts();
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
