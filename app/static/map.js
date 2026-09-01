/* Pittsburg County petition map — vanilla JS, no build step.
 *
 * Host page must load Leaflet 1.9.4 BEFORE this file:
 *   <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
 *   <script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
 *   <link rel="stylesheet" href="/static/map.css">
 *   <script src="/static/map.js"></script>
 *
 * Usage:
 *   const m = initPetitionMap(document.getElementById('map'), {
 *     precinctsUrl: '/static/precincts/pittsburg_web.geojson',   // required (FeatureCollection, EPSG:4326)
 *     locationsUrl: '/api/locations.geojson',                    // optional: signing locations (Point features)
 *     pollingPlaces: true,                                       // optional: markers from precinct props
 *     districtsUrl: '/static/precincts/commissioner_districts.geojson',  // optional
 *     municipalitiesUrl: '/static/precincts/municipalities.geojson',     // optional
 *     countyUrl: '/static/precincts/county.geojson',             // optional
 *     finderUrl: '/api/precinct?address=',                       // optional: enables the address box
 *     fitBounds: true, tiles: 'osm'                              // 'osm' | 'carto'
 *   });
 *   m.refreshLocations();   // re-fetch locationsUrl (e.g. after admin edits)
 *   m.map                   // the Leaflet map
 *
 * Signing-location feature properties expected: name, address, city, zip, hours, status (planned|active|closed),
 * next_event (text, optional), precinct (int, optional), url (optional).
 * Precinct feature properties (from toolkit.geo.fetch): precinct, polling_place, address, city, pop2020, vap2020,
 * comm, label_lat, label_lon.
 */
(function () {
  'use strict';

  var STATUS_COLOR = { active: '#1e7f4b', planned: '#f2b705', closed: '#8a8580' };

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function fmt(n) { return n == null ? '—' : Number(n).toLocaleString(); }
  function getJSON(url) {
    return fetch(url, { headers: { Accept: 'application/json' } }).then(function (r) {
      if (!r.ok) throw new Error(url + ' -> ' + r.status);
      return r.json();
    });
  }
  function pointInRing(pt, ring) {
    var x = pt[0], y = pt[1], inside = false;
    for (var i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      var xi = ring[i][0], yi = ring[i][1], xj = ring[j][0], yj = ring[j][1];
      var intersect = ((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi);
      if (intersect) inside = !inside;
    }
    return inside;
  }
  function pointInPolygon(pt, geom) {
    var polys = geom.type === 'Polygon' ? [geom.coordinates] : geom.type === 'MultiPolygon' ? geom.coordinates : [];
    for (var p = 0; p < polys.length; p++) {
      if (pointInRing(pt, polys[p][0])) {
        var inHole = false;
        for (var h = 1; h < polys[p].length; h++) if (pointInRing(pt, polys[p][h])) { inHole = true; break; }
        if (!inHole) return true;
      }
    }
    return false;
  }

  function initPetitionMap(el, opts) {
    if (typeof L === 'undefined') throw new Error('Leaflet must be loaded before map.js');
    opts = opts || {};
    if (!opts.precinctsUrl) throw new Error('initPetitionMap: precinctsUrl is required');
    var fitBounds = opts.fitBounds !== false;

    el.classList.add('pmap-wrap');
    var mapEl = document.createElement('div');
    mapEl.className = 'pmap-canvas';
    mapEl.style.cssText = 'position:absolute;top:0;right:0;bottom:0;left:0;width:100%;height:100%';
    mapEl.style.width = '100%'; mapEl.style.height = '100%';
    el.appendChild(mapEl);

    var map = L.map(mapEl, { center: [34.93, -95.75], zoom: 10, tap: true, zoomControl: true });
    var tiles = opts.tiles === 'carto'
      ? L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>' })
      : L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' });
    tiles.addTo(map);

    var state = { precincts: null, locations: null, coverage: false, precinctLayer: null, labelLayer: L.layerGroup(),
      pollLayer: L.layerGroup(), locLayer: L.layerGroup(), youLayer: L.layerGroup(), overlays: {} };
    var pane = map.createPane('labels'); pane.style.zIndex = 650; pane.style.pointerEvents = 'none';

    function locsInPrecinct(num) {
      if (!state.locations) return [];
      return state.locations.features.filter(function (f) { return f.properties && Number(f.properties.precinct) === Number(num); });
    }
    function activeCount(num) {
      return locsInPrecinct(num).filter(function (f) { return f.properties.status === 'active'; }).length;
    }
    function coverageColor(n) {
      if (!n) return '#fff3c4';
      var t = Math.min(n, 4) / 4;
      var a = [255, 243, 196], b = [30, 111, 184];
      return 'rgb(' + a.map(function (v, i) { return Math.round(v + (b[i] - v) * t); }).join(',') + ')';
    }
    function precinctStyle(f) {
      var n = f.properties.precinct;
      if (state.coverage) return { color: '#155a96', weight: 1.2, opacity: 0.9, fillColor: coverageColor(activeCount(n)), fillOpacity: 0.75 };
      return { color: '#1e6fb8', weight: 1.2, opacity: 0.9, fillColor: '#1e6fb8', fillOpacity: 0.06 };
    }
    function precinctPopup(p) {
      var locs = locsInPrecinct(p.precinct);
      var html = '<div class="pmap-popup"><h4>Precinct ' + esc(p.precinct) + '</h4>' +
        '<div><span class="k">Polling place:</span> ' + esc(p.polling_place || '—') + '</div>' +
        '<div><span class="k">Address:</span> ' + esc(p.address || '') + (p.city ? ', ' + esc(p.city) : '') + '</div>' +
        '<div><span class="k">2020 population:</span> ' + fmt(p.pop2020) + ' &middot; <span class="k">voting age:</span> ' + fmt(p.vap2020) + '</div>' +
        '<div><span class="k">Commissioner district:</span> ' + esc(p.comm || '—') + '</div>';
      if (locs.length) {
        html += '<div style="margin-top:6px"><strong>Signing locations here</strong><ul>' + locs.map(function (f) {
          var q = f.properties;
          return '<li>' + esc(q.name) + (q.status ? ' <span class="status ' + esc(q.status) + '">' + esc(q.status) + '</span>' : '') +
            (q.next_event ? '<br><span class="k">' + esc(q.next_event) + '</span>' : '') + '</li>';
        }).join('') + '</ul></div>';
      } else if (state.locations) {
        html += '<div style="margin-top:6px" class="k">No signing location scheduled in this precinct yet.</div>';
      }
      return html + '</div>';
    }
    function locationPopup(q) {
      return '<div class="pmap-popup"><h4>' + esc(q.name) + '</h4>' +
        (q.status ? '<span class="status ' + esc(q.status) + '">' + esc(q.status) + '</span> ' : '') +
        '<div>' + esc(q.address || '') + (q.city ? ', ' + esc(q.city) : '') + (q.zip ? ' ' + esc(q.zip) : '') + '</div>' +
        (q.hours ? '<div><span class="k">Hours:</span> ' + esc(q.hours) + '</div>' : '') +
        (q.next_event ? '<div><span class="k">Next:</span> ' + esc(q.next_event) + '</div>' : '') +
        (q.precinct ? '<div><span class="k">Precinct:</span> ' + esc(q.precinct) + '</div>' : '') +
        (q.url ? '<div><a href="' + esc(q.url) + '">Details</a></div>' : '') + '</div>';
    }
    function pin(cls, size) {
      return L.divIcon({ className: '', html: '<div class="pmap-pin ' + cls + '"></div>', iconSize: [size || 14, size || 14], iconAnchor: [(size || 14) / 2, (size || 14) / 2] });
    }

    function cullLabels() {
      if (!state.labelMarkers) return;
      var z = map.getZoom();
      state.labelMarkers.forEach(function (o) {
        var el = o.marker.getElement(); if (!el) return;
        var sw = map.latLngToLayerPoint(o.bounds.getSouthWest()), ne = map.latLngToLayerPoint(o.bounds.getNorthEast());
        var small = Math.min(Math.abs(ne.x - sw.x), Math.abs(ne.y - sw.y)) < 30;
        el.classList.toggle('pmap-hidden', small && z < 13);
      });
    }

    function drawPrecincts(fc) {
      state.precincts = fc;
      if (state.precinctLayer) map.removeLayer(state.precinctLayer);
      state.labelLayer.clearLayers(); state.pollLayer.clearLayers();
      state.precinctLayer = L.geoJSON(fc, {
        style: precinctStyle,
        onEachFeature: function (f, layer) {
          layer.bindPopup(function () { return precinctPopup(f.properties); }, { maxWidth: 320 });
          layer.on('mouseover', function () { layer.setStyle({ weight: 2.5, fillOpacity: state.coverage ? 0.85 : 0.18 }); });
          layer.on('mouseout', function () { state.precinctLayer.resetStyle(layer); });
        }
      }).addTo(map);
      state.labelMarkers = [];
      fc.features.forEach(function (f) {
        var p = f.properties;
        if (p.label_lat != null && p.label_lon != null) {
          var mk = L.marker([p.label_lat, p.label_lon], { pane: 'labels', interactive: false,
            icon: L.divIcon({ className: 'pmap-label', html: esc(p.precinct), iconSize: null }) }).addTo(state.labelLayer);
          state.labelMarkers.push({ marker: mk, bounds: L.geoJSON(f).getBounds() });
        }
      });
      state.labelLayer.addTo(map);
      map.off('zoomend', cullLabels); map.on('zoomend', cullLabels); setTimeout(cullLabels, 0);
      if (opts.pollingPlaces) {
        fc.features.forEach(function (f) {
          var p = f.properties;
          if (p.label_lat != null && p.polling_place) {
            L.marker([p.label_lat, p.label_lon], { icon: pin('poll', 11), title: p.polling_place })
              .bindPopup('<div class="pmap-popup"><h4>' + esc(p.polling_place) + '</h4><div>' + esc(p.address || '') + (p.city ? ', ' + esc(p.city) : '') + '</div><div class="k">Polling place for precinct ' + esc(p.precinct) + '</div></div>')
              .addTo(state.pollLayer);
          }
        });
      }
      if (fitBounds) map.fitBounds(state.precinctLayer.getBounds(), { padding: [10, 10] });
      buildLegend();
    }

    function drawLocations(fc) {
      state.locations = fc;
      state.locLayer.clearLayers();
      (fc.features || []).forEach(function (f) {
        if (!f.geometry || f.geometry.type !== 'Point') return;
        var q = f.properties || {};
        if (q.precinct == null && state.precincts) {
          var hit = state.precincts.features.find(function (pf) { return pointInPolygon(f.geometry.coordinates, pf.geometry); });
          if (hit) q.precinct = hit.properties.precinct;
        }
        L.marker([f.geometry.coordinates[1], f.geometry.coordinates[0]], { icon: pin(q.status || 'planned'), title: q.name })
          .bindPopup(locationPopup(q), { maxWidth: 300 }).addTo(state.locLayer);
      });
      if (!map.hasLayer(state.locLayer)) state.locLayer.addTo(map);
      if (state.precinctLayer) state.precinctLayer.setStyle(precinctStyle);
    }

    function addOverlay(name, url, style, labelProp, labelCls) {
      return getJSON(url).then(function (fc) {
        var layer = L.geoJSON(fc, { style: style, interactive: !!labelProp, onEachFeature: function (f, l) {
          if (labelProp && f.properties && f.properties[labelProp]) {
            l.bindTooltip(String(f.properties[labelProp]), { permanent: false, direction: 'center', className: 'pmap-label ' + (labelCls || '') });
          }
        } });
        state.overlays[name] = layer;
        return layer;
      }).catch(function (e) { console.warn('map overlay failed', name, e); return null; });
    }

    function buildLegend() {
      if (state.legend) map.removeControl(state.legend);
      var legend = L.control({ position: 'bottomright' });
      legend.onAdd = function () {
        var d = L.DomUtil.create('div', 'pmap-legend');
        d.innerHTML = '<div><span class="sw" style="background:#1e7f4b"></span>Signing now (active)</div>' +
          '<div><span class="sw" style="background:#f2b705"></span>Planned location</div>' +
          '<div><span class="sw" style="background:#8a8580"></span>Closed</div>' +
          (opts.pollingPlaces ? '<div><span class="sw sq" style="background:#1e6fb8"></span>Polling place</div>' : '') +
          '<label><input type="checkbox" class="pmap-cov"' + (state.coverage ? ' checked' : '') + '> Coverage: <span class="grad"></span> active locations per precinct</label>';
        L.DomEvent.disableClickPropagation(d);
        d.querySelector('.pmap-cov').addEventListener('change', function (e) {
          state.coverage = e.target.checked;
          if (state.precinctLayer) state.precinctLayer.setStyle(precinctStyle);
        });
        return d;
      };
      legend.addTo(map); state.legend = legend;
    }

    function buildFinder() {
      var box = L.DomUtil.create('div', 'pmap-finder', el);
      box.innerHTML = '<form><input type="text" name="address" placeholder="Your address (street, city) — find your precinct" aria-label="Street address" autocomplete="street-address"><button type="submit">Find</button></form>' +
        '<p class="pmap-note">Your address is sent to the U.S. Census Bureau geocoder to find the precinct. It is not stored by this site.</p><div class="pmap-result" hidden></div>';
      L.DomEvent.disableClickPropagation(box); L.DomEvent.disableScrollPropagation(box);
      var form = box.querySelector('form'), input = box.querySelector('input'), btn = box.querySelector('button'), out = box.querySelector('.pmap-result');
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        var q = input.value.trim(); if (!q) return;
        btn.disabled = true; out.hidden = false; out.className = 'pmap-result'; out.textContent = 'Looking up…';
        getJSON(opts.finderUrl + encodeURIComponent(q)).then(function (r) {
          state.youLayer.clearLayers();
          if (r.error && !r.precinct) { out.className = 'pmap-result err'; out.textContent = r.error; return; }
          var p = r.precinct || {};
          var html = '<strong>Precinct ' + esc(p.precinct) + '</strong>' + (p.polling_place ? ' — polling place: ' + esc(p.polling_place) + (p.city ? ', ' + esc(p.city) : '') : '') +
            (r.matched_address ? '<br><span class="k">Matched: ' + esc(r.matched_address) + '</span>' : '');
          if (r.nearest && r.nearest.length) {
            html += '<br>Nearest signing locations:<ol>' + r.nearest.slice(0, 3).map(function (n) {
              return '<li>' + esc(n.name) + (n.status ? ' (' + esc(n.status) + ')' : '') + ' — ' + esc(n.distance_mi) + ' mi' + (n.hours ? ', ' + esc(n.hours) : '') + '</li>';
            }).join('') + '</ol>';
          }
          out.innerHTML = html;
          if (r.lat != null) {
            L.marker([r.lat, r.lon], { icon: pin('you', 18), title: 'Your address' }).addTo(state.youLayer);
            state.youLayer.addTo(map);
            map.setView([r.lat, r.lon], Math.max(map.getZoom(), 13));
          }
        }).catch(function () { out.className = 'pmap-result err'; out.textContent = 'Lookup failed. Please try again.'; })
          .finally(function () { btn.disabled = false; });
      });
    }

    var api = { map: map, state: state,
      refreshLocations: function () {
        if (!opts.locationsUrl) return Promise.resolve(null);
        return getJSON(opts.locationsUrl).then(function (fc) { drawLocations(fc); return fc; }).catch(function (e) { console.warn('locations failed', e); return null; });
      },
      setCoverage: function (on) { state.coverage = !!on; if (state.precinctLayer) state.precinctLayer.setStyle(precinctStyle); buildLegend(); }
    };

    var ready = getJSON(opts.precinctsUrl).then(function (fc) {
      drawPrecincts(fc);
      var overlays = { 'Precincts': state.precinctLayer, 'Precinct numbers': state.labelLayer };
      if (opts.locationsUrl) overlays['Signing locations'] = state.locLayer;
      if (opts.pollingPlaces) overlays['Polling places'] = state.pollLayer;
      var extra = [];
      if (opts.countyUrl) extra.push(addOverlay('County line', opts.countyUrl, { color: '#1c1a19', weight: 2.5, fill: false, dashArray: '6 4' }));
      if (opts.districtsUrl) extra.push(addOverlay('Commissioner districts', opts.districtsUrl, { color: '#2b5f9e', weight: 2.5, fill: false }, 'DISTRICT'));
      if (opts.municipalitiesUrl) extra.push(addOverlay('Municipalities', opts.municipalitiesUrl, { color: '#4a4a4a', weight: 1, fillColor: '#ffd35c', fillOpacity: 0.18 }, 'NAME', 'pmap-label-sm'));
      return Promise.all(extra).then(function () {
        if (state.overlays['County line']) { overlays['County line'] = state.overlays['County line']; state.overlays['County line'].addTo(map); }
        if (state.overlays['Commissioner districts']) overlays['Commissioner districts'] = state.overlays['Commissioner districts'];
        if (state.overlays['Municipalities']) overlays['Municipalities'] = state.overlays['Municipalities'];
        L.control.layers(null, overlays, { collapsed: true, position: 'topright' }).addTo(map);
        if (opts.finderUrl) buildFinder();
        return api.refreshLocations();
      });
    }).catch(function (e) { console.error('petition map failed', e); mapEl.insertAdjacentHTML('afterbegin', '<p style="padding:1em">Map data could not be loaded.</p>'); });

    api.ready = ready;
    var focusMarker = null;
    api.focus = function (lat, lon, precinct) {
      if (focusMarker) { map.removeLayer(focusMarker); }
      focusMarker = L.circleMarker([lat, lon], { radius: 9, color: '#1F2A44', weight: 3, fillColor: '#F2B705', fillOpacity: 1 }).addTo(map);
      focusMarker.bindPopup('<strong>Your address</strong>' + (precinct ? '<br>Precinct ' + esc(String(precinct)) : '')).openPopup();
      map.setView([lat, lon], Math.max(map.getZoom(), 13));
      return focusMarker;
    };
    return api;
  }

  window.initPetitionMap = initPetitionMap;
})();
