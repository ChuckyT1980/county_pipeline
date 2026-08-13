/* California Interactive Parcel Map — High Scale 13.2M Parcel Controller */

// App State
let currentLevel = 1; // 1: State, 2: County, 3: Parcel
let selectedCounty = null;
let selectedCity = null;
let selectedParcel = null;

let countyLayerGroup = L.layerGroup();
let cityLayerGroup = L.layerGroup();
let parcelLayerGroup = L.layerGroup();

let selectedParcelLayer = null;

// Initialize Map
const map = L.map('map', {
  center: [37.2, -119.5],
  zoom: 6,
  zoomControl: true,
  attributionControl: false
});

// CartoDB Dark Matter Base Tiles
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
  maxZoom: 19,
  subdomains: 'abcd'
}).addTo(map);

countyLayerGroup.addTo(map);
cityLayerGroup.addTo(map);
parcelLayerGroup.addTo(map);

// Color mappings for Land Use (Level 3)
const LAND_USE_COLORS = {
  "Single Family Residential": "#00f3ff",
  "Multi-Family Residential": "#a855f7",
  "Commercial": "#ffd700",
  "Industrial": "#ff007f",
  "Agricultural": "#00ff9d",
  "Vacant Land": "#94a3b8"
};

// Initial Load
document.addEventListener("DOMContentLoaded", () => {
  loadStateCounties();
  setupSearch();
  fetchStats();
});

// Fetch Global Stats
function fetchStats() {
  fetch('/api/stats')
    .then(res => res.json())
    .then(data => {
      document.getElementById('stat-counties').innerText = `${data.total_counties} CA Counties`;
      document.getElementById('stat-parcels').innerText = `${(data.total_parcels / 1000000).toFixed(1)}M CA Parcels`;
    })
    .catch(err => console.error("Error fetching stats:", err));
}

// -------------------------------------------------------------
// LEVEL 1: State View (Vibrant 58 Counties)
// -------------------------------------------------------------
function loadStateCounties() {
  currentLevel = 1;
  updateUILevel();
  updateLegendForLevel(1);

  countyLayerGroup.clearLayers();
  cityLayerGroup.clearLayers();
  parcelLayerGroup.clearLayers();

  fetch('/api/boundaries/counties')
    .then(res => res.json())
    .then(data => {
      const geojson = L.geoJSON(data, {
        style: (feature) => {
          const color = feature.properties.color || '#00f3ff';
          return {
            color: color,
            weight: 1.8,
            fillColor: color,
            fillOpacity: 0.3
          };
        },
        onEachFeature: (feature, layer) => {
          const props = feature.properties;
          const countyName = props.name;
          const parcelEst = props.parcel_count ? props.parcel_count.toLocaleString() : 'N/A';
          const region = props.region || 'California';

          layer.bindTooltip(`
            <div style="font-family:'Inter',sans-serif; padding:4px;">
              <strong style="font-size:0.95rem; color:#ffffff;">${countyName} County</strong><br>
              <span style="color:#00f3ff; font-weight:600;">Region: ${region}</span><br>
              <span style="color:#ffd700;">Est. Parcels: ${parcelEst}</span>
            </div>
          `, { sticky: true });

          layer.on({
            mouseover: (e) => {
              e.target.setStyle({
                fillOpacity: 0.65,
                weight: 3.5
              });
            },
            mouseout: (e) => {
              geojson.resetStyle(e.target);
            },
            click: (e) => {
              selectCounty(countyName, layer.getBounds(), props);
            }
          });
        }
      });
      countyLayerGroup.addLayer(geojson);
    })
    .catch(err => console.error("Error loading counties:", err));
}

function selectCounty(countyName, bounds, props) {
  selectedCounty = countyName;
  currentLevel = 2;
  updateUILevel();
  updateLegendForLevel(2);

  countyLayerGroup.clearLayers();
  map.flyToBounds(bounds, { padding: [40, 40], duration: 1.2 });

  showCountyInspector(props);
  loadCountyCities(countyName);
}

function showCountyInspector(props) {
  const body = document.getElementById('inspector-body');
  body.innerHTML = `
    <div class="detail-group">
      <div class="detail-group-title">County Region</div>
      <div class="detail-row">
        <span class="detail-label">County</span>
        <span class="detail-value highlight">${props.name}</span>
      </div>
      <div class="detail-row">
        <span class="detail-label">Region</span>
        <span class="detail-value" style="color:${props.color}">${props.region}</span>
      </div>
      <div class="detail-row">
        <span class="detail-label">FIPS Code</span>
        <span class="detail-value">06${props.fips}</span>
      </div>
      <div class="detail-row">
        <span class="detail-label">Est. Parcel Count</span>
        <span class="detail-value highlight">${(props.parcel_count || 0).toLocaleString()}</span>
      </div>
    </div>
    <div class="placeholder-msg">
      👇 Click any <strong>city boundary</strong> to inspect individual parcel vector polygons!
    </div>
  `;
}

// -------------------------------------------------------------
// LEVEL 2: County View (Cities & Places)
// -------------------------------------------------------------
function loadCountyCities(countyName) {
  cityLayerGroup.clearLayers();
  parcelLayerGroup.clearLayers();

  fetch(`/api/boundaries/cities?county=${encodeURIComponent(countyName)}`)
    .then(res => res.json())
    .then(data => {
      const geojson = L.geoJSON(data, {
        style: (feature) => {
          const color = feature.properties.color || '#00ff9d';
          return {
            color: color,
            weight: 2,
            fillColor: color,
            fillOpacity: 0.45
          };
        },
        onEachFeature: (feature, layer) => {
          const cityName = feature.properties.name;
          layer.bindTooltip(`<strong>${cityName}</strong><br><span style="color:#00ff9d;">Click to view parcel vectors</span>`, { sticky: true });

          layer.on({
            mouseover: (e) => {
              e.target.setStyle({
                fillOpacity: 0.75,
                weight: 3.5
              });
            },
            mouseout: (e) => {
              geojson.resetStyle(e.target);
            },
            click: (e) => {
              selectCity(cityName, layer.getBounds());
            }
          });
        }
      });
      cityLayerGroup.addLayer(geojson);
    })
    .catch(err => console.error("Error loading cities:", err));
}

function selectCity(cityName, bounds) {
  selectedCity = cityName;
  currentLevel = 3;
  updateUILevel();
  updateLegendForLevel(3);

  cityLayerGroup.clearLayers();
  map.flyToBounds(bounds, { padding: [20, 20], duration: 1.2 });

  loadCityParcels(cityName);
}

// -------------------------------------------------------------
// LEVEL 3: City View (Vibrant Parcel Vectors)
// -------------------------------------------------------------
function loadCityParcels(cityName) {
  parcelLayerGroup.clearLayers();

  fetch(`/api/parcels?city=${encodeURIComponent(cityName)}&limit=600`)
    .then(res => res.json())
    .then(data => {
      const geojson = L.geoJSON(data, {
        style: (feature) => {
          const landUse = feature.properties.land_use;
          const color = LAND_USE_COLORS[landUse] || feature.properties.color_code || '#00f3ff';
          return {
            color: '#070a14',
            weight: 1.2,
            fillColor: color,
            fillOpacity: 0.8
          };
        },
        onEachFeature: (feature, layer) => {
          const props = feature.properties;
          layer.bindTooltip(`<strong>APN: ${props.apn}</strong><br>${props.address}`, { sticky: true });

          layer.on({
            mouseover: (e) => {
              if (selectedParcelLayer !== e.target) {
                e.target.setStyle({ weight: 2.5, color: '#ffffff' });
              }
            },
            mouseout: (e) => {
              if (selectedParcelLayer !== e.target) {
                geojson.resetStyle(e.target);
              }
            },
            click: (e) => {
              if (selectedParcelLayer) {
                geojson.resetStyle(selectedParcelLayer);
              }
              selectedParcelLayer = e.target;
              e.target.setStyle({
                weight: 4,
                color: '#FFD700',
                fillColor: '#FFD700',
                fillOpacity: 0.95
              });
              showParcelInspector(props);
            }
          });
        }
      });
      parcelLayerGroup.addLayer(geojson);
    })
    .catch(err => console.error("Error loading parcels:", err));
}

// -------------------------------------------------------------
// Side Property Inspector UI
// -------------------------------------------------------------
function showParcelInspector(props) {
  selectedParcel = props;
  updateUILevel();

  const body = document.getElementById('inspector-body');
  body.innerHTML = `
    <div class="detail-group">
      <div class="detail-group-title">Parcel Identifier</div>
      <div class="detail-row">
        <span class="detail-label">APN</span>
        <span class="detail-value highlight">${props.apn}</span>
      </div>
      <div class="detail-row">
        <span class="detail-label">County</span>
        <span class="detail-value">${props.county}</span>
      </div>
      <div class="detail-row">
        <span class="detail-label">City</span>
        <span class="detail-value">${props.city}</span>
      </div>
    </div>

    <div class="detail-group">
      <div class="detail-group-title">Assessor Valuation</div>
      <div class="detail-row">
        <span class="detail-label">Total Assessed</span>
        <span class="detail-value highlight">$${props.assessed_value.toLocaleString()}</span>
      </div>
      <div class="detail-row">
        <span class="detail-label">Land Value</span>
        <span class="detail-value">$${props.land_value.toLocaleString()}</span>
      </div>
      <div class="detail-row">
        <span class="detail-label">Improvement Value</span>
        <span class="detail-value">$${props.improvement_value.toLocaleString()}</span>
      </div>
    </div>

    <div class="detail-group">
      <div class="detail-group-title">Property Details</div>
      <div class="detail-row">
        <span class="detail-label">Address</span>
        <span class="detail-value">${props.address}</span>
      </div>
      <div class="detail-row">
        <span class="detail-label">Owner</span>
        <span class="detail-value">${props.owner_name}</span>
      </div>
      <div class="detail-row">
        <span class="detail-label">Land Use</span>
        <span class="detail-value" style="color:${props.color_code || '#00f3ff'}; font-weight:700;">${props.land_use}</span>
      </div>
      <div class="detail-row">
        <span class="detail-label">Lot Size</span>
        <span class="detail-value">${props.lot_size_sqft.toLocaleString()} sq ft (${props.lot_size_acres} acres)</span>
      </div>
      <div class="detail-row">
        <span class="detail-label">Year Built</span>
        <span class="detail-value">${props.year_built || 'N/A'}</span>
      </div>
    </div>
  `;
}

// -------------------------------------------------------------
// Navigation & Reset Handlers
// -------------------------------------------------------------
function resetToState() {
  selectedCounty = null;
  selectedCity = null;
  selectedParcel = null;
  selectedParcelLayer = null;

  map.flyTo([37.2, -119.5], 6, { duration: 1.2 });
  loadStateCounties();

  const body = document.getElementById('inspector-body');
  body.innerHTML = `
    <div class="placeholder-msg">
      👈 <strong>Click on any county</strong> to drill into cities.<br><br>
      Click a <strong>city polygon</strong> to load parcel vectors.<br><br>
      Click any <strong>parcel</strong> to inspect full assessor records across California's 13.2M parcels!
    </div>
  `;
}

function resetToCounty() {
  if (!selectedCounty) return;
  selectedCity = null;
  selectedParcel = null;
  selectedParcelLayer = null;

  currentLevel = 2;
  updateUILevel();
  updateLegendForLevel(2);
  parcelLayerGroup.clearLayers();

  loadCountyCities(selectedCounty);
}

function updateUILevel() {
  const badge = document.getElementById('level-badge');
  const inspectBadge = document.getElementById('inspect-status-badge');

  const crumbCounty = document.getElementById('crumb-county');
  const crumbCity = document.getElementById('crumb-city');
  const crumbParcel = document.getElementById('crumb-parcel');

  const sep1 = document.getElementById('sep-1');
  const sep2 = document.getElementById('sep-2');
  const sep3 = document.getElementById('sep-3');

  if (currentLevel === 1) {
    badge.innerText = "LEVEL 1: STATE VIEW";
    badge.style.color = "#00f3ff";
    badge.style.borderColor = "#00f3ff";
    inspectBadge.innerText = "STATE VIEW";

    crumbCounty.style.display = "none";
    crumbCity.style.display = "none";
    crumbParcel.style.display = "none";
    sep1.style.display = "none";
    sep2.style.display = "none";
    sep3.style.display = "none";
  } else if (currentLevel === 2) {
    badge.innerText = `LEVEL 2: ${selectedCounty.toUpperCase()} COUNTY`;
    badge.style.color = "#00ff9d";
    badge.style.borderColor = "#00ff9d";
    inspectBadge.innerText = "COUNTY VIEW";

    crumbCounty.innerText = selectedCounty + " County";
    crumbCounty.style.display = "inline";
    crumbCounty.className = "crumb active";
    crumbCity.style.display = "none";
    crumbParcel.style.display = "none";
    sep1.style.display = "inline";
    sep2.style.display = "none";
    sep3.style.display = "none";
  } else if (currentLevel === 3) {
    badge.innerText = `LEVEL 3: ${selectedCity.toUpperCase()} PARCELS`;
    badge.style.color = "#ffd700";
    badge.style.borderColor = "#ffd700";
    inspectBadge.innerText = selectedParcel ? "PARCEL INSPECTOR" : "PARCEL VIEW";

    crumbCounty.className = "crumb";
    crumbCity.innerText = selectedCity;
    crumbCity.style.display = "inline";
    crumbCity.className = "crumb active";
    sep1.style.display = "inline";
    sep2.style.display = "inline";

    if (selectedParcel) {
      crumbCity.className = "crumb";
      crumbParcel.innerText = "APN " + selectedParcel.apn;
      crumbParcel.style.display = "inline";
      crumbParcel.className = "crumb active";
      sep3.style.display = "inline";
    } else {
      crumbParcel.style.display = "none";
      sep3.style.display = "none";
    }
  }
}

function updateLegendForLevel(level) {
  const legendTitle = document.getElementById('legend-title');
  const legendItems = document.getElementById('legend-items');

  if (level === 1 || level === 2) {
    legendTitle.innerText = "Regional Color Palette";
    legendItems.innerHTML = `
      <div class="legend-item"><div class="legend-color" style="background:#00f3ff;"></div> Bay Area</div>
      <div class="legend-item"><div class="legend-color" style="background:#ff007f;"></div> Southern CA</div>
      <div class="legend-item"><div class="legend-color" style="background:#fb923c;"></div> Central Valley</div>
      <div class="legend-item"><div class="legend-color" style="background:#38bdf8;"></div> Central Coast</div>
      <div class="legend-item"><div class="legend-color" style="background:#facc15;"></div> Sacramento Valley</div>
      <div class="legend-item"><div class="legend-color" style="background:#34d399;"></div> Northern CA</div>
      <div class="legend-item"><div class="legend-color" style="background:#a855f7;"></div> Sierra Region</div>
    `;
  } else {
    legendTitle.innerText = "Land Use Color Key";
    legendItems.innerHTML = `
      <div class="legend-item"><div class="legend-color" style="background:#00f3ff;"></div> Single Family</div>
      <div class="legend-item"><div class="legend-color" style="background:#a855f7;"></div> Multi-Family</div>
      <div class="legend-item"><div class="legend-color" style="background:#ffd700;"></div> Commercial</div>
      <div class="legend-item"><div class="legend-color" style="background:#ff007f;"></div> Industrial</div>
      <div class="legend-item"><div class="legend-color" style="background:#00ff9d;"></div> Agricultural</div>
      <div class="legend-item"><div class="legend-color" style="background:#94a3b8;"></div> Vacant</div>
    `;
  }
}

// -------------------------------------------------------------
// Real-time Search Logic
// -------------------------------------------------------------
function setupSearch() {
  const input = document.getElementById('search-input');
  const resultsDiv = document.getElementById('search-results');

  let debounceTimer;

  input.addEventListener('input', (e) => {
    clearTimeout(debounceTimer);
    const q = e.target.value.trim();

    if (q.length < 2) {
      resultsDiv.style.display = 'none';
      return;
    }

    debounceTimer = setTimeout(() => {
      fetch(`/api/search?q=${encodeURIComponent(q)}`)
        .then(res => res.json())
        .then(results => {
          if (results.length === 0) {
            resultsDiv.innerHTML = `<div class="search-item"><div class="search-item-sub">No matching parcels found</div></div>`;
          } else {
            resultsDiv.innerHTML = results.map(r => `
              <div class="search-item" onclick='jumpToSearchResult(${JSON.stringify(r).replace(/'/g, "&apos;")})'>
                <div class="search-item-title">${r.apn} &mdash; ${r.address}</div>
                <div class="search-item-sub">Owner: ${r.owner_name} | City: ${r.city} | Value: $${r.assessed_value.toLocaleString()}</div>
              </div>
            `).join('');
          }
          resultsDiv.style.display = 'block';
        })
        .catch(err => console.error("Search error:", err));
    }, 250);
  });

  document.addEventListener('click', (e) => {
    if (!input.contains(e.target) && !resultsDiv.contains(e.target)) {
      resultsDiv.style.display = 'none';
    }
  });
}

function jumpToSearchResult(parcel) {
  document.getElementById('search-results').style.display = 'none';
  document.getElementById('search-input').value = parcel.apn;

  selectedCounty = parcel.county;
  selectedCity = parcel.city;
  currentLevel = 3;
  updateUILevel();
  updateLegendForLevel(3);

  map.flyTo([parcel.centroid_lat, parcel.centroid_lon], 18, { duration: 1.5 });
  loadCityParcels(parcel.city);
  showParcelInspector(parcel);
}
