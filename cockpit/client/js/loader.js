/* ====== LOADER -- Schema-driven cockpit loader ======
   Fetches graph_data.json, optionally cockpit_schema.yaml,
   runs inference engine, merges overrides, outputs internal format
   compatible with app.js _buildScene().                          */

import { inferConfig } from './inference/engine.js';

/**
 * Load a cockpit from graph data URL, with optional schema overrides.
 *
 * @param {string} graphUrl - URL to graph_data.json
 * @param {object} [options]
 * @param {string} [options.schemaUrl] - URL to cockpit_schema.yaml/json
 * @param {string} [options.theme='dark'] - 'dark' or 'light'
 * @param {boolean} [options.log=false] - Enable inference logging
 * @returns {Promise<object>} Internal cockpit data
 */
export async function loadCockpit(graphUrl, options = {}) {
  const { schemaUrl = null, theme = 'dark', log = false } = options;

  // 1. Fetch graph data
  const graphData = await _fetchJson(graphUrl);
  _validateGraphData(graphData);

  // 2. Optionally fetch cockpit schema
  let schema = null;
  if (schemaUrl) {
    schema = await _fetchSchema(schemaUrl);
  }

  // 3. Run inference engine
  const inferred = inferConfig(graphData, { theme, log });

  // 4. Merge schema overrides over inferred values
  const merged = _mergeOverrides(graphData, inferred, schema);

  // 5. Build internal format compatible with app.js
  return _buildInternalFormat(graphData, inferred, merged, schema);
}

/**
 * Load cockpit from already-fetched data objects (no network needed).
 */
export function loadCockpitFromData(graphData, schema = null, options = {}) {
  const { theme = 'dark', log = false } = options;
  _validateGraphData(graphData);
  const inferred = inferConfig(graphData, { theme, log });
  const merged = _mergeOverrides(graphData, inferred, schema);
  return _buildInternalFormat(graphData, inferred, merged, schema);
}

// ── Fetch helpers ──

async function _fetchJson(url) {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`Failed to fetch ${url}: ${resp.status}`);
  const text = await resp.text();
  try {
    return JSON.parse(text);
  } catch (e) {
    throw new Error(`[Loader] Invalid JSON from ${url}: ${e.message}`);
  }
}

async function _fetchSchema(url) {
  const resp = await fetch(url);
  if (!resp.ok) {
    console.warn(`[Loader] Schema not found at ${url}, proceeding with inference only`);
    return null;
  }

  const contentType = resp.headers.get('content-type') || '';
  const text = await resp.text();

  // Detect YAML vs JSON
  if (url.endsWith('.yaml') || url.endsWith('.yml') || contentType.includes('yaml')) {
    try {
      return _parseYaml(text);
    } catch (e) {
      console.warn(`[Loader] YAML parse error in ${url}:`, e);
      return null;
    }
  }
  try {
    return JSON.parse(text);
  } catch (e) {
    console.warn(`[Loader] JSON parse error in schema ${url}:`, e);
    return null;
  }
}

/**
 * Minimal YAML parser for cockpit_schema.yaml.
 * Handles: scalars, objects, arrays, nested indentation.
 * NOT a full YAML parser -- sufficient for our schema files.
 */
function _parseYaml(text) {
  const lines = text.split('\n');
  return _yamlParse(lines, 0, 0).value;
}

function _yamlParse(lines, startIdx, baseIndent) {
  const result = {};
  let i = startIdx;

  while (i < lines.length) {
    const line = lines[i];
    const stripped = line.replace(/\r$/, '');

    // Skip empty lines and comments
    if (!stripped.trim() || stripped.trim().startsWith('#')) {
      i++;
      continue;
    }

    // Compute indentation
    const indent = stripped.length - stripped.trimStart().length;

    // If we've dedented back past our level, stop
    if (indent < baseIndent && i > startIdx) {
      break;
    }

    // If this is deeper than our base, skip (handled by recursive calls)
    if (indent > baseIndent && i > startIdx) {
      i++;
      continue;
    }

    const trimmed = stripped.trim();

    // Array item: "- value" or "- key: value"
    if (trimmed.startsWith('- ')) {
      // This is an array context -- let parent handle it
      break;
    }

    // Key: value pair
    const colonIdx = trimmed.indexOf(':');
    if (colonIdx === -1) {
      i++;
      continue;
    }

    const key = trimmed.substring(0, colonIdx).trim();
    const valueStr = trimmed.substring(colonIdx + 1).trim();

    if (valueStr === '' || valueStr === '|' || valueStr === '>') {
      // Check for nested content: array or object
      const nextNonEmpty = _findNextNonEmpty(lines, i + 1);
      if (nextNonEmpty < lines.length) {
        const nextLine = lines[nextNonEmpty].replace(/\r$/, '');
        const nextIndent = nextLine.length - nextLine.trimStart().length;
        const nextTrimmed = nextLine.trim();

        if (nextIndent > indent && nextTrimmed.startsWith('- ')) {
          // Array
          const arr = _yamlParseArray(lines, nextNonEmpty, nextIndent);
          result[key] = arr.value;
          i = arr.nextIdx;
          continue;
        } else if (nextIndent > indent) {
          // Nested object
          const nested = _yamlParse(lines, nextNonEmpty, nextIndent);
          result[key] = nested.value;
          i = nested.nextIdx;
          continue;
        }
      }
      result[key] = null;
      i++;
    } else {
      result[key] = _yamlScalar(valueStr);
      i++;
    }
  }

  return { value: result, nextIdx: i };
}

function _yamlParseArray(lines, startIdx, baseIndent) {
  const result = [];
  let i = startIdx;

  while (i < lines.length) {
    const line = lines[i].replace(/\r$/, '');
    if (!line.trim() || line.trim().startsWith('#')) {
      i++;
      continue;
    }

    const indent = line.length - line.trimStart().length;
    if (indent < baseIndent) break;

    const trimmed = line.trim();
    if (!trimmed.startsWith('- ')) break;

    const itemContent = trimmed.substring(2).trim();

    // Check if item is a compact object: "- {id: x, label: y}"
    if (itemContent.startsWith('{') && itemContent.endsWith('}')) {
      result.push(_parseInlineObject(itemContent));
      i++;
      continue;
    }

    // Check if item has key:value on same line: "- key: value"
    if (itemContent.includes(':')) {
      // Could be a mapping item
      const obj = {};
      const firstColon = itemContent.indexOf(':');
      const k = itemContent.substring(0, firstColon).trim();
      const v = itemContent.substring(firstColon + 1).trim();
      obj[k] = _yamlScalar(v);

      // Check for more keys at deeper indent
      const nextNonEmpty = _findNextNonEmpty(lines, i + 1);
      if (nextNonEmpty < lines.length) {
        const nextLine = lines[nextNonEmpty].replace(/\r$/, '');
        const nextIndent = nextLine.length - nextLine.trimStart().length;
        const nextTrimmed = nextLine.trim();
        if (nextIndent > indent && !nextTrimmed.startsWith('- ')) {
          const nested = _yamlParse(lines, nextNonEmpty, nextIndent);
          Object.assign(obj, nested.value);
          i = nested.nextIdx;
          result.push(obj);
          continue;
        }
      }
      result.push(obj);
      i++;
    } else {
      // Simple scalar item
      result.push(_yamlScalar(itemContent));
      i++;
    }
  }

  return { value: result, nextIdx: i };
}

function _parseInlineObject(str) {
  // Parse "{key: val, key: val}" compact format
  const inner = str.slice(1, -1).trim();
  const obj = {};
  // Split on commas, handling quoted values
  const parts = _splitInlineObject(inner);
  for (const part of parts) {
    const colonIdx = part.indexOf(':');
    if (colonIdx === -1) continue;
    const k = part.substring(0, colonIdx).trim();
    const v = part.substring(colonIdx + 1).trim();
    obj[k] = _yamlScalar(v);
  }
  return obj;
}

function _splitInlineObject(str) {
  const parts = [];
  let current = '';
  let inQuote = false;
  let quoteChar = '';
  for (let i = 0; i < str.length; i++) {
    const ch = str[i];
    if (inQuote) {
      current += ch;
      if (ch === quoteChar) inQuote = false;
    } else if (ch === '"' || ch === "'") {
      inQuote = true;
      quoteChar = ch;
      current += ch;
    } else if (ch === ',') {
      parts.push(current.trim());
      current = '';
    } else {
      current += ch;
    }
  }
  if (current.trim()) parts.push(current.trim());
  return parts;
}

function _yamlScalar(s) {
  if (s === '' || s === 'null' || s === '~') return null;
  if (s === 'true') return true;
  if (s === 'false') return false;

  // Remove quotes
  if ((s.startsWith("'") && s.endsWith("'")) || (s.startsWith('"') && s.endsWith('"'))) {
    return s.slice(1, -1);
  }

  // Numbers
  const num = Number(s);
  if (!isNaN(num) && s !== '') return num;

  return s;
}

function _findNextNonEmpty(lines, startIdx) {
  let i = startIdx;
  while (i < lines.length) {
    const trimmed = lines[i].replace(/\r$/, '').trim();
    if (trimmed && !trimmed.startsWith('#')) return i;
    i++;
  }
  return i;
}

// ── Validation ──

function _validateGraphData(data) {
  if (!data || typeof data !== 'object') {
    throw new Error('[Loader] graph_data must be an object');
  }
  if (!Array.isArray(data.nodes)) {
    // Tolerate missing nodes: default to empty array
    data.nodes = [];
  }
  if (!Array.isArray(data.edges)) {
    // Tolerate missing edges: default to empty array
    data.edges = [];
  }
  // Empty graph is valid -- engine.js returns _blankConfig() for it
  for (const n of data.nodes) {
    if (!n.id) throw new Error('[Loader] Every node must have an id');
  }
}

// ── Merge ──

function _mergeOverrides(graphData, inferred, schema) {
  if (!schema) return inferred;

  const merged = { ...inferred };

  // Meta overrides
  if (schema.meta) {
    if (schema.meta.template) merged.template = schema.meta.template;
    if (schema.meta.layout) merged.layout = schema.meta.layout;
  }

  // Per-node overrides (shape, size, group)
  if (schema.nodes) {
    for (const [nodeId, overrides] of Object.entries(schema.nodes)) {
      if (overrides.shape) {
        merged.shapes.set(nodeId, overrides.shape);
      }
      if (overrides.size != null) {
        merged.sizes.set(nodeId, overrides.size);
      }
    }
  }

  return merged;
}

// ── Internal format builder ──

function _buildInternalFormat(graphData, inferred, merged, schema) {
  const metadata = graphData.metadata || {};
  const schemaDetails = schema?.details || {};
  const schemaSubmaps = schema?.submaps || {};
  const schemaNodes = schema?.nodes || {};
  const schemaStats = schema?.stats || null;
  const schemaLegend = schema?.legend || null;
  const sceneCfg = schema?.scene || {};

  // Build N array (sysmap-compatible node format for app.js)
  const N = graphData.nodes.map(n => {
    const props = n.properties || {};
    const nodeOverride = schemaNodes[n.id] || {};
    const shape = merged.shapes.get(n.id) || 'sphere';
    const group = nodeOverride.group || n.group || n.type || 'module';

    // Position: prefer explicit, then properties, then 0
    const x = nodeOverride.x ?? props.x ?? 0;
    const z = nodeOverride.z ?? props.z ?? 0;

    return {
      id: n.id,
      label: nodeOverride.label || n.label || _labelFromId(n.id),
      sub: nodeOverride.sub || props.subtitle || props.description || '',
      g: group,
      sh: shape,
      x,
      z,
      hero: nodeOverride.hero || props.hero || false,
      auto: nodeOverride.auto || props.auto || false,
      hidden: nodeOverride.hidden || false,
      // Preserve size for layout
      _inferredSize: merged.sizes.get(n.id) || 1.0,
      // Preserve original properties
      _properties: props,
    };
  });

  // Build E array (sysmap-compatible edge format)
  const E = graphData.edges.map(e => {
    const edgeProps = e.properties || {};
    return {
      f: e.from || e.f,
      t: e.to || e.t,
      c: edgeProps.color || _edgeTypeToColor(e.type),
    };
  });

  // Title / subtitle for header
  const title = schema?.meta?.title || metadata.name || 'Ontology Cockpit';
  const description = schema?.meta?.description || '';

  // Stats: from schema or auto-generated
  const stats = schemaStats || _autoGenerateStats(graphData, N);

  // Legend: from schema or auto-generated from edge colors
  const legend = schemaLegend || _autoGenerateLegend(E);

  return {
    // Core data (sysmap-compatible)
    N,
    E,
    DT: schemaDetails,
    SUBMAPS: schemaSubmaps,
    ND: schema?.node_data || {},
    DOC_TREE: [],
    KLIB: {},

    // Metadata
    title,
    description,
    stats,
    legend,

    // Inference results (for transparency/debug)
    inferredConfig: merged,
    graphData,
    cockpitSchema: schema,

    // Scene config
    scene: sceneCfg,
  };
}

/**
 * Derive a human-readable label from a node ID.
 * 'auth_service' -> 'Auth Service', 'my-module' -> 'My Module'
 */
function _labelFromId(id) {
  return id
    .replace(/[_.-]/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase());
}

/**
 * Map edge type to a color name.
 */
function _edgeTypeToColor(type) {
  if (!type) return 'white';
  const t = type.toUpperCase();
  if (['HTTP', 'GRPC', 'REST', 'CALLS', 'AMQP'].includes(t)) return 'cyan';
  if (['CONTAINS', 'GROUNDS', 'INFORMS'].includes(t)) return 'white';
  if (['IMPORTS', 'DEPENDS_ON'].includes(t)) return 'blue';
  if (['PUBLISHES', 'SUBSCRIBES'].includes(t)) return 'green';
  if (['DERIVES', 'SUPPORTS', 'REINFORCES'].includes(t)) return 'purple';
  return 'white';
}

/**
 * Auto-generate stats from graph data.
 */
function _autoGenerateStats(graphData, nodes) {
  const nodeCount = graphData.nodes.length;
  const edgeCount = graphData.edges.length;
  const groups = new Set(nodes.map(n => n.g));
  const edgeTypes = new Set(graphData.edges.map(e => e.type).filter(Boolean));

  return [
    { label: 'Nodes', value: nodeCount },
    { label: 'Edges', value: edgeCount },
    { label: 'Groups', value: groups.size },
    ...(edgeTypes.size > 0 ? [{ label: 'Edge Types', value: edgeTypes.size }] : []),
  ];
}

/**
 * Auto-generate legend from edge colors present in the graph.
 */
function _autoGenerateLegend(edges) {
  const colorLabels = {
    green: 'Data Flow',
    blue: 'Dependencies',
    purple: 'Feedback',
    cyan: 'Delivery',
    white: 'Hierarchy',
  };

  const colorHexes = {
    green: '#34d399',
    blue: '#6b8fff',
    purple: '#9b7cff',
    cyan: '#5eead4',
    white: '#8899bb',
  };

  const usedColors = new Set(edges.map(e => e.c));
  return [...usedColors].map(c => ({
    label: colorLabels[c] || c,
    color: colorHexes[c] || '#808080',
    edge_type: c,
  }));
}
