const NJ_GEOJSON_URL =
  "https://raw.githubusercontent.com/OpenDataDE/State-zip-code-GeoJSON/master/nj_new_jersey_zip_codes_geo.min.json";

const map = L.map("map", {
  zoomControl: true,
}).setView([40.0583, -74.4057], 8);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 18,
  attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);

const infoEl = document.getElementById("info");
const zipSearchEl = document.getElementById("zipSearch");
const searchBtnEl = document.getElementById("searchBtn");
const yearSelectEl = document.getElementById("yearSelect");

const layerByZip = new Map();
let selectedLayer = null;
let zipDetails = {};
let selectedZip = null;

function safeNum(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "N/A";
  }
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function collectAvailableYears() {
  const years = new Set();

  Object.values(zipDetails).forEach((details) => {
    if (details && details.yearly_lmp && typeof details.yearly_lmp === "object") {
      Object.keys(details.yearly_lmp).forEach((year) => years.add(String(year)));
    }

    if (details && typeof details === "object") {
      Object.keys(details).forEach((k) => {
        const match = k.match(/^avg_lmp_(\d{4})$/);
        if (match) {
          years.add(match[1]);
        }
      });
    }
  });

  if (years.size === 0) {
    ["2020", "2021", "2022", "2023", "2024", "2025"].forEach((year) => years.add(year));
  }

  return Array.from(years).sort((a, b) => Number(a) - Number(b));
}

function populateYearSelect() {
  const years = collectAvailableYears();
  yearSelectEl.innerHTML = "";

  years.forEach((year) => {
    const option = document.createElement("option");
    option.value = year;
    option.textContent = year;
    yearSelectEl.appendChild(option);
  });

  if (years.length > 0) {
    yearSelectEl.value = years[years.length - 1];
  }
}

function renderZipInfo(zip) {
  const details = zipDetails[zip];

  if (!details) {
    infoEl.innerHTML = `
      <h2>ZIP ${zip}</h2>
      <p>No local metrics loaded for this ZIP yet.</p>
      <p class="info-row">Tip: add this ZIP in nj_zip_info.json</p>
    `;
    return;
  }

  const yearly = details.yearly_lmp || {};
  const selectedYear = String(yearSelectEl.value || details.selected_year || "");
  const selectedYearValue = yearly[selectedYear] ?? details[`avg_lmp_${selectedYear}`];

  const allYears = collectAvailableYears();
  const baseYear = allYears.length > 0 ? allYears[0] : "2020";
  const baseValue = yearly[baseYear] ?? details[`avg_lmp_${baseYear}`];

  let selectedVsBase = null;
  if (Number(baseValue) > 0 && Number.isFinite(Number(selectedYearValue))) {
    selectedVsBase = ((Number(selectedYearValue) - Number(baseValue)) / Number(baseValue)) * 100;
  }

  infoEl.innerHTML = `
    <h2>ZIP ${zip}</h2>
    <div class="info-row"><strong>County:</strong> ${details.county || "N/A"}</div>
    <div class="info-row"><strong>Avg DA LMP ${selectedYear} ($/MWh):</strong> ${safeNum(selectedYearValue)}</div>
    <div class="info-row"><strong>Avg DA LMP ${baseYear} ($/MWh):</strong> ${safeNum(baseValue)}</div>
    <div class="info-row"><strong>Change ${baseYear} to ${selectedYear}:</strong> ${safeNum(selectedVsBase)}%</div>
    <div class="info-row"><strong>Notes:</strong> ${details.notes || "-"}</div>
  `;
}

function baseStyle() {
  return {
    color: "#3b4f62",
    weight: 1,
    fillColor: "#7cc6d4",
    fillOpacity: 0.35,
  };
}

function selectedStyle() {
  return {
    color: "#003049",
    weight: 2,
    fillColor: "#006d77",
    fillOpacity: 0.55,
  };
}

function selectLayer(layer, zip) {
  if (selectedLayer) {
    selectedLayer.setStyle(baseStyle());
  }
  selectedLayer = layer;
  selectedLayer.setStyle(selectedStyle());
  selectedZip = zip;

  const details = zipDetails[zip];
  if (details && details.selected_year) {
    yearSelectEl.value = String(details.selected_year);
  }

  renderZipInfo(zip);
}

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
  const response = await fetch(NJ_GEOJSON_URL);
  const geo = await response.json();

  const layer = L.geoJSON(geo, {
    style: baseStyle,
    onEachFeature: (feature, featureLayer) => {
      const zip = String(feature.properties.ZCTA5CE10 || "");
      layerByZip.set(zip, featureLayer);
      featureLayer.bindTooltip(`ZIP ${zip}`, {
        className: "zip-label",
        sticky: true,
      });
      featureLayer.on("click", () => {
        selectLayer(featureLayer, zip);
      });
    },
  });

  layer.addTo(map);
  map.fitBounds(layer.getBounds());
}

function setupSearch() {
  function goToZip() {
    const zip = zipSearchEl.value.trim();
    const target = layerByZip.get(zip);

    if (!target) {
      infoEl.innerHTML = `
        <h2>ZIP not found</h2>
        <p>No shape found for ZIP ${zip || "(blank)"}.</p>
      `;
      return;
    }

    map.fitBounds(target.getBounds(), { maxZoom: 11 });
    selectLayer(target, zip);
  }

  searchBtnEl.addEventListener("click", goToZip);
  zipSearchEl.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      goToZip();
    }
  });

  yearSelectEl.addEventListener("change", () => {
    if (selectedZip) {
      renderZipInfo(selectedZip);
    }
  });
}

(async function init() {
  await loadZipDetails();
  populateYearSelect();
  await buildZipLayer();
  setupSearch();
})();
