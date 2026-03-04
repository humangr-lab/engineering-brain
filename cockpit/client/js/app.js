/* ═══════════════ APP — Entry point: boot, build scene, wire everything ═══════════════ */

import { CONFIG, FEATURES } from './config.js';
import { state, subscribe, batch } from './state.js';
import { connectAPI, disconnect } from './api.js';
import { initTheme, isDark } from './theme.js';
import { initSearch } from './search.js';
import { initEngine, scene, onTick, startLoop, setThemeColors, getPerformanceMetrics, adjustBloomForNodeCount } from './scene/engine.js';
import { setPalette, matFactory, setCC, setGroupNeon } from './scene/materials.js';
import { mkObj } from './scene/shapes.js';
import { createGround, createZones } from './scene/platforms.js';
import { connections, buildConnections, toggleConnectionType } from './scene/connections.js';
import { createPillLabel, createSubLabel, createAutoPill } from './scene/labels.js';
import { defaultLayout, pipelineLayout, funnelLayout, transitionLayout, animateCamera, CAMERA_PRESETS, computeLayout } from './scene/layout.js';
import { initInteraction, setClickables } from './scene/interaction.js';
import { registerIcons, tick as animTick } from './scene/animation.js';
import { setMainGroup, enterSubmap, exitSubmap } from './scene/submaps.js';
import { initKlib, openKlib } from './klib/klib.js';
import { initDetailPanel, openPanel, closePanel } from './panels/detail-panel.js';
import { initStatsBar, animateCounters } from './panels/stats-bar.js';
import { initTour } from './tour.js';
import { SYSMAP } from './data/sysmap.js';
import { loadCockpit } from './loader.js';
import { setGroupColorsFromPalette } from './schema.js';
import { initView2d, show2d, hide2d, is2dActive } from './view2d/view2d.js';
// ═══ WP-PERF: Instanced Rendering ═══
import { createInstancedScene, disposeInstancedScene, batchUpdatePositions } from './scene/instanced-renderer.js';
// ═══ WP-3: Navigation ═══
import { initBreadcrumb } from './ui/breadcrumb.js';
import { initRouter, getShareUrl } from './ui/router.js';
import { initSearchOverlay, openSearchOverlay, closeSearchOverlay } from './ui/search-overlay.js';
// ═══ WP-A11Y: Accessibility ═══
import { initKeyboardNav } from './a11y/keyboard-nav.js';
import { initAriaManager } from './a11y/aria-manager.js';
import { createFocusTrap, activateTrap, deactivateTrap } from './a11y/focus-trap.js';
// ═══ WP-4: Fractal Drill ═══
import { initZoomManager, tickZoomManager, drillInto, drillOut, jumpTo, edit, closeEditor, getCurrentLevel, onZoomEvent, LEVELS } from './drill/zoom-manager.js';
import { initLODManager } from './drill/lod-manager.js';
import { getCache } from './drill/data-cache.js';
// ═══ WP-6: Conversation Mode ═══
import { initChatPanel } from './agent/chat-panel.js';
import * as T from 'three';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

async function boot() {
  // 1. Try schema-driven loader first, fall back to SYSMAP
  let cockpitData = null;

  if (CONFIG.GRAPH_DATA_URL) {
    try {
      cockpitData = await loadCockpit(CONFIG.GRAPH_DATA_URL, {
        schemaUrl: CONFIG.COCKPIT_SCHEMA_URL || undefined,
        theme: isDark() ? 'dark' : 'light',
        log: CONFIG.ENABLE_INFERENCE_LOG,
      });
      console.log('[Boot] Loaded via schema-driven loader:', cockpitData.title);
    } catch (e) {
      console.warn('[Boot] Schema-driven loader failed, falling back to sysmap.js:', e.message);
    }
  }

  if (cockpitData) {
    // Store inference results in state
    batch({
      sysNodes: cockpitData.N,
      sysEdges: cockpitData.E,
      sysDetails: cockpitData.DT,
      submaps: cockpitData.SUBMAPS,
      nodeDetails: cockpitData.ND,
      docTree: cockpitData.DOC_TREE,
      klibData: cockpitData.KLIB || {},
      graphData: cockpitData.graphData,
      cockpitSchema: cockpitData.cockpitSchema,
      inferredConfig: cockpitData.inferredConfig,
    });

    // Update header from loaded data
    _updateHeader(cockpitData.title, cockpitData.description);

    // Update stats bar from loaded data
    _updateStatsBar(cockpitData.stats);

    // Update legend from loaded data
    _updateLegend(cockpitData.legend);

    // Register group colors from inference palette
    if (cockpitData.inferredConfig?.palette) {
      setGroupColorsFromPalette(cockpitData.inferredConfig.palette);
      for (const [group, color] of cockpitData.inferredConfig.palette) {
        setGroupNeon(group, color.int);
      }
    }
  } else {
    // Fallback to SYSMAP
    batch({
      sysNodes: SYSMAP.N,
      sysEdges: SYSMAP.E,
      sysDetails: SYSMAP.DT,
      submaps: SYSMAP.SUBMAPS,
      nodeDetails: SYSMAP.ND,
      docTree: SYSMAP.DOC_TREE,
      klibData: SYSMAP.KLIB || {},
    });
  }

  // 2. Connect to API for live knowledge graph data
  try {
    await connectAPI();
  } catch (e) {
    console.warn('API connection failed, running with static data only:', e.message);
  }

  // 3. Initialize Three.js engine (must happen before theme callback accesses scene)
  const container = document.getElementById('sc');
  if (!container) { console.error('No #sc container found'); return; }
  initEngine(container);

  // 4. Initialize theme (after engine, so setThemeColors can access scene)
  initTheme((theme) => {
    setThemeColors(theme === 'dark');
    setCC(theme === 'dark');
  });

  // 5. Build the 3D scene
  const icons = _buildScene();

  // 6. Start render loop
  onTick(animTick);
  startLoop();

  // ═══ WP-4: Fractal Drill ═══
  try {
    initZoomManager();
    initLODManager();
    onTick(tickZoomManager);
    _wireDrillSystem();
  } catch (e) { console.warn('[Boot] WP-4 Fractal Drill init failed:', e.message); }
  // ═══ End WP-4 ═══

  // 7. Initialize UI systems
  initDetailPanel(_openModal);
  initStatsBar();
  if (FEATURES.SEARCH) try { initSearch(_onSearchNavigate); } catch (e) { console.warn('[Boot] Search init failed:', e.message); }
  if (FEATURES.KLIB) try { initKlib(); } catch (e) { console.warn('[Boot] KLib init failed:', e.message); }
  if (FEATURES.TOUR) try { initTour(icons, _openModal); } catch (e) { console.warn('[Boot] Tour init failed:', e.message); }

  // ═══ WP-3: Navigation ═══
  try {
    initBreadcrumb((level, seg) => {
      // ═══ WP-4: Fractal Drill — breadcrumb navigation ═══
      const currentDrillLevel = getCurrentLevel();
      if (currentDrillLevel > LEVELS.SYSTEM) {
        // Use drill FSM to navigate back to the clicked breadcrumb level
        jumpTo(level, seg?.id);
        return;
      }
      // Fallback: legacy submap navigation
      if (level === 0 && state.inSubmap) {
        exitSubmap();
      }
    });
    initRouter();
    initSearchOverlay(_onSearchNavigate);
    _wireCmdK();
  } catch (e) { console.warn('[Boot] WP-3 Navigation init failed:', e.message); }

  // 8. Wire layout buttons
  _wireLayoutButtons(icons);

  // 9. Wire back button
  const backBtn = document.getElementById('backBtn');
  if (backBtn) backBtn.addEventListener('click', () => exitSubmap());

  // 9b. Initialize 2D view toggle (camera mode, no separate renderer)
  try { initView2d(); } catch (e) { console.warn('[Boot] 2D view init failed:', e.message); }
  _wireViewToggle();

  // 10. Wire doc map
  if (FEATURES.DOC_MAP) _wireDocMap();

  // 11. Wire modal
  _wireModal();

  // 12. Wire legend toggle (click to show/hide connection types)
  _wireLegend();

  // 13. Animate stats bar counters
  setTimeout(animateCounters, 500);

  // ═══ WP-A11Y: Accessibility ═══
  try {
    initAriaManager();
    initKeyboardNav({ openModal: _openModal });
    _initFocusTraps();
  } catch (e) { console.warn('[Boot] A11Y init failed:', e.message); }

  // ═══ WP-6: Conversation Mode ═══
  try { initChatPanel(); } catch (e) { console.warn('[Boot] Chat panel init failed:', e.message); }
}

/**
 * WP-A11Y: Set up focus traps for all overlay/modal containers.
 */
function _initFocusTraps() {
  // Detail panel
  const dp = document.getElementById('dp');
  if (dp) createFocusTrap(dp);

  // Search overlay (WP-3)
  const searchOv = document.getElementById('wp3SearchOv');
  if (searchOv) createFocusTrap(searchOv);

  // Modal overlay
  const modalOv = document.getElementById('modalOv');
  if (modalOv) createFocusTrap(modalOv);

  // Knowledge Library overlay
  const klibOv = document.getElementById('klibOv');
  if (klibOv) createFocusTrap(klibOv);

  // Documentation overlay
  const docOv = document.getElementById('docOv');
  if (docOv) createFocusTrap(docOv);

  // Wire focus trap activation/deactivation to overlay open/close
  subscribe('searchOverlayOpen', (open) => {
    if (open) activateTrap('wp3SearchOv');
    else deactivateTrap('wp3SearchOv');
  });

  subscribe('klibOpen', (open) => {
    if (open) activateTrap('klibOv');
    else deactivateTrap('klibOv');
  });

  subscribe('docOverlayOpen', (open) => {
    if (open) activateTrap('docOv');
    else deactivateTrap('docOv');
  });

  // Modal and detail panel: observe class changes for open/close
  _observeClassToggle('modalOv', 'open', (isOpen) => {
    if (isOpen) activateTrap('modalOv');
    else deactivateTrap('modalOv');
  });

  _observeClassToggle('dp', 'open', (isOpen) => {
    if (isOpen) activateTrap('dp');
    else deactivateTrap('dp');
  });
}

/**
 * WP-A11Y: Observe a class toggle on an element and fire callback.
 */
function _observeClassToggle(elementId, className, callback) {
  const el = document.getElementById(elementId);
  if (!el) return;

  const observer = new MutationObserver(() => {
    callback(el.classList.contains(className));
  });
  observer.observe(el, { attributes: true, attributeFilter: ['class'] });
}

function _buildScene() {
  const nodes = state.sysNodes;
  const edges = state.sysEdges;
  const visibleNodes = nodes.filter(n => !n.hidden);

  // Ground + zones — added to scene directly (stay visible in submaps)
  createGround(scene);
  createZones(scene);

  // ═══ WP-PERF: Instanced Rendering ═══════════════════════════════════
  // If node count exceeds threshold, use InstancedMesh for background nodes.
  // Small scenes (<=INSTANCED_THRESHOLD) use the original per-Group path
  // for full fidelity with labels, interaction proxies, etc.
  const useInstanced = visibleNodes.length > CONFIG.INSTANCED_THRESHOLD;

  if (useInstanced) {
    console.log(`[WP-PERF] Instanced mode: ${visibleNodes.length} nodes > threshold ${CONFIG.INSTANCED_THRESHOLD}`);

    // Adjust bloom for large scenes
    adjustBloomForNodeCount(visibleNodes.length);

    // Create instanced scene for ALL nodes
    const instancedScene = createInstancedScene(nodes, edges, scene);

    // Store reference for potential cleanup
    state._instancedScene = instancedScene;

    // Start Web Worker for force layout if available
    _startForceWorker(nodes, edges, instancedScene);

    // Return empty icons array (instanced mode has no per-node Groups)
    return [];
  }
  // ═══ End WP-PERF ════════════════════════════════════════════════════

  // mainGroup holds all node objects — hidden when entering submaps
  const mainGroup = new T.Group();
  scene.add(mainGroup);

  // Build icons
  const icons = [];
  const clickables = [];
  const posMap = new Map();

  nodes.forEach((n) => {
    // Skip hidden nodes
    if (n.hidden) return;

    const g = new T.Group();

    // Use inferred size for node scale, with hero override
    const inferredSize = n._inferredSize || 1.0;
    const s = n.hero ? 4.5 : Math.max(1.5, inferredSize * 1.8 + 0.4);

    // Set palette for this shape
    setPalette(n.sh, n.g);

    const obj = mkObj(n.sh, s, matFactory);
    obj.position.y = s * 0.38;
    g.add(obj);

    const proxy = new T.Mesh(
      new T.BoxGeometry(s * 1, s * 0.9, s * 0.8),
      new T.MeshBasicMaterial({ visible: false }),
    );
    proxy.position.y = s * 0.38;
    proxy.userData = { id: n.id };
    g.add(proxy);
    clickables.push({ mesh: proxy, id: n.id, data: n });

    // Ground pad
    const padR = s * 0.5;
    const pad = new T.Mesh(
      new T.CylinderGeometry(padR, padR, s * 0.02, 16),
      new T.MeshStandardMaterial({ color: 0xc8ccd4, metalness: 0.1, roughness: 0.8, transparent: true, opacity: 0.35 }),
    );
    pad.position.y = 0.01;
    g.add(pad);

    // Pad ring
    const ring = new T.Mesh(
      new T.RingGeometry(padR - 0.01, padR, 16),
      new T.MeshBasicMaterial({ color: 0xa0a4b0, transparent: true, opacity: 0.3, side: T.DoubleSide }),
    );
    ring.rotation.x = -Math.PI / 2;
    ring.position.y = 0.02;
    g.add(ring);

    // Contact shadow
    const cShadow = new T.Mesh(
      new T.CircleGeometry(s * 0.45, 12),
      new T.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.12, depthWrite: false }),
    );
    cShadow.rotation.x = -Math.PI / 2;
    cShadow.position.y = 0.005;
    g.add(cShadow);

    // Auto indicator
    if (n.auto) {
      const ant = new T.Mesh(
        new T.CylinderGeometry(0.018, 0.018, 0.4, 6),
        new T.MeshBasicMaterial({ color: 0x34d399 }),
      );
      ant.position.y = s * 0.82;
      g.add(ant);
      const dot = new T.Mesh(
        new T.SphereGeometry(0.06, 8, 8),
        new T.MeshBasicMaterial({ color: 0x34d399 }),
      );
      dot.position.y = s * 1.05;
      g.add(dot);
    }

    // Labels (CSS2D)
    const labelDiv = document.createElement('div');
    labelDiv.className = 'pill-label ' + n.g + (n.hero ? ' hero' : '');
    labelDiv.textContent = n.label;
    const labelObj = new CSS2DObject(labelDiv);
    labelObj.position.set(0, s * 0.38 + (n.hero ? 1.2 : 0.85), 0);
    g.add(labelObj);

    if (n.auto) {
      const autoDiv = document.createElement('div');
      autoDiv.className = 'auto-pill';
      autoDiv.textContent = '\u26A1 Auto';
      const autoObj = new CSS2DObject(autoDiv);
      autoObj.position.set(0, s * 0.38 + (n.hero ? 1.0 : 0.65), 0);
      g.add(autoObj);
    }

    const subDiv = document.createElement('div');
    subDiv.className = 'sub-3d';
    subDiv.textContent = n.sub;
    const subObj = new CSS2DObject(subDiv);
    subObj.position.set(0, -0.2, 0);
    g.add(subObj);

    // Position — use inferred size for yBase, with legacy fallback
    const yBase = {
      erg: 0.25, scorer: 0.16, taxon: 0.16, router: 0.16, embed: 0.16, packv2: 0.16,
      l0: 0.12, l1: 0.12, l2: 0.12, l3: 0.12, l4: 0.12, l5: 0.12,
      cryst: 0.18, promot: 0.18, xlay: 0.18, linkp: 0.18, adapt: 0.18, trust: 0.18,
      eladder: 0.18, bedge: 0.18, pdecay: 0.18, ctensor: 0.18, dstcomb: 0.18,
      seeds: 0.14, mining: 0.14, ontol: 0.14, obslog: 0.14,
      llm: 0.14, mcp: 0.14, cicd: 0.14, ide: 0.14, klib: 0.18,
    };
    const baseY = n._inferredSize != null && !(n.id in yBase)
      ? n._inferredSize * 0.5 + 0.5
      : (yBase[n.id] || 0.15) * 7;
    g.position.set(n.x, baseY, n.z);
    mainGroup.add(g);

    posMap.set(n.id, { x: n.x, y: baseY, z: n.z });

    icons.push({
      id: n.id,
      mesh: g,
      data: n,
      baseScale: 1,
      phase: Math.random() * Math.PI * 2,
    });
  });

  // Build connections
  buildConnections(mainGroup, edges, posMap);

  // Register for animation
  registerIcons(icons);

  // Set up interaction
  initInteraction(clickables, _onNodeClick, _onNodeHover);

  // Store main group reference for submap system
  setMainGroup(mainGroup, icons.map(i => ({
    mesh: i.mesh,
    id: i.id,
    data: i.data,
  })));

  return icons;
}

// ═══ WP-PERF: Force Layout Worker ═══════════════════════════════════
let _forceWorker = null;

/**
 * Start a Web Worker for off-thread force layout computation.
 * Only used in instanced mode for large graphs.
 */
function _startForceWorker(nodes, edges, instancedScene) {
  try {
    _forceWorker = new Worker('./js/workers/force-layout.js');

    const nodeOrder = nodes.filter(n => !n.hidden).map(n => n.id);

    _forceWorker.onmessage = (e) => {
      const msg = e.data;
      if (msg.type === 'positions') {
        batchUpdatePositions(instancedScene, nodeOrder, msg.data);
      } else if (msg.type === 'converged') {
        console.log('[WP-PERF] Force layout converged, alpha:', msg.alpha);
      } else if (msg.type === 'ready') {
        console.log('[WP-PERF] Force worker ready, starting ticks');
        // Tick the worker on each animation frame
        onTick(() => {
          if (_forceWorker) {
            _forceWorker.postMessage({ type: 'tick' });
          }
        });
      } else if (msg.type === 'error') {
        console.warn('[WP-PERF] Force worker error:', msg.message);
      }
    };

    _forceWorker.onerror = (err) => {
      console.warn('[WP-PERF] Force worker failed:', err.message);
      _forceWorker = null;
    };

    _forceWorker.postMessage({
      type: 'init',
      nodes: nodes.filter(n => !n.hidden),
      edges,
      config: {
        alpha: 0.3,
        alphaDecay: 0.015,
        velocityDecay: 0.4,
        chargeStrength: -80,
        linkDistance: 12,
        ticksPerMessage: 3,
      },
    });
  } catch (err) {
    console.warn('[WP-PERF] Worker creation failed:', err);
    _forceWorker = null;
  }
}
// ═══ End WP-PERF ═════════════════════════════════════════════════════

function _onNodeClick(item) {
  if (!item) {
    closePanel();
    return;
  }
  const id = item.id;
  if (id === 'klib') {
    openKlib();
  } else if (state.submaps[id]) {
    enterSubmap(id, state.submaps, state.nodeDetails, _openModal);
  } else if (state.inSubmap && item.data?._parentId) {
    _openModal(id, item.data._parentId);
  } else if (getCurrentLevel() > LEVELS.SYSTEM && item.data?.nodeData) {
    // ═══ WP-4: Drill deeper from within a drill level ═══
    drillInto(id, item.data.nodeData || item.data);
  } else {
    openPanel(id);
  }
}

function _onNodeHover(item, event) {
  const tip = document.getElementById('hoverTip');
  const htTitle = document.getElementById('htTitle');
  const htSub = document.getElementById('htSub');
  if (!tip || !htTitle || !htSub) return;

  if (item) {
    const n = state.sysNodes.find(v => v.id === item.id);
    htTitle.textContent = n?.label || item.id;
    htSub.textContent = n?.sub || '';
    tip.style.left = (event.clientX + 16) + 'px';
    tip.style.top = (event.clientY + 16) + 'px';
    tip.classList.add('show');
  } else {
    tip.classList.remove('show');
  }
}

function _wireLayoutButtons(icons) {
  const btns = document.getElementById('layoutBtns');
  if (!btns) return;

  btns.addEventListener('click', (e) => {
    const btn = e.target.closest('.layout-btn');
    if (!btn) return;

    const layout = btn.dataset.layout;
    btns.querySelectorAll('.layout-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.layout = layout;

    // Use computeLayout dispatcher for all layouts
    const nodes = state.sysNodes;
    const edges = state.sysEdges;
    const positions = computeLayout(layout, nodes, edges);

    // Transition icons
    transitionLayout(icons, positions);

    // Animate camera
    const preset = CAMERA_PRESETS[layout] || CAMERA_PRESETS.default;
    animateCamera(preset.pos, preset.lookAt, 1200);
  });
}

function _wireDocMap() {
  const docOv = document.getElementById('docOv');
  const docGrid = document.getElementById('docGrid');
  const docViewer = document.getElementById('docViewer');
  const docViewerC = document.getElementById('docViewerC');

  document.getElementById('docMapBtn')?.addEventListener('click', () => {
    if (!docGrid) return;
    state.docOverlayOpen = true;
    docGrid.innerHTML = state.docTree.map((cat, ci) => {
      let h = `<div class="doc-cat" data-ci="${ci}"><div class="doc-cat-name">${cat.cat}</div>`;
      h += `<div class="doc-cat-count">${cat.files.length} files \u00b7 ${cat.desc}</div>`;
      h += '<div class="doc-cat-files">';
      cat.files.forEach(f => { h += `<div class="doc-file" data-ci="${ci}" data-f="${f}">${f}</div>`; });
      h += '</div></div>';
      return h;
    }).join('');
    docOv?.classList.add('open');
  });

  document.getElementById('docOvX')?.addEventListener('click', () => {
    state.docOverlayOpen = false;
    docOv?.classList.remove('open');
    docViewer?.classList.remove('open');
  });

  document.getElementById('docViewerX')?.addEventListener('click', () => {
    docViewer?.classList.remove('open');
  });

  docGrid?.addEventListener('click', (e) => {
    const file = e.target.closest('.doc-file');
    if (file) {
      const ci = +file.dataset.ci;
      const f = file.dataset.f;
      const catData = state.docTree[ci];
      if (docViewerC) {
        docViewerC.innerHTML = `
          <div class="doc-viewer-cat">${catData.cat}</div>
          <div class="doc-viewer-title">${f.replace('.md', '').replace(/-/g, ' ')}</div>
          <div class="doc-viewer-path">docs/${catData.cat.toLowerCase().replace(/ & /g, '-').replace(/ /g, '-')}/${f}</div>
          <div class="doc-viewer-desc">${catData.desc}<br><br>This document is part of the <strong>${catData.cat}</strong> category which contains ${catData.files.length} files covering ${catData.desc.toLowerCase()}.</div>
        `;
      }
      docViewer?.classList.add('open');
      e.stopPropagation();
      return;
    }
    const cat = e.target.closest('.doc-cat');
    if (cat) cat.classList.toggle('expanded');
  });
}

function _openModal(nodeId, parentId) {
  const nd = state.nodeDetails[nodeId];
  if (!nd) return;
  const sm = state.submaps[parentId];
  if (!sm) return;
  const color = sm.color || 'module';

  const accentColor = color === 'source' ? 'var(--green)' : color === 'layer' ? 'var(--blue)' : color === 'consumer' ? 'var(--cyan)' : 'var(--purple)';
  const arrowColor = color === 'source' ? '#34d399' : color === 'layer' ? '#6b8fff' : color === 'consumer' ? '#5eead4' : '#9b7cff';

  let h = '<div class="modal-head">';
  h += `<div class="modal-tp ${color}">${sm.title}</div>`;
  h += `<div class="modal-tt">${nd.t}</div>`;
  h += `<div class="modal-dd">${nd.d}</div>`;
  h += '</div><div class="modal-body">';

  // Flow steps
  if (nd.s && nd.s.length) {
    h += `<div class="md-section" data-color="${color}"><span class="md-section-label">PROCESSING PIPELINE</span></div>`;
    h += '<div class="md-flow">';
    nd.s.forEach((st, i) => {
      if (i > 0) {
        h += `<div class="md-arr"><svg viewBox="0 0 28 14"><path d="M2 7h20M18 3l4 4-4 4" stroke="${arrowColor}" fill="none" stroke-width="1.5"/></svg><div class="md-arr-pulse" style="background:${arrowColor};color:${arrowColor}"></div></div>`;
      }
      h += `<div class="md-step ${st[1]}" style="animation-delay:${0.08 * i}s">`;
      h += '<div class="md-step-box">';
      h += `<div class="md-step-num">${String(i + 1).padStart(2, '0')}</div>`;
      h += `<div class="md-step-tag">${st[1]}</div>`;
      h += `<div class="md-step-l">${st[0]}</div>`;
      h += `<div class="md-step-d">${st[2]}</div>`;
      h += '</div></div>';
    });
    h += '</div>';
  }

  // Formula
  if (nd.f) {
    h += `<div class="md-section" data-color="${color}"><span class="md-section-label">FORMULA</span></div>`;
    h += `<div class="md-formula">${nd.f.replace(/([A-Za-z_]+)\s*=/, '<span class="hl">$1</span> =').replace(/([=+\u00d7\u03a3\u2211\u00b7\u2264\u2265<>])/g, '<span class="op">$1</span>')}</div>`;
  }

  // IO section
  if (nd.io) {
    h += `<div class="md-section" data-color="${color}"><span class="md-section-label">DATA FLOW</span></div>`;
    h += '<div class="md-io">';
    if (nd.io.i && nd.io.i.length) {
      h += '<div class="md-io-col in"><div class="md-io-h in">INPUTS</div>';
      nd.io.i.forEach(v => { h += `<div class="md-io-item">${v}</div>`; });
      h += '</div>';
    }
    if (nd.io.o && nd.io.o.length) {
      h += '<div class="md-io-col out"><div class="md-io-h out">OUTPUTS</div>';
      nd.io.o.forEach(v => { h += `<div class="md-io-item">${v}</div>`; });
      h += '</div>';
    }
    h += '</div>';
  }

  // KV metrics
  if (nd.kv) {
    h += `<div class="md-section" data-color="${color}"><span class="md-section-label">METRICS</span></div>`;
    h += '<div class="md-kv">';
    for (const [k, v] of Object.entries(nd.kv)) {
      h += `<div class="md-kv-item"><div class="md-kv-accent" style="background:${arrowColor}"></div><div class="md-kv-k">${k}</div><div class="md-kv-v">${v}</div></div>`;
    }
    h += '</div>';
  }

  // Opinion bars
  if (nd.bars) {
    h += `<div class="md-section" data-color="${color}"><span class="md-section-label">OPINION DISTRIBUTION</span></div>`;
    h += '<div class="md-bars">';
    nd.bars.forEach(bar => {
      h += `<div class="md-bar-row"><div class="md-bar-lbl">${bar[0]}</div><div class="md-bar-track">`;
      h += `<div class="md-bar-seg b" style="width:${bar[1]}%">${bar[1] > 6 ? bar[1] + '%' : ''}</div>`;
      h += `<div class="md-bar-seg d" style="width:${bar[2]}%">${bar[2] > 6 ? bar[2] + '%' : ''}</div>`;
      h += `<div class="md-bar-seg u" style="width:${bar[3]}%">${bar[3] > 6 ? bar[3] + '%' : ''}</div>`;
      h += '</div></div>';
    });
    h += '</div>';
  }

  // Conflict meter
  if (nd.conf != null) {
    h += `<div class="md-section" data-color="${color}"><span class="md-section-label">CONFLICT ANALYSIS</span></div>`;
    const sev = nd.conf < 0.1 ? 'none' : nd.conf < 0.2 ? 'low' : nd.conf < 0.4 ? 'moderate' : 'high';
    const sevLbl = nd.conf < 0.1 ? 'NO CONFLICT' : nd.conf < 0.2 ? 'LOW' : nd.conf < 0.4 ? 'MODERATE' : 'HIGH';
    const gaugeColor = sev === 'none' || sev === 'low' ? '#34d399' : sev === 'moderate' ? '#f59e0b' : '#ef4444';
    const gaugeAngle = Math.min(nd.conf, 1) * 360;
    const gaugeRad = gaugeAngle * Math.PI / 180;
    const gx = 20 + 16 * Math.sin(gaugeRad);
    const gy = 20 - 16 * Math.cos(gaugeRad);
    const largeArc = gaugeAngle > 180 ? 1 : 0;
    h += `<div class="md-conf ${sev}">`;
    h += '<div class="md-conf-gauge-wrap">';
    h += `<svg class="md-conf-gauge" viewBox="0 0 40 40">`;
    h += `<circle cx="20" cy="20" r="16" fill="none" stroke="${gaugeColor}" stroke-opacity=".15" stroke-width="3"/>`;
    if (gaugeAngle > 0.5) {
      h += `<path d="M20 4 A16 16 0 ${largeArc} 1 ${gx.toFixed(1)} ${gy.toFixed(1)}" fill="none" stroke="${gaugeColor}" stroke-width="3" stroke-linecap="round"/>`;
    }
    h += '</svg>';
    h += `<div class="md-conf-k">K = ${nd.conf.toFixed(2)}</div>`;
    h += '</div>';
    h += `<div class="md-conf-info"><div class="md-conf-sev">${sevLbl} CONFLICT</div>`;
    h += `<div class="md-conf-detail">${nd.confDetail || 'Dempster-Shafer conflict factor'}</div></div></div>`;
  }

  h += '</div>';

  // Apply content and color class to modal card
  const modalC = document.getElementById('modalC');
  if (modalC) {
    modalC.innerHTML = h;
    const card = modalC.closest('.modal-card');
    if (card) card.className = `modal-card ${color}`;
  }
  document.getElementById('modalOv')?.classList.add('open');
}

function _wireModal() {
  const modalOv = document.getElementById('modalOv');
  const modalX = document.getElementById('modalX');

  function closeModal() {
    modalOv?.classList.remove('open');
  }

  if (modalX) modalX.addEventListener('click', closeModal);
  if (modalOv) {
    modalOv.addEventListener('click', (e) => {
      if (e.target === modalOv) closeModal();
    });
  }
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modalOv?.classList.contains('open')) closeModal();
  });
}

function _onSearchNavigate(item) {
  if (item.type === 'klib') {
    openKlib();
  } else if (item.type === 'sub') {
    if (state.inSubmap) exitSubmap();
    setTimeout(() => {
      enterSubmap(item.parentId, state.submaps, state.nodeDetails, _openModal);
      setTimeout(() => {
        if (state.nodeDetails[item.id]) _openModal(item.id, item.parentId);
      }, 1400);
    }, state.inSubmap ? 200 : 100);
  } else {
    if (state.inSubmap) {
      exitSubmap();
      setTimeout(() => {
        if (state.submaps[item.id]) {
          enterSubmap(item.id, state.submaps, state.nodeDetails, _openModal);
        } else {
          openPanel(item.id);
        }
      }, 1300);
    } else {
      if (state.submaps[item.id]) {
        enterSubmap(item.id, state.submaps, state.nodeDetails, _openModal);
      } else {
        openPanel(item.id);
      }
    }
  }
}

// ═══ WP-3: Cmd+K keyboard shortcut ═══
function _wireCmdK() {
  document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault();
      if (state.searchOverlayOpen) {
        closeSearchOverlay();
      } else {
        openSearchOverlay();
      }
    }
  });
}

function _wireViewToggle() {
  const btns = document.querySelectorAll('#viewToggle .view-btn');
  btns.forEach(btn => {
    btn.addEventListener('click', () => {
      btns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      if (btn.dataset.view === '2d') show2d();
      else hide2d();
    });
  });
}

function _wireLegend() {
  const legend = document.getElementById('legend');
  if (!legend) return;
  legend.addEventListener('click', (e) => {
    const item = e.target.closest('.legend-item');
    if (!item) return;
    const edgeColor = item.dataset.edge;
    if (!edgeColor) return;
    item.classList.toggle('active');
    toggleConnectionType(edgeColor, item.classList.contains('active'));
  });
}

// ── Data-driven DOM updaters ──

function _updateHeader(title, description) {
  const h1 = document.querySelector('.header h1');
  const sub = document.querySelector('.header .sub');
  if (h1 && title) h1.textContent = title;
  if (sub && description) sub.textContent = description;
  if (title) document.title = `${title} -- Ontology Cockpit`;
}

function _updateStatsBar(stats) {
  if (!stats || !stats.length) return;
  const bar = document.querySelector('.stats-bar');
  if (!bar) return;
  bar.innerHTML = stats.map(s =>
    `<div class="stat"><span class="n" data-t="${s.value}">0</span><span class="l">${s.label}</span></div>`
  ).join('');
}

function _updateLegend(legend) {
  if (!legend || !legend.length) return;
  const el = document.getElementById('legend');
  if (!el) return;
  el.innerHTML = legend.map(l =>
    `<div class="legend-item active" data-edge="${l.edge_type}"><div class="legend-dot" style="background:${l.color}"></div>${l.label}</div>`
  ).join('');
}

// ═══ WP-4: Fractal Drill Wiring ═══

/**
 * Wire the fractal drill-down system: Edit button, Close button, Escape key,
 * double-click handler, and zoom event logging.
 */
function _wireDrillSystem() {
  // Edit button (L3 -> L4)
  const editBtn = document.getElementById('wp4EditBtn');
  if (editBtn) {
    editBtn.addEventListener('click', () => {
      if (getCurrentLevel() === LEVELS.FUNCTION) {
        edit();
      }
    });
  }

  // Editor close button (L4 -> L3)
  const editorCloseBtn = document.getElementById('wp4EditorClose');
  if (editorCloseBtn) {
    editorCloseBtn.addEventListener('click', () => {
      if (getCurrentLevel() === LEVELS.CODE) {
        closeEditor();
      }
    });
  }

  // Escape key: drill out one level
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      const level = getCurrentLevel();
      if (level === LEVELS.CODE) {
        e.preventDefault();
        e.stopPropagation();
        closeEditor();
      } else if (level > LEVELS.SYSTEM) {
        e.preventDefault();
        e.stopPropagation();
        drillOut();
      }
    }
  });

  // Double-click: drill into node
  const sc = document.getElementById('sc');
  if (sc) {
    sc.addEventListener('dblclick', (e) => {
      // The interaction system handles single clicks; double-click triggers drill
      if (state.selectedNode && getCurrentLevel() < LEVELS.FUNCTION) {
        const nodeData = _resolveClickNodeData(state.selectedNode);
        if (nodeData) {
          drillInto(state.selectedNode, nodeData);
        }
      }
    });
  }

  // Log zoom events for debugging
  onZoomEvent((event, data) => {
    console.log(`[WP-4] ${event}:`, data);
  });
}

/**
 * Resolve node data for drill-in from a clicked node ID.
 */
function _resolveClickNodeData(nodeId) {
  // Check submaps
  if (state.submaps && state.submaps[nodeId]) {
    const sm = state.submaps[nodeId];
    return {
      id: nodeId,
      label: sm.title || nodeId,
      children: sm.nodes || [],
      edges: sm.edges || [],
      color: sm.color,
      ...sm,
    };
  }
  // Check graph nodes
  const graphNode = (state.sysNodes || []).find(n => n.id === nodeId);
  if (graphNode) {
    return { id: nodeId, label: graphNode.label || nodeId, ...graphNode };
  }
  return null;
}

// ═══ End WP-4 ═══

// Boot
boot().catch(err => console.error('Boot failed:', err));
