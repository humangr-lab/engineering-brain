/* ═══════════════ INTERACTION — Raycasting, hover, click, selection ═══════════════ */

import * as T from 'three';
import { cam, ren, outlinePass } from './engine.js';
import { state } from '../state.js';

const raycaster = new T.Raycaster();
const mouse = new T.Vector2();

export let hoveredItemId = null;

let _clickables = [];
let _meshCache = [];          // O7: cached mesh array
let _onSelect = null;
let _onHover = null;
let _initialized = false;
let _lastMoveTime = 0;        // O7: throttle timestamp

/**
 * Initialize interaction system.
 * @param {Array} clickableObjects - [{mesh, id, data}]
 * @param {Function} onSelect - (item) => void
 * @param {Function} onHover - (item|null, event) => void
 */
export function initInteraction(clickableObjects, onSelect, onHover) {
  _clickables = clickableObjects;
  _meshCache = clickableObjects.map(c => c.mesh);
  _onSelect = onSelect;
  _onHover = onHover;

  if (!_initialized) {
    ren.domElement.addEventListener('click', _onClick);
    ren.domElement.addEventListener('mousemove', _onMouseMove);
    _initialized = true;
  }
}

function _onClick(event) {
  _updateMouse(event);
  raycaster.setFromCamera(mouse, cam);
  const intersects = raycaster.intersectObjects(_meshCache, false);

  if (intersects.length > 0) {
    const hit = intersects[0].object;
    const item = _clickables.find(c => {
      let obj = hit;
      while (obj) {
        if (obj === c.mesh) return true;
        obj = obj.parent;
      }
      return false;
    });

    if (item && _onSelect) {
      state.selectedNode = item.id;
      outlinePass.selectedObjects = [item.mesh];
      outlinePass.enabled = true;
      _onSelect(item);
    }
  } else {
    // Deselect
    state.selectedNode = null;
    outlinePass.selectedObjects = [];
    outlinePass.enabled = false;
    if (_onSelect) _onSelect(null);
  }
}

function _onMouseMove(event) {
  // O7: 16ms throttle
  const now = performance.now();
  if (now - _lastMoveTime < 16) return;
  _lastMoveTime = now;

  _updateMouse(event);
  raycaster.setFromCamera(mouse, cam);
  const intersects = raycaster.intersectObjects(_meshCache, false);

  if (intersects.length > 0) {
    const hit = intersects[0].object;
    const item = _clickables.find(c => {
      let obj = hit;
      while (obj) {
        if (obj === c.mesh) return true;
        obj = obj.parent;
      }
      return false;
    });
    ren.domElement.style.cursor = 'pointer';
    hoveredItemId = item ? item.id : null;
    if (item && _onHover) _onHover(item, event);
  } else {
    ren.domElement.style.cursor = 'default';
    hoveredItemId = null;
    if (_onHover) _onHover(null, event);
  }
}

function _updateMouse(event) {
  mouse.x = (event.clientX / innerWidth) * 2 - 1;
  mouse.y = -(event.clientY / innerHeight) * 2 + 1;
}

/**
 * Update the clickable objects list (e.g., when entering a sub-map).
 */
export function setClickables(newClickables) {
  _clickables = newClickables;
  _meshCache = newClickables.map(c => c.mesh);
}
