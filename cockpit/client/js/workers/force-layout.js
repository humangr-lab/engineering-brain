/* ═══════════════ WP-PERF: FORCE LAYOUT WEB WORKER ═══════════════
   Runs d3-force-3d simulation off the main thread.
   Communicates via postMessage with Transferable Float32Arrays.

   Messages IN:
     { type: 'init', nodes: [...], edges: [...], config: {...} }
     { type: 'tick' }
     { type: 'pin', nodeId: string, x, y, z }
     { type: 'stop' }

   Messages OUT:
     { type: 'positions', data: Float32Array, alpha: number }
     { type: 'converged', alpha: number }
     { type: 'ready' }
     { type: 'error', message: string }
   ════════════════════════════════════════════════════════════════ */

// Import d3-force-3d from CDN (same version as importmap)
importScripts('https://cdn.jsdelivr.net/npm/d3-force-3d@3/dist/d3-force-3d.min.js');

let simulation = null;
let nodeArray = [];
let nodeIndexMap = new Map(); // nodeId → index
let ticksPerMessage = 1;
let running = false;
let converged = false;

self.onmessage = function (e) {
  const msg = e.data;

  switch (msg.type) {
    case 'init':
      _init(msg.nodes, msg.edges, msg.config || {});
      break;

    case 'tick':
      _tick();
      break;

    case 'pin':
      _pin(msg.nodeId, msg.x, msg.y, msg.z);
      break;

    case 'stop':
      _stop();
      break;

    default:
      self.postMessage({ type: 'error', message: `Unknown message type: ${msg.type}` });
  }
};

function _init(nodes, edges, config) {
  try {
    // Build node array with initial positions
    nodeArray = nodes.map((n, i) => ({
      id: n.id,
      index: i,
      x: n.x ?? n.properties?.x ?? (Math.random() - 0.5) * 50,
      y: n.y ?? n.properties?.y ?? (Math.random() - 0.5) * 10,
      z: n.z ?? n.properties?.z ?? (Math.random() - 0.5) * 50,
      fx: null,
      fy: null,
      fz: null,
    }));

    // Build lookup
    nodeIndexMap.clear();
    nodeArray.forEach((n, i) => nodeIndexMap.set(n.id, i));

    // Build link array (d3-force uses source/target)
    const links = edges
      .filter(e => nodeIndexMap.has(e.f || e.from) && nodeIndexMap.has(e.t || e.to))
      .map(e => ({
        source: e.f || e.from,
        target: e.t || e.to,
      }));

    // Configuration with sensible defaults
    const alpha = config.alpha ?? 0.3;
    const alphaDecay = config.alphaDecay ?? 0.01;
    const velocityDecay = config.velocityDecay ?? 0.4;
    const chargeStrength = config.chargeStrength ?? -100;
    const linkDistance = config.linkDistance ?? 15;
    const centerStrength = config.centerStrength ?? 0.05;
    ticksPerMessage = config.ticksPerMessage ?? 3;

    // Create 3D force simulation
    // d3.forceSimulation is available globally from the importScripts above
    /* global d3 */
    simulation = d3.forceSimulation(nodeArray, 3)
      .alpha(alpha)
      .alphaDecay(alphaDecay)
      .velocityDecay(velocityDecay)
      .force('charge', d3.forceManyBody().strength(chargeStrength))
      .force('link', d3.forceLink(links).id(d => d.id).distance(linkDistance))
      .force('center', d3.forceCenter(0, 0, 0).strength(centerStrength))
      .stop(); // We tick manually

    running = true;
    converged = false;

    self.postMessage({ type: 'ready' });
  } catch (err) {
    self.postMessage({ type: 'error', message: err.message });
  }
}

function _tick() {
  if (!simulation || !running) return;

  // Run N ticks per message to amortize postMessage overhead
  for (let i = 0; i < ticksPerMessage; i++) {
    simulation.tick();
  }

  const alpha = simulation.alpha();

  // Build position buffer as Float32Array (Transferable)
  const buffer = new Float32Array(nodeArray.length * 3);
  for (let i = 0; i < nodeArray.length; i++) {
    buffer[i * 3] = nodeArray[i].x;
    buffer[i * 3 + 1] = nodeArray[i].y;
    buffer[i * 3 + 2] = nodeArray[i].z;
  }

  // Transfer ownership of the buffer (zero-copy)
  self.postMessage(
    { type: 'positions', data: buffer, alpha },
    [buffer.buffer],
  );

  // Check convergence
  if (alpha < 0.001 && !converged) {
    converged = true;
    self.postMessage({ type: 'converged', alpha });
  }
}

function _pin(nodeId, x, y, z) {
  if (!simulation) return;
  const idx = nodeIndexMap.get(nodeId);
  if (idx == null) return;

  const node = nodeArray[idx];
  if (x != null) { node.fx = x; node.x = x; }
  if (y != null) { node.fy = y; node.y = y; }
  if (z != null) { node.fz = z; node.z = z; }

  // Reheat simulation slightly when a node is pinned
  if (simulation.alpha() < 0.05) {
    simulation.alpha(0.1);
    converged = false;
  }
}

function _stop() {
  running = false;
  if (simulation) {
    simulation.stop();
    simulation = null;
  }
  nodeArray = [];
  nodeIndexMap.clear();
  self.close();
}
