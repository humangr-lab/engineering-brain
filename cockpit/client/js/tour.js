/* ═══════════════ TOUR — Guided auto-tour through the architecture ═══════════════ */

import { state, subscribe } from './state.js';
import { animateCamera, CAMERA_PRESETS } from './scene/layout.js';
import { enterSubmap, exitSubmap } from './scene/submaps.js';

const TOUR_SCRIPT = [
  ['zone',  null,    5000, 'Welcome to the Engineering Brain — a self-improving epistemic knowledge graph with 3,700+ nodes and zero LLM calls for reasoning.'],
  ['node',  'seeds', 4000, 'Knowledge starts here: 285 expert-curated YAML seed files across 66 technologies and 69 domains.'],
  ['enter', 'seeds', 6000, 'Each seed file passes through schema validation, WHY/HOW quality scoring, deduplication, and edge building.'],
  ['exit',  null,    2000, 'Back to the main map...'],
  ['node',  'l0',    4000, 'Cortical Layer 0: Axioms — foundational truths with confidence 1.0 that never decay.'],
  ['enter', 'l0',    6000, 'Axioms from mathematics, computer science, and physics ground all reasoning chains.'],
  ['exit',  null,    2000, ''],
  ['node',  'erg',   5000, 'The ERG (Epistemic Reasoning Graph) — the core differentiator. Zero-LLM multi-chain reasoning via graph traversal.'],
  ['enter', 'erg',   6000, 'Subjective Logic opinion fusion, Dempster-Shafer evidence synthesis, contradiction detection, and gap analysis — all without a single LLM call.'],
  ['exit',  null,    2000, ''],
  ['node',  'cryst', 4000, 'The Crystallizer transforms L4 evidence into L3 rules using embedding similarity matching.'],
  ['node',  'adapt', 4000, 'Thompson Sampling optimizes scoring weights from user feedback. Each signal has a Beta posterior.'],
  ['node',  'mcp',   5000, 'The MCP Server exposes 20 tools: query, think, reason, search, learn, validate, and more.'],
  ['enter', 'mcp',   6000, 'Full Model Context Protocol implementation with JSON-RPC 2.0, epistemic reasoning, knowledge packs, and 20 specialized tools.'],
  ['exit',  null,    2000, ''],
  ['zone',  null,    5000, 'The Engineering Brain: self-improving, zero-LLM reasoning, 6 cortical layers, 32 edge types, and 285 seed sources. Built to scale.'],
];

let _timer = null;
let _icons = [];  // reference to scene icons for position lookup
let _openModalCb = null;

/**
 * Initialize tour system.
 * @param {Array} icons - scene icon references [{id, mesh}]
 * @param {Function} [openModal] - callback for opening node modals in submaps
 */
export function initTour(icons, openModal) {
  _icons = icons || [];
  _openModalCb = openModal || null;

  const btn = document.getElementById('tourBtn');
  if (btn) {
    btn.addEventListener('click', () => {
      if (state.tourActive) stopTour();
      else startTour();
    });
  }
}

export function startTour() {
  state.tourActive = true;
  state.tourStep = 0;
  const btn = document.getElementById('tourBtn');
  if (btn) btn.textContent = '\u25A0 Stop Tour';
  _runStep();
}

export function stopTour() {
  state.tourActive = false;
  if (_timer) { clearTimeout(_timer); _timer = null; }
  const info = document.getElementById('tourInfo');
  if (info) info.classList.remove('show');
  const btn = document.getElementById('tourBtn');
  if (btn) btn.textContent = '\u25B6 Auto Tour';
}

function _runStep() {
  if (!state.tourActive || state.tourStep >= TOUR_SCRIPT.length) {
    stopTour();
    return;
  }

  const [type, target, dur, text] = TOUR_SCRIPT[state.tourStep];
  const info = document.getElementById('tourInfo');
  const stepNum = state.tourStep + 1;
  const totalSteps = TOUR_SCRIPT.length;

  if (text && info) {
    info.textContent = `Step ${stepNum}/${totalSteps} \u2014 ${text}`;
    info.classList.add('show');
  } else if (info) {
    info.classList.remove('show');
  }

  const mainCam = CAMERA_PRESETS.default;

  switch (type) {
    case 'zone':
      animateCamera(mainCam.pos, mainCam.lookAt, 800);
      break;
    case 'node': {
      const sysNode = state.sysNodes.find(n => n.id === target);
      const icon = _icons.find(i => i.id === target);
      if (sysNode) {
        const lookAt = icon
          ? { x: icon.mesh.position.x, y: 0, z: icon.mesh.position.z }
          : { x: sysNode.x, y: 0, z: sysNode.z };
        animateCamera(mainCam.pos, lookAt, 800);
      }
      break;
    }
    case 'enter':
      if (target && !state.inSubmap) {
        enterSubmap(target, state.submaps, state.nodeDetails, _openModalCb);
      }
      break;
    case 'exit':
      if (state.inSubmap) exitSubmap();
      break;
  }

  state.tourStep++;
  _timer = setTimeout(_runStep, dur);
}
