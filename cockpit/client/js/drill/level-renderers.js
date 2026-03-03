/* ═══════════════ WP-4: LEVEL RENDERERS — Per-level rendering logic ═══════════════
   L0-L2: 3D shapes (existing Three.js nodes with DOI-based visibility)
   L3: Shiki syntax highlighting panel (~25KB lazy load via dynamic import)
   L4: CodeMirror 6 editor panel (~75KB lazy load via dynamic import)

   Each level renderer: enter(nodeData), exit(), update()
   Show/hide code panels based on drill level.

   References:
     - docs/research/F-06_fractal_drill_down.md Sections 4, 8.3, 8.4
     - docs/design/wireframes.md Screen 2, Screen 5                               */

import * as T from 'three';
import { scene, cam } from '../scene/engine.js';
import { state, batch } from '../state.js';
import { LEVELS } from './zoom-manager.js';

/* ── Module state ── */

let _activeLevel = null;
let _levelGroup = null;          // Three.js Group for current drill level content
let _codePanelEl = null;         // DOM reference to code panel container
let _editorPanelEl = null;       // DOM reference to editor panel container
let _shikiInstance = null;       // Cached Shiki highlighter
let _codeMirrorView = null;      // CodeMirror EditorView instance
let _codeMirrorLoaded = false;   // Whether CM6 module is loaded
let _shikiLoaded = false;        // Whether Shiki module is loaded
let _codeContent = '';           // Current code content for L3/L4

/* ── Public API ── */

/**
 * Render content for a drill level.
 * @param {number} level - Drill level (0-4)
 * @param {object} nodeData - Data for the focused node
 */
export function renderLevel(level, nodeData) {
  _activeLevel = level;

  switch (level) {
    case LEVELS.SYSTEM:
      _renderSystem(nodeData);
      break;
    case LEVELS.MODULE:
      _renderModule(nodeData);
      break;
    case LEVELS.FILE:
      _renderFile(nodeData);
      break;
    case LEVELS.FUNCTION:
      _renderFunction(nodeData);
      break;
    case LEVELS.CODE:
      _renderCode(nodeData);
      break;
    default:
      console.warn(`[WP-4] renderLevel: unknown level ${level}`);
  }
}

/**
 * Exit/cleanup rendering for a drill level.
 * @param {number} level - Drill level being exited
 */
export function exitLevel(level) {
  switch (level) {
    case LEVELS.SYSTEM:
    case LEVELS.MODULE:
    case LEVELS.FILE:
      _exit3DLevel();
      break;
    case LEVELS.FUNCTION:
      _exitCodePanel();
      break;
    case LEVELS.CODE:
      _exitEditorPanel();
      break;
  }
  _activeLevel = null;
}

/* ── L0: System View ── */

function _renderSystem(_nodeData) {
  // At L0, the main scene is visible. Restore all main nodes.
  _showMainScene();
  _hideCodePanels();
  _restoreSceneContainer();
}

/* ── L1: Module View ── */

function _renderModule(nodeData) {
  _hideCodePanels();
  _restoreSceneContainer();

  if (!nodeData) return;

  // Create a Three.js group for module-level child nodes
  _levelGroup = new T.Group();
  _levelGroup.name = 'wp4-drill-L1';
  scene.add(_levelGroup);

  // Render children as cubes (file nodes)
  const children = nodeData.children || nodeData.nodes || [];
  const edges = nodeData.edges || [];

  // Compute grid positions for children
  const count = children.length;
  const cols = Math.ceil(Math.sqrt(count));
  const spacing = 4;

  children.forEach((child, i) => {
    const row = Math.floor(i / cols);
    const col = i % cols;
    const x = (col - (cols - 1) / 2) * spacing;
    const z = (row - (Math.ceil(count / cols) - 1) / 2) * spacing;

    // File node: cube shape
    const geometry = new T.BoxGeometry(1.5, 1.5, 1.5);
    const material = new T.MeshStandardMaterial({
      color: _getNodeColor(child),
      metalness: 0.1,
      roughness: 0.6,
      transparent: true,
      opacity: 0,
    });
    const mesh = new T.Mesh(geometry, material);
    mesh.position.set(x, 1, z);
    mesh.userData = { id: child.id || child, nodeData: child };

    _levelGroup.add(mesh);

    // Fade in animation
    _animateOpacity(material, 0, 1, 300, i * 40);
  });

  // Draw edges between children
  _drawChildEdges(_levelGroup, children, edges, cols, spacing, count);
}

/* ── L2: File View ── */

function _renderFile(nodeData) {
  _hideCodePanels();
  _restoreSceneContainer();

  if (!nodeData) return;

  _levelGroup = new T.Group();
  _levelGroup.name = 'wp4-drill-L2';
  scene.add(_levelGroup);

  // At L2, we show classes and functions within the file
  // Data might come from source_location or submap children
  const symbols = nodeData.symbols || nodeData.children || nodeData.nodes || [];
  const count = symbols.length;
  const cols = Math.ceil(Math.sqrt(Math.max(count, 1)));
  const spacing = 3;

  symbols.forEach((sym, i) => {
    const row = Math.floor(i / cols);
    const col = i % cols;
    const x = (col - (cols - 1) / 2) * spacing;
    const z = (row - (Math.ceil(count / cols) - 1) / 2) * spacing;

    const type = sym.type || sym.sh || 'sphere';
    const geometry = _getSymbolGeometry(type);
    const material = new T.MeshStandardMaterial({
      color: _getSymbolColor(type),
      metalness: 0.15,
      roughness: 0.5,
      transparent: true,
      opacity: 0,
    });
    const mesh = new T.Mesh(geometry, material);
    mesh.position.set(x, 0.8, z);
    mesh.userData = { id: sym.id || sym, nodeData: sym };

    _levelGroup.add(mesh);

    _animateOpacity(material, 0, 1, 300, i * 30);
  });
}

/* ── L3: Function / Read-Only Code View (Shiki) ── */

function _renderFunction(nodeData) {
  // Show code panel, compress 3D scene to 40%
  _compressSceneContainer();
  _showCodePanel();

  // Load code content
  const codeContent = _getCodeContent(nodeData);
  _codeContent = codeContent;

  // Lazy-load Shiki and render
  _loadAndRenderShiki(codeContent, nodeData);
}

/* ── L4: Editable Code View (CodeMirror 6) ── */

function _renderCode(nodeData) {
  // Show editor panel, keep 3D scene compressed
  _compressSceneContainer();
  _hideCodePanel();
  _showEditorPanel();

  const codeContent = _codeContent || _getCodeContent(nodeData);

  // Lazy-load CodeMirror 6 and render
  _loadAndRenderCodeMirror(codeContent, nodeData);
}

/* ── Exit helpers ── */

function _exit3DLevel() {
  if (_levelGroup) {
    // Dispose all children
    _levelGroup.traverse(obj => {
      if (obj.geometry) obj.geometry.dispose();
      if (obj.material) {
        if (Array.isArray(obj.material)) obj.material.forEach(m => m.dispose());
        else obj.material.dispose();
      }
    });
    scene.remove(_levelGroup);
    _levelGroup = null;
  }
}

function _exitCodePanel() {
  _hideCodePanel();
  _restoreSceneContainer();
  _shikiInstance = null;
}

function _exitEditorPanel() {
  if (_codeMirrorView) {
    _codeMirrorView.destroy();
    _codeMirrorView = null;
  }
  _hideEditorPanel();
  _restoreSceneContainer();
}

/* ── DOM Panel management ── */

function _getCodePanel() {
  if (!_codePanelEl) {
    _codePanelEl = document.getElementById('wp4CodePanel');
  }
  return _codePanelEl;
}

function _getEditorPanel() {
  if (!_editorPanelEl) {
    _editorPanelEl = document.getElementById('wp4EditorPanel');
  }
  return _editorPanelEl;
}

function _showCodePanel() {
  const panel = _getCodePanel();
  if (panel) {
    panel.classList.add('wp4-visible');
    panel.style.display = 'flex';
  }
}

function _hideCodePanel() {
  const panel = _getCodePanel();
  if (panel) {
    panel.classList.remove('wp4-visible');
    panel.style.display = 'none';
    const codeArea = panel.querySelector('.wp4-code-area');
    if (codeArea) codeArea.innerHTML = '';
  }
}

function _showEditorPanel() {
  const panel = _getEditorPanel();
  if (panel) {
    panel.classList.add('wp4-visible');
    panel.style.display = 'flex';
  }
}

function _hideEditorPanel() {
  const panel = _getEditorPanel();
  if (panel) {
    panel.classList.remove('wp4-visible');
    panel.style.display = 'none';
    const editorArea = panel.querySelector('.wp4-editor-area');
    if (editorArea) editorArea.innerHTML = '';
  }
}

function _hideCodePanels() {
  _hideCodePanel();
  _hideEditorPanel();
}

/**
 * Compress the 3D scene container to 40% width for code panel split.
 */
function _compressSceneContainer() {
  const sc = document.getElementById('sc');
  if (sc) {
    sc.style.transition = 'width 200ms cubic-bezier(0.2, 0, 0, 1)';
    sc.style.width = '40%';
  }
}

/**
 * Restore the 3D scene container to full width.
 */
function _restoreSceneContainer() {
  const sc = document.getElementById('sc');
  if (sc) {
    sc.style.transition = 'width 200ms cubic-bezier(0.2, 0, 0, 1)';
    sc.style.width = '100%';
  }
}

function _showMainScene() {
  // Ensure the main group is visible when returning to L0
  scene.traverse(obj => {
    if (obj.name === 'wp4-drill-L1' || obj.name === 'wp4-drill-L2') {
      scene.remove(obj);
    }
  });
}

/* ── Shiki lazy loader ── */

async function _loadAndRenderShiki(code, nodeData) {
  const panel = _getCodePanel();
  if (!panel) return;

  const codeArea = panel.querySelector('.wp4-code-area');
  const fileLabel = panel.querySelector('.wp4-code-file-label');
  const badge = panel.querySelector('.wp4-code-badge');

  // Update header
  if (fileLabel) fileLabel.textContent = nodeData?.label || nodeData?.id || 'Code';
  if (badge) { badge.textContent = 'RO'; badge.className = 'wp4-code-badge wp4-badge-ro'; }

  if (!codeArea) return;

  // Show loading state
  codeArea.innerHTML = '<div class="wp4-code-loading">Loading syntax highlighter...</div>';

  // If no actual code, show placeholder
  if (!code || code === '// No source available') {
    codeArea.innerHTML = `<pre class="wp4-code-pre"><code class="wp4-code-block">${_escapeHtml(code || '// No source available for this node.\n// Connect a Project Graph server to enable code viewing.')}</code></pre>`;
    return;
  }

  try {
    // Lazy load Shiki via CDN dynamic import
    if (!_shikiLoaded) {
      const { codeToHtml } = await import('https://esm.sh/shiki@1.0.0/bundle/web');
      _shikiInstance = codeToHtml;
      _shikiLoaded = true;
    }

    // Detect language from file extension
    const lang = _detectLanguage(nodeData);

    const html = await _shikiInstance(code, {
      lang,
      theme: _getShikiTheme(),
    });

    codeArea.innerHTML = html;

    // Add line numbers
    _addLineNumbers(codeArea, code);

    // Highlight the focused symbol's line range
    if (nodeData?.source_location) {
      _highlightLineRange(codeArea, nodeData.source_location.start_line, nodeData.source_location.end_line);
    }
  } catch (err) {
    console.warn('[WP-4] Shiki load failed, falling back to plain text:', err.message);
    codeArea.innerHTML = `<pre class="wp4-code-pre"><code class="wp4-code-block">${_escapeHtml(code)}</code></pre>`;
    _addLineNumbers(codeArea, code);
  }
}

/* ── CodeMirror 6 lazy loader ── */

async function _loadAndRenderCodeMirror(code, nodeData) {
  const panel = _getEditorPanel();
  if (!panel) return;

  const editorArea = panel.querySelector('.wp4-editor-area');
  const fileLabel = panel.querySelector('.wp4-editor-file-label');
  const badge = panel.querySelector('.wp4-editor-badge');

  // Update header
  if (fileLabel) fileLabel.textContent = nodeData?.label || nodeData?.id || 'Code';
  if (badge) { badge.textContent = 'EDIT'; badge.className = 'wp4-code-badge wp4-badge-edit'; }

  if (!editorArea) return;

  editorArea.innerHTML = '<div class="wp4-code-loading">Loading editor...</div>';

  if (!code || code === '// No source available') {
    editorArea.innerHTML = '<div class="wp4-code-loading">No source available for editing.</div>';
    return;
  }

  try {
    // Lazy load CodeMirror 6 modules via CDN
    if (!_codeMirrorLoaded) {
      const [
        { EditorView, basicSetup },
        { javascript },
        { python },
        { oneDark },
      ] = await Promise.all([
        import('https://esm.sh/@codemirror/basic-setup@0.20.0'),
        import('https://esm.sh/@codemirror/lang-javascript@6.2.0'),
        import('https://esm.sh/@codemirror/lang-python@6.1.0'),
        import('https://esm.sh/@codemirror/theme-one-dark@6.1.0'),
      ]);
      // Store loaded modules
      _codeMirrorLoaded = { EditorView, basicSetup, javascript, python, oneDark };
    }

    const { EditorView, basicSetup, javascript, python, oneDark } = _codeMirrorLoaded;

    editorArea.innerHTML = '';

    // Detect language
    const lang = _detectLanguage(nodeData);
    const langExtension = lang === 'python' ? python() : javascript();

    // Build extensions
    const extensions = [
      basicSetup,
      langExtension,
      oneDark,
      EditorView.lineWrapping,
      EditorView.updateListener.of((update) => {
        if (update.docChanged) {
          // Track modifications
          const modLabel = panel.querySelector('.wp4-editor-modified');
          if (modLabel) modLabel.textContent = '* unsaved changes';
        }
      }),
    ];

    _codeMirrorView = new EditorView({
      doc: code,
      extensions,
      parent: editorArea,
    });

    // Wire save shortcut
    _wireEditorShortcuts(panel, nodeData);

  } catch (err) {
    console.warn('[WP-4] CodeMirror load failed, falling back to textarea:', err.message);
    editorArea.innerHTML = `<textarea class="wp4-editor-fallback" spellcheck="false">${_escapeHtml(code)}</textarea>`;
  }
}

function _wireEditorShortcuts(panel, nodeData) {
  const saveBtn = panel.querySelector('.wp4-editor-save');
  const formatBtn = panel.querySelector('.wp4-editor-format');
  const copyBtn = panel.querySelector('.wp4-editor-copy');

  if (saveBtn) {
    saveBtn.addEventListener('click', () => {
      if (_codeMirrorView) {
        const content = _codeMirrorView.state.doc.toString();
        console.log('[WP-4] Save requested:', nodeData?.id, content.length, 'chars');
        // Dispatch save event for external handlers
        window.dispatchEvent(new CustomEvent('wp4-code-save', {
          detail: { nodeId: nodeData?.id, content },
        }));
        const modLabel = panel.querySelector('.wp4-editor-modified');
        if (modLabel) modLabel.textContent = '';
      }
    });
  }

  if (copyBtn) {
    copyBtn.addEventListener('click', () => {
      if (_codeMirrorView) {
        const content = _codeMirrorView.state.doc.toString();
        navigator.clipboard.writeText(content).catch(console.warn);
      }
    });
  }
}

/* ── Utility helpers ── */

function _getCodeContent(nodeData) {
  if (!nodeData) return '// No source available';

  // Try source_content field
  if (nodeData.source_content) return nodeData.source_content;

  // Try code field
  if (nodeData.code) return nodeData.code;

  // Try fetching from data cache (will be populated by data-cache.js prefetch)
  if (nodeData.source_location?.file) {
    return `// Source: ${nodeData.source_location.file}\n// Lines ${nodeData.source_location.start_line}-${nodeData.source_location.end_line}\n// Connect a Project Graph server to view source code.`;
  }

  return '// No source available';
}

function _detectLanguage(nodeData) {
  if (!nodeData) return 'javascript';
  const file = nodeData.file || nodeData.source_location?.file || nodeData.label || '';
  if (file.endsWith('.py')) return 'python';
  if (file.endsWith('.ts') || file.endsWith('.tsx')) return 'typescript';
  if (file.endsWith('.js') || file.endsWith('.jsx')) return 'javascript';
  if (file.endsWith('.rs')) return 'rust';
  if (file.endsWith('.go')) return 'go';
  if (file.endsWith('.css')) return 'css';
  if (file.endsWith('.html')) return 'html';
  if (file.endsWith('.yaml') || file.endsWith('.yml')) return 'yaml';
  if (file.endsWith('.json')) return 'json';
  return 'javascript';
}

function _getShikiTheme() {
  const isDark = document.body.classList.contains('dark') ||
    document.documentElement.getAttribute('data-theme') === 'dark';
  return isDark ? 'github-dark' : 'github-light';
}

function _getNodeColor(child) {
  const colors = {
    source: 0x34d399,
    layer: 0x6b8fff,
    module: 0x9b7cff,
    consumer: 0x5eead4,
  };
  const group = child.g || child.group || 'module';
  return colors[group] || 0x9b7cff;
}

function _getSymbolGeometry(type) {
  switch (type) {
    case 'class': return new T.BoxGeometry(1.2, 1.2, 1.2);
    case 'function': return new T.SphereGeometry(0.6, 16, 16);
    case 'enum': return new T.OctahedronGeometry(0.6);
    case 'constant': return new T.TetrahedronGeometry(0.6);
    default: return new T.SphereGeometry(0.5, 12, 12);
  }
}

function _getSymbolColor(type) {
  switch (type) {
    case 'class': return 0x6b8fff;     // blue
    case 'function': return 0x34d399;  // green
    case 'enum': return 0xf97316;      // orange
    case 'constant': return 0xfbbf24;  // amber
    default: return 0x9b7cff;          // purple
  }
}

function _animateOpacity(material, from, to, duration, delay = 0) {
  const startTime = performance.now() + delay;

  function step() {
    const elapsed = performance.now() - startTime;
    if (elapsed < 0) { requestAnimationFrame(step); return; }
    const t = Math.min(elapsed / duration, 1);
    const ease = 1 - Math.pow(1 - t, 3); // easeOutCubic
    material.opacity = from + (to - from) * ease;
    if (t < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

function _escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function _addLineNumbers(container, code) {
  const lines = code.split('\n');
  const pre = container.querySelector('pre');
  if (!pre) return;

  // Wrap existing content
  const codeEl = pre.querySelector('code') || pre;
  const wrapper = document.createElement('div');
  wrapper.className = 'wp4-line-wrapper';

  const gutterEl = document.createElement('div');
  gutterEl.className = 'wp4-line-gutter';
  gutterEl.innerHTML = lines.map((_, i) =>
    `<span class="wp4-line-num">${i + 1}</span>`
  ).join('\n');

  wrapper.appendChild(gutterEl);

  // Move code content into wrapper
  const codeWrapper = document.createElement('div');
  codeWrapper.className = 'wp4-line-code';
  while (pre.firstChild) codeWrapper.appendChild(pre.firstChild);
  wrapper.appendChild(codeWrapper);

  pre.appendChild(wrapper);
}

function _highlightLineRange(container, startLine, endLine) {
  if (!startLine || !endLine) return;
  const lineNums = container.querySelectorAll('.wp4-line-num');
  lineNums.forEach(el => {
    const num = parseInt(el.textContent, 10);
    if (num >= startLine && num <= endLine) {
      el.classList.add('wp4-line-highlighted');
    }
  });
}

function _drawChildEdges(group, children, edges, cols, spacing, count) {
  if (!edges || !edges.length) return;

  const posMap = new Map();
  children.forEach((child, i) => {
    const row = Math.floor(i / cols);
    const col = i % cols;
    const x = (col - (cols - 1) / 2) * spacing;
    const z = (row - (Math.ceil(count / cols) - 1) / 2) * spacing;
    posMap.set(child.id || child, { x, y: 1, z });
  });

  const material = new T.LineBasicMaterial({ color: 0x6b8fff, transparent: true, opacity: 0.4 });

  for (const edge of edges) {
    const fromId = edge.f || edge.from;
    const toId = edge.t || edge.to;
    const fromPos = posMap.get(fromId);
    const toPos = posMap.get(toId);
    if (!fromPos || !toPos) continue;

    const points = [
      new T.Vector3(fromPos.x, fromPos.y, fromPos.z),
      new T.Vector3(toPos.x, toPos.y, toPos.z),
    ];
    const geometry = new T.BufferGeometry().setFromPoints(points);
    const line = new T.Line(geometry, material);
    group.add(line);
  }
}
