/* ═══════════════ WP-6: PROVIDER — BYOK LLM provider abstraction ═══════════════
   Supports Anthropic (Claude) and OpenAI (GPT-4) via direct browser fetch.
   Key stored in localStorage. Provider auto-detected from key prefix.
   Phase 1: no backend proxy, browser-direct only.
   ════════════════════════════════════════════════════════════════════════════ */

const STORAGE_KEY = 'ontology-cockpit-api-key';
const STORAGE_PROVIDER = 'ontology-cockpit-provider';

const ANTHROPIC_API = 'https://api.anthropic.com/v1/messages';
const OPENAI_API = 'https://api.openai.com/v1/chat/completions';

const ANTHROPIC_MODEL = 'claude-sonnet-4-20250514';
const OPENAI_MODEL = 'gpt-4o';

let _apiKey = null;
let _provider = null; // 'anthropic' | 'openai'
let _keyModalEl = null;
let _onConfigureCallback = null;

/**
 * Detect provider from API key prefix.
 * @param {string} key
 * @returns {'anthropic'|'openai'|null}
 */
function _detectProvider(key) {
  if (!key) return null;
  if (key.startsWith('sk-ant-')) return 'anthropic';
  if (key.startsWith('sk-')) return 'openai';
  // Fallback: try anthropic for any other key format
  return 'anthropic';
}

/**
 * Initialize the provider system. Loads stored key from localStorage.
 */
export function initProvider() {
  try {
    _apiKey = localStorage.getItem(STORAGE_KEY) || null;
    _provider = localStorage.getItem(STORAGE_PROVIDER) || _detectProvider(_apiKey);
  } catch (e) {
    console.warn('[WP-6] Could not read localStorage:', e);
    _apiKey = null;
    _provider = null;
  }
  _buildKeyModal();
}

/**
 * Check if an API key is configured.
 * @returns {boolean}
 */
export function isConfigured() {
  return !!_apiKey;
}

/**
 * Get the current provider name.
 * @returns {'anthropic'|'openai'|null}
 */
export function getProvider() {
  return _provider;
}

/**
 * Get the configured API key (for display — first/last 4 chars).
 * @returns {string|null} Masked key like "sk-a...xYzW"
 */
export function getMaskedKey() {
  if (!_apiKey) return null;
  if (_apiKey.length < 12) return '****';
  return _apiKey.slice(0, 5) + '...' + _apiKey.slice(-4);
}

/**
 * Set the API key and persist to localStorage.
 * @param {string} key
 */
export function setApiKey(key) {
  _apiKey = key || null;
  _provider = _detectProvider(_apiKey);
  try {
    if (_apiKey) {
      localStorage.setItem(STORAGE_KEY, _apiKey);
      localStorage.setItem(STORAGE_PROVIDER, _provider);
    } else {
      localStorage.removeItem(STORAGE_KEY);
      localStorage.removeItem(STORAGE_PROVIDER);
    }
  } catch (e) {
    console.warn('[WP-6] Could not write localStorage:', e);
  }
}

/**
 * Get the raw API key (for API calls only — never display).
 * @returns {string|null}
 */
export function getApiKey() {
  return _apiKey;
}

/**
 * Clear the stored API key.
 */
export function clearApiKey() {
  setApiKey(null);
}

/**
 * Send a chat completion request with streaming.
 * @param {Array} messages - Conversation history [{role, content}]
 * @param {Array} tools - Tool definitions (provider-formatted)
 * @param {object} callbacks - { onStream(event), onError(err), onDone() }
 * @returns {Promise<AbortController>} controller to abort the stream
 */
export async function chat(messages, tools, callbacks) {
  if (!_apiKey || !_provider) {
    callbacks.onError?.(new Error('No API key configured'));
    return null;
  }

  const controller = new AbortController();

  try {
    if (_provider === 'anthropic') {
      await _chatAnthropic(messages, tools, callbacks, controller);
    } else if (_provider === 'openai') {
      await _chatOpenAI(messages, tools, callbacks, controller);
    } else {
      callbacks.onError?.(new Error(`Unknown provider: ${_provider}`));
    }
  } catch (e) {
    if (e.name !== 'AbortError') {
      callbacks.onError?.(e);
    }
  }

  return controller;
}

/* ── Anthropic Streaming ── */

async function _chatAnthropic(messages, tools, callbacks, controller) {
  // Anthropic format: separate system message from conversation
  const systemMsg = messages.find(m => m.role === 'system');
  const convMessages = messages.filter(m => m.role !== 'system');

  const body = {
    model: ANTHROPIC_MODEL,
    max_tokens: 4096,
    stream: true,
    messages: convMessages,
  };

  if (systemMsg) {
    body.system = systemMsg.content;
  }

  if (tools && tools.length) {
    body.tools = tools;
  }

  const response = await fetch(ANTHROPIC_API, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': _apiKey,
      'anthropic-version': '2023-06-01',
      'anthropic-dangerous-direct-browser-access': 'true',
    },
    body: JSON.stringify(body),
    signal: controller.signal,
  });

  if (!response.ok) {
    const errorBody = await response.text();
    let errorMsg = `Anthropic API error: ${response.status}`;
    try {
      const parsed = JSON.parse(errorBody);
      errorMsg = parsed.error?.message || errorMsg;
    } catch { /* ignore parse errors */ }
    throw new Error(errorMsg);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6).trim();
        if (data === '[DONE]') {
          callbacks.onDone?.();
          return;
        }
        try {
          const event = JSON.parse(data);
          callbacks.onStream?.(event);
        } catch { /* skip malformed lines */ }
      }
    }
  }

  callbacks.onDone?.();
}

/* ── OpenAI Streaming ── */

async function _chatOpenAI(messages, tools, callbacks, controller) {
  const body = {
    model: OPENAI_MODEL,
    stream: true,
    messages: messages.map(m => ({
      role: m.role,
      content: m.content,
      ...(m.tool_call_id ? { tool_call_id: m.tool_call_id } : {}),
      ...(m.tool_calls ? { tool_calls: m.tool_calls } : {}),
    })),
  };

  if (tools && tools.length) {
    body.tools = tools;
  }

  const response = await fetch(OPENAI_API, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${_apiKey}`,
    },
    body: JSON.stringify(body),
    signal: controller.signal,
  });

  if (!response.ok) {
    const errorBody = await response.text();
    let errorMsg = `OpenAI API error: ${response.status}`;
    try {
      const parsed = JSON.parse(errorBody);
      errorMsg = parsed.error?.message || errorMsg;
    } catch { /* ignore parse errors */ }
    throw new Error(errorMsg);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6).trim();
        if (data === '[DONE]') {
          callbacks.onDone?.();
          return;
        }
        try {
          const event = JSON.parse(data);
          callbacks.onStream?.(event);
        } catch { /* skip malformed lines */ }
      }
    }
  }

  callbacks.onDone?.();
}

/* ── Key Configuration Modal ── */

function _buildKeyModal() {
  if (document.getElementById('agentKeyModalOv')) return;

  const ov = document.createElement('div');
  ov.id = 'agentKeyModalOv';
  ov.className = 'agent-key-modal-ov';
  ov.innerHTML = `
    <div class="agent-key-modal">
      <div class="agent-key-modal-title">Configure API Key</div>
      <div class="agent-key-modal-desc">
        Enter your API key to enable the AI agent. Your key is stored locally in your browser and sent directly to the provider API. It is never sent to any other server.
      </div>
      <input type="password" class="agent-key-input" id="agentKeyInput"
             placeholder="sk-ant-... or sk-..."
             autocomplete="off" spellcheck="false">
      <div class="agent-key-modal-hint" id="agentKeyHint">
        Supports: Anthropic (sk-ant-...) and OpenAI (sk-...)
      </div>
      <div class="agent-key-modal-actions">
        <button class="agent-key-modal-cancel" id="agentKeyCancel">Cancel</button>
        <button class="agent-key-modal-save" id="agentKeySave" disabled>Save Key</button>
      </div>
    </div>
  `;
  document.body.appendChild(ov);
  _keyModalEl = ov;

  // Wire events
  const input = document.getElementById('agentKeyInput');
  const saveBtn = document.getElementById('agentKeySave');
  const cancelBtn = document.getElementById('agentKeyCancel');
  const hint = document.getElementById('agentKeyHint');

  input.addEventListener('input', () => {
    const val = input.value.trim();
    const detected = _detectProvider(val);
    saveBtn.disabled = !val;
    if (val && detected === 'anthropic') {
      hint.textContent = 'Detected: Anthropic (Claude)';
    } else if (val && detected === 'openai') {
      hint.textContent = 'Detected: OpenAI (GPT-4)';
    } else if (val) {
      hint.textContent = 'Will attempt as Anthropic key';
    } else {
      hint.textContent = 'Supports: Anthropic (sk-ant-...) and OpenAI (sk-...)';
    }
  });

  saveBtn.addEventListener('click', () => {
    const val = input.value.trim();
    if (val) {
      setApiKey(val);
      closeKeyModal();
      if (_onConfigureCallback) _onConfigureCallback();
    }
  });

  cancelBtn.addEventListener('click', () => {
    closeKeyModal();
  });

  // Click outside to close
  ov.addEventListener('click', (e) => {
    if (e.target === ov) closeKeyModal();
  });

  // Enter key to save
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && input.value.trim()) {
      saveBtn.click();
    } else if (e.key === 'Escape') {
      closeKeyModal();
    }
  });
}

/**
 * Open the API key configuration modal.
 * @param {Function} [onConfigure] - Called after key is saved
 */
export function openKeyModal(onConfigure) {
  _onConfigureCallback = onConfigure || null;
  if (!_keyModalEl) _buildKeyModal();
  const input = document.getElementById('agentKeyInput');
  if (input) input.value = '';
  _keyModalEl.classList.add('open');
  requestAnimationFrame(() => input?.focus());
}

/**
 * Close the API key configuration modal.
 */
export function closeKeyModal() {
  if (_keyModalEl) _keyModalEl.classList.remove('open');
  _onConfigureCallback = null;
}
