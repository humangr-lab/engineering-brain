/* ═══════════════ WP-A11Y: FOCUS TRAP — Modal/overlay focus containment ═══════════════
   Creates, activates, and deactivates focus traps for modal overlays.
   Traps Tab/Shift+Tab within a container and restores focus on deactivation.

   Exports: createFocusTrap(container), activateTrap(trapId), deactivateTrap(trapId) */

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ');

/** @type {Map<string, {container: HTMLElement, handler: Function, triggerEl: HTMLElement|null}>} */
const _traps = new Map();

/** @type {string|null} Active trap ID */
let _activeTrapId = null;

/**
 * Register a focus trap on a container element.
 * @param {HTMLElement} container - The element to trap focus within
 * @returns {string} Trap ID (based on container id or auto-generated)
 */
export function createFocusTrap(container) {
  if (!container) return '';

  const trapId = container.id || `trap-${_traps.size}`;

  if (_traps.has(trapId)) return trapId;

  function handler(e) {
    if (e.key !== 'Tab') return;

    const focusables = Array.from(container.querySelectorAll(FOCUSABLE_SELECTOR))
      .filter(el => el.offsetParent !== null); // visible only

    if (focusables.length === 0) {
      e.preventDefault();
      return;
    }

    const first = focusables[0];
    const last = focusables[focusables.length - 1];

    if (e.shiftKey) {
      // Shift+Tab: if on first element, wrap to last
      if (document.activeElement === first || !container.contains(document.activeElement)) {
        e.preventDefault();
        last.focus();
      }
    } else {
      // Tab: if on last element, wrap to first
      if (document.activeElement === last || !container.contains(document.activeElement)) {
        e.preventDefault();
        first.focus();
      }
    }
  }

  _traps.set(trapId, { container, handler, triggerEl: null });
  return trapId;
}

/**
 * Activate a focus trap. Saves the currently focused element for restoration.
 * @param {string} trapId - The trap to activate
 */
export function activateTrap(trapId) {
  const trap = _traps.get(trapId);
  if (!trap) return;

  // Save the element that triggered the overlay
  trap.triggerEl = document.activeElement;

  // Deactivate any existing active trap
  if (_activeTrapId && _activeTrapId !== trapId) {
    deactivateTrap(_activeTrapId);
  }

  _activeTrapId = trapId;

  // Attach keydown listener
  trap.container.addEventListener('keydown', trap.handler);

  // Focus the first focusable element inside the container
  requestAnimationFrame(() => {
    const focusables = Array.from(trap.container.querySelectorAll(FOCUSABLE_SELECTOR))
      .filter(el => el.offsetParent !== null);

    // Prefer an input or the close button
    const input = trap.container.querySelector('input:not([disabled])');
    const closeBtn = trap.container.querySelector('[class*="-x"], [class*="close"]');
    const target = input || closeBtn || focusables[0];

    if (target) target.focus();
  });
}

/**
 * Deactivate a focus trap and restore focus to the triggering element.
 * @param {string} trapId - The trap to deactivate
 */
export function deactivateTrap(trapId) {
  const trap = _traps.get(trapId);
  if (!trap) return;

  // Remove keydown listener
  trap.container.removeEventListener('keydown', trap.handler);

  if (_activeTrapId === trapId) {
    _activeTrapId = null;
  }

  // Restore focus to the element that opened the overlay
  if (trap.triggerEl && trap.triggerEl.isConnected) {
    requestAnimationFrame(() => {
      trap.triggerEl.focus();
      trap.triggerEl = null;
    });
  }
}
