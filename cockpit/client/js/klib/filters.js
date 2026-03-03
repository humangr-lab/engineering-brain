/* ═══════════════ KLIB FILTERS — Left panel: SOTA faceted search ═══════════════
   Algolia-inspired: instant feedback, active filter chips, preserved state.
   Search debounced. Slider cross-browser. All tags shown (scrollable).        */

import { state } from '../state.js';
import { LAYERS, SEVERITY_ORDER, SEVERITY_COLORS } from '../schema.js';

let _debounceTimer = null;

/**
 * Build the filter panel from node data.
 * Preserves current filter state across rebuilds.
 */
export function buildFilters(nodes) {
  const container = document.getElementById('klibFilters');
  if (!container) return;

  // Count by layer, severity, tags
  const layerCounts = {};
  const sevCounts = {};
  const tagCounts = {};

  for (const n of nodes) {
    layerCounts[n.layer] = (layerCounts[n.layer] || 0) + 1;

    const sev = (n.severity || 'info').toUpperCase();
    sevCounts[sev] = (sevCounts[sev] || 0) + 1;

    for (const t of (n.technologies || [])) {
      tagCounts[t] = (tagCounts[t] || 0) + 1;
    }
    for (const d of (n.domains || [])) {
      tagCounts[d] = (tagCounts[d] || 0) + 1;
    }
  }

  const f = state.klibFilters;
  let html = '';

  /* ── Active Filter Chips ── */
  const activeChips = _buildActiveChips(f);
  if (activeChips) {
    html += `<div class="klib-filter-section klib-active-chips">
      <div class="klib-filter-label">Active Filters</div>
      <div class="klib-chip-row">${activeChips}</div>
      <div class="klib-clear-all" id="klibClearAll">Clear all</div>
    </div>`;
  }

  /* ── Search ── */
  html += `<div class="klib-filter-section">
    <div class="klib-filter-label">Search</div>
    <div class="klib-search-wrap">
      <input class="klib-search-input" id="klibSearchInput"
             placeholder="Filter nodes..." value="${_esc(f.search || '')}"
             autocomplete="off" spellcheck="false">
    </div>
  </div>`;

  /* ── Cortical Layers ── */
  html += '<div class="klib-filter-section"><div class="klib-filter-label">Cortical Layers</div><div class="klib-layer-list">';
  LAYERS.forEach(l => {
    const count = layerCounts[l.id] || 0;
    const active = !f.layers.length || f.layers.includes(l.id);
    html += `<div class="klib-layer-item${active ? ' active' : ''}" data-layer="${l.id}">
      <div class="klib-layer-dot" style="background:${l.color}"></div>
      <div class="klib-layer-name">${l.name}</div>
      <div class="klib-layer-cnt">${count.toLocaleString()}</div>
    </div>`;
  });
  html += '</div></div>';

  /* ── Severity ── */
  html += '<div class="klib-filter-section"><div class="klib-filter-label">Severity</div><div class="klib-sev-row">';
  SEVERITY_ORDER.forEach(s => {
    const count = sevCounts[s] || 0;
    const active = !f.severities.length || f.severities.includes(s);
    html += `<div class="klib-sev-chip ${s}${active ? ' active' : ''}" data-sev="${s}">
      <span class="klib-sev-name">${s}</span>
      <span class="klib-sev-count">${count.toLocaleString()}</span>
    </div>`;
  });
  html += '</div></div>';

  /* ── Confidence Slider ── */
  const confPct = Math.round((f.confidence || 0) * 100);
  html += `<div class="klib-filter-section">
    <div class="klib-filter-label">Min Confidence</div>
    <div class="klib-conf-row">
      <input type="range" class="klib-conf-slider" id="klibConfSlider"
             min="0" max="100" value="${confPct}" step="5">
      <div class="klib-conf-val" id="klibConfVal">${confPct}%</div>
    </div>
  </div>`;

  /* ── Tags (all, sorted by count, scrollable) ── */
  const sortedTags = Object.entries(tagCounts).sort((a, b) => b[1] - a[1]);
  html += `<div class="klib-filter-section">
    <div class="klib-filter-label">Tags <span class="klib-filter-count">${sortedTags.length}</span></div>
    <div class="klib-tag-cloud">`;
  sortedTags.forEach(([t, count]) => {
    const active = f.tags && f.tags.includes(t);
    html += `<div class="klib-tag${active ? ' active' : ''}" data-tag="${_esc(t)}" title="${_esc(t)} (${count})">${_esc(t)}<span class="klib-tag-n">${count}</span></div>`;
  });
  html += '</div></div>';

  container.innerHTML = html;
  _wireFilters(container);
}

/* ── Active Filter Chips ─────────────────────────────── */

function _buildActiveChips(f) {
  const chips = [];

  if (f.layers?.length) {
    f.layers.forEach(l => {
      const layer = LAYERS.find(x => x.id === l);
      if (layer) chips.push(`<div class="klib-chip" data-action="remove-layer" data-val="${l}"><span class="klib-chip-dot" style="background:${layer.color}"></span>${layer.shortName}<span class="klib-chip-x">\u00d7</span></div>`);
    });
  }

  if (f.severities?.length) {
    f.severities.forEach(s => {
      chips.push(`<div class="klib-chip" data-action="remove-sev" data-val="${s}"><span class="klib-chip-dot" style="background:${SEVERITY_COLORS[s]}"></span>${s}<span class="klib-chip-x">\u00d7</span></div>`);
    });
  }

  if (f.confidence > 0) {
    chips.push(`<div class="klib-chip" data-action="remove-conf">\u2265${Math.round(f.confidence * 100)}%<span class="klib-chip-x">\u00d7</span></div>`);
  }

  if (f.tags?.length) {
    f.tags.forEach(t => {
      chips.push(`<div class="klib-chip" data-action="remove-tag" data-val="${_esc(t)}">${_esc(t)}<span class="klib-chip-x">\u00d7</span></div>`);
    });
  }

  if (f.search) {
    chips.push(`<div class="klib-chip" data-action="remove-search">"${_esc(f.search.slice(0, 20))}"<span class="klib-chip-x">\u00d7</span></div>`);
  }

  return chips.length ? chips.join('') : '';
}

/* ── Wire Events ─────────────────────────────────────── */

function _wireFilters(container) {
  // Search with debounce
  const searchInput = container.querySelector('#klibSearchInput');
  if (searchInput) {
    searchInput.addEventListener('input', () => {
      if (_debounceTimer) clearTimeout(_debounceTimer);
      _debounceTimer = setTimeout(() => {
        state.klibFilters = { ...state.klibFilters, search: searchInput.value };
      }, 150);
    });
    // Auto-focus
    setTimeout(() => searchInput.focus(), 100);
  }

  // Layer toggles
  container.querySelectorAll('.klib-layer-item').forEach(el => {
    el.addEventListener('click', () => {
      const layer = parseInt(el.dataset.layer, 10);
      const current = [...(state.klibFilters.layers || [])];
      const idx = current.indexOf(layer);
      if (idx >= 0) current.splice(idx, 1);
      else current.push(layer);
      el.classList.toggle('active');
      state.klibFilters = { ...state.klibFilters, layers: current };
    });
  });

  // Severity chips
  container.querySelectorAll('.klib-sev-chip').forEach(el => {
    el.addEventListener('click', () => {
      const sev = el.dataset.sev;
      const current = [...(state.klibFilters.severities || [])];
      const idx = current.indexOf(sev);
      if (idx >= 0) current.splice(idx, 1);
      else current.push(sev);
      el.classList.toggle('active');
      state.klibFilters = { ...state.klibFilters, severities: current };
    });
  });

  // Confidence slider (cross-browser)
  const slider = container.querySelector('#klibConfSlider');
  const confVal = container.querySelector('#klibConfVal');
  if (slider) {
    const onSlide = () => {
      const val = parseInt(slider.value, 10) / 100;
      if (confVal) confVal.textContent = `${Math.round(val * 100)}%`;
      state.klibFilters = { ...state.klibFilters, confidence: val };
    };
    slider.addEventListener('input', onSlide);
    slider.addEventListener('change', onSlide); // Firefox fallback
  }

  // Tags
  container.querySelectorAll('.klib-tag').forEach(el => {
    el.addEventListener('click', () => {
      const tag = el.dataset.tag;
      const current = [...(state.klibFilters.tags || [])];
      const idx = current.indexOf(tag);
      if (idx >= 0) current.splice(idx, 1);
      else current.push(tag);
      el.classList.toggle('active');
      state.klibFilters = { ...state.klibFilters, tags: current };
    });
  });

  // Clear all
  const clearBtn = container.querySelector('#klibClearAll');
  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      state.klibFilters = { layers: [], severities: [], tags: [], confidence: 0, search: '' };
      // Rebuild to reset visual state
      buildFilters(state.nodes);
    });
  }

  // Active filter chip removal
  container.querySelectorAll('.klib-chip').forEach(el => {
    el.addEventListener('click', () => {
      const action = el.dataset.action;
      const val = el.dataset.val;
      const f = { ...state.klibFilters };

      switch (action) {
        case 'remove-layer':
          f.layers = (f.layers || []).filter(l => l !== parseInt(val, 10));
          break;
        case 'remove-sev':
          f.severities = (f.severities || []).filter(s => s !== val);
          break;
        case 'remove-conf':
          f.confidence = 0;
          break;
        case 'remove-tag':
          f.tags = (f.tags || []).filter(t => t !== val);
          break;
        case 'remove-search':
          f.search = '';
          break;
      }
      state.klibFilters = f;
      // Rebuild to update chip display
      buildFilters(state.nodes);
    });
  });
}

function _esc(s) {
  if (!s) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
