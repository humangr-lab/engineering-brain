/* ═══════════════ WP-6: CHAT PANEL — Right sidebar AI conversation ═══════════════
   400px collapsible right sidebar with message bubbles, tool cards,
   suggestion chips, streaming text, and input area.
   Orchestrates provider.js, tools.js, stream.js, and system-prompt.js.
   ════════════════════════════════════════════════════════════════════════════════ */

import { state, subscribe } from '../state.js';
import { initProvider, isConfigured, getProvider, openKeyModal, chat } from './provider.js';
import { getToolsForAnthropic, getToolsForOpenAI, wireActionCancellation } from './tools.js';
import { createAnthropicHandler, createOpenAIHandler } from './stream.js';
import { buildSystemPrompt } from './system-prompt.js';

/* ── DOM References ── */
let _panel = null;
let _toggle = null;
let _messagesEl = null;
let _inputEl = null;
let _sendBtn = null;
let _providerBadge = null;
let _providerDot = null;

/* ── State ── */
let _conversationHistory = []; // Full conversation for API calls
let _isStreaming = false;
let _currentController = null; // AbortController for current stream
let _currentAgentBubble = null; // DOM element for current streaming message

const SUGGESTIONS = [
  'What does this system do?',
  'Find the most connected node',
  'Explain the architecture',
];

/* ── Initialization ── */

/**
 * Initialize the chat panel system. Call once during boot.
 * Creates DOM, wires events, initializes provider.
 */
export function initChatPanel() {
  initProvider();
  _buildDOM();
  _wireEvents();
  wireActionCancellation();

  // Subscribe to agentOpen state
  subscribe('agentOpen', (isOpen) => {
    if (isOpen) _openPanel();
    else _closePanel();
  });

  // Update provider badge when key changes
  _updateProviderBadge();

  console.log('[WP-6] Chat panel initialized, provider:', getProvider() || 'none');
}

/* ── DOM Construction ── */

function _buildDOM() {
  // Toggle button
  _toggle = document.createElement('button');
  _toggle.className = 'agent-toggle';
  _toggle.id = 'agentToggle';
  _toggle.setAttribute('aria-label', 'Toggle AI Chat');
  _toggle.setAttribute('title', 'Toggle AI Chat');
  _toggle.innerHTML = '\u{1F4AC}';
  document.body.appendChild(_toggle);

  // Panel
  _panel = document.createElement('div');
  _panel.className = 'agent-panel';
  _panel.id = 'agentPanel';
  _panel.setAttribute('role', 'complementary');
  _panel.setAttribute('aria-label', 'AI Chat Panel');

  _panel.innerHTML = `
    <div class="agent-header">
      <div class="agent-header-left">
        <div class="agent-header-title">Ontology Agent</div>
        <div class="agent-header-provider" id="agentProviderBadge">
          <span class="agent-header-dot unconfigured" id="agentProviderDot"></span>
          <span id="agentProviderText">No key configured</span>
        </div>
      </div>
      <div class="agent-header-actions">
        <button class="agent-header-btn" id="agentKeyBtn" aria-label="Configure API key" title="Configure API key">
          \u{1F511}
        </button>
        <button class="agent-header-btn" id="agentClearBtn" aria-label="Clear chat" title="Clear chat">
          \u{1F5D1}
        </button>
        <button class="agent-header-btn" id="agentCloseBtn" aria-label="Close chat panel" title="Close">
          \u2715
        </button>
      </div>
    </div>
    <div class="agent-messages" id="agentMessages"></div>
    <div class="agent-input-area">
      <textarea class="agent-input" id="agentInput"
                placeholder="Ask about the system..."
                rows="1"
                aria-label="Chat message input"></textarea>
      <button class="agent-send-btn" id="agentSendBtn" aria-label="Send message" disabled>
        \u2191
      </button>
    </div>
  `;

  document.body.appendChild(_panel);

  // Cache references
  _messagesEl = document.getElementById('agentMessages');
  _inputEl = document.getElementById('agentInput');
  _sendBtn = document.getElementById('agentSendBtn');
  _providerBadge = document.getElementById('agentProviderBadge');
  _providerDot = document.getElementById('agentProviderDot');
}

/* ── Event Wiring ── */

function _wireEvents() {
  // Toggle button
  _toggle.addEventListener('click', () => {
    state.agentOpen = !state.agentOpen;
  });

  // Close button
  document.getElementById('agentCloseBtn')?.addEventListener('click', () => {
    state.agentOpen = false;
  });

  // Key button
  document.getElementById('agentKeyBtn')?.addEventListener('click', () => {
    openKeyModal(() => {
      _updateProviderBadge();
      _renderContent();
    });
  });

  // Clear button
  document.getElementById('agentClearBtn')?.addEventListener('click', () => {
    clearChat();
  });

  // Send button
  _sendBtn.addEventListener('click', () => {
    _handleSend();
  });

  // Input: enable/disable send, auto-resize, Enter to send
  _inputEl.addEventListener('input', () => {
    _sendBtn.disabled = !_inputEl.value.trim() || _isStreaming;
    _autoResizeInput();
  });

  _inputEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (_inputEl.value.trim() && !_isStreaming) {
        _handleSend();
      }
    }
  });
}

/* ── Panel Open/Close ── */

function _openPanel() {
  _panel.classList.add('open');
  _toggle.classList.add('panel-open');
  _toggle.innerHTML = '\u{25B6}';
  _renderContent();
  requestAnimationFrame(() => {
    if (isConfigured() && _conversationHistory.length > 1) {
      _inputEl.focus();
    }
  });
}

function _closePanel() {
  _panel.classList.remove('open');
  _toggle.classList.remove('panel-open');
  _toggle.innerHTML = '\u{1F4AC}';
}

/* ── Content Rendering ── */

function _renderContent() {
  if (!isConfigured()) {
    _renderNoKeyState();
  } else if (_conversationHistory.length <= 1) {
    _renderEmptyState();
  }
  // If there are messages, they are already rendered incrementally
}

function _renderNoKeyState() {
  _messagesEl.innerHTML = `
    <div class="agent-no-key">
      <div class="agent-no-key-icon">\u{1F511}</div>
      <div class="agent-no-key-title">Configure your API key to enable the AI agent.</div>
      <div class="agent-no-key-sub">Supports: Anthropic, OpenAI</div>
      <button class="agent-no-key-btn" id="agentNoKeyBtn">Configure Key</button>
      <div class="agent-no-key-privacy">Your key stays in your browser. Never sent to us.</div>
    </div>
  `;
  document.getElementById('agentNoKeyBtn')?.addEventListener('click', () => {
    openKeyModal(() => {
      _updateProviderBadge();
      _renderContent();
    });
  });
  _inputEl.disabled = true;
  _sendBtn.disabled = true;
}

function _renderEmptyState() {
  _messagesEl.innerHTML = `
    <div class="agent-empty">
      <div class="agent-empty-icon">\u{1F4AC}</div>
      <div class="agent-empty-title">Ask me about this system</div>
      <div class="agent-empty-suggestions" id="agentSuggestions"></div>
      <div class="agent-empty-cost">Session cost: $0.00</div>
    </div>
  `;

  const suggestionsEl = document.getElementById('agentSuggestions');
  for (const suggestion of SUGGESTIONS) {
    const btn = document.createElement('button');
    btn.className = 'agent-suggestion';
    btn.textContent = suggestion;
    btn.addEventListener('click', () => {
      _inputEl.value = suggestion;
      _inputEl.disabled = false;
      _sendBtn.disabled = false;
      _handleSend();
    });
    suggestionsEl.appendChild(btn);
  }

  _inputEl.disabled = false;
  _sendBtn.disabled = true;
}

/* ── Provider Badge ── */

function _updateProviderBadge() {
  const provider = getProvider();
  const providerText = document.getElementById('agentProviderText');

  if (isConfigured() && provider) {
    const label = provider === 'anthropic' ? 'Anthropic' : 'OpenAI';
    if (providerText) providerText.textContent = `Using your ${label} key`;
    if (_providerDot) _providerDot.classList.remove('unconfigured');
  } else {
    if (providerText) providerText.textContent = 'No key configured';
    if (_providerDot) _providerDot.classList.add('unconfigured');
  }
}

/* ── Message Handling ── */

async function _handleSend() {
  const text = _inputEl.value.trim();
  if (!text || _isStreaming) return;

  // Initialize conversation with system prompt if fresh
  if (_conversationHistory.length === 0) {
    const systemPrompt = buildSystemPrompt();
    _conversationHistory.push({ role: 'system', content: systemPrompt });
  }

  // Clear empty state if present
  const emptyState = _messagesEl.querySelector('.agent-empty');
  const noKeyState = _messagesEl.querySelector('.agent-no-key');
  if (emptyState) emptyState.remove();
  if (noKeyState) noKeyState.remove();

  // Add user message
  addUserMessage(text);
  _conversationHistory.push({ role: 'user', content: text });

  // Clear input
  _inputEl.value = '';
  _inputEl.disabled = true;
  _sendBtn.disabled = true;
  _autoResizeInput();

  // Start streaming response
  await _streamResponse();
}

/**
 * Stream a response from the LLM provider.
 * Handles tool call loops: if the model returns tool_use, execute tools
 * and send results back for continuation.
 */
async function _streamResponse() {
  _isStreaming = true;
  _sendBtn.innerHTML = '\u25A0'; // Stop icon
  _sendBtn.classList.add('stop');
  _sendBtn.disabled = false;

  // Wire stop button
  const stopHandler = () => {
    if (_currentController) {
      _currentController.abort();
      _currentController = null;
    }
    _finishStreaming();
  };
  _sendBtn.addEventListener('click', stopHandler, { once: true });

  const provider = getProvider();

  // Add typing indicator
  _showTypingIndicator();

  let continueLoop = true;

  while (continueLoop) {
    continueLoop = false;
    let fullText = '';
    let handler;

    const tools = provider === 'anthropic' ? getToolsForAnthropic() : getToolsForOpenAI();

    const callbacks = {
      onText: (text) => {
        // Remove typing indicator on first text
        _hideTypingIndicator();

        fullText += text;
        if (!_currentAgentBubble) {
          _currentAgentBubble = _createAgentBubble();
        }
        _updateAgentBubbleText(_currentAgentBubble, fullText);
        _scrollToBottom();
      },
      onToolStart: (toolCallId, toolName) => {
        _hideTypingIndicator();
        addToolCard(toolName, 'pending', null);
      },
      onToolResult: (toolCallId, toolName, result) => {
        _updateLastToolCard(toolName, 'complete', result);
      },
      onToolError: (toolCallId, toolName, error) => {
        _updateLastToolCard(toolName, 'error', { error: error.message });
      },
      onDone: (stopReason) => {
        _hideTypingIndicator();
      },
      onError: (error) => {
        _hideTypingIndicator();
        _addErrorCard(error.message);
      },
    };

    if (provider === 'anthropic') {
      handler = createAnthropicHandler(callbacks);
    } else {
      handler = createOpenAIHandler(callbacks);
    }

    try {
      _currentController = await chat(
        _conversationHistory,
        tools,
        {
          onStream: (event) => handler.processEvent(event),
          onError: callbacks.onError,
          onDone: () => {
            // Check if we need to continue with tool results
            if (handler.needsToolResponse()) {
              continueLoop = true;
            }
          },
        }
      );
    } catch (e) {
      if (e.name !== 'AbortError') {
        _addErrorCard(e.message);
      }
      break;
    }

    // Wait for stream to complete by polling (stream is async)
    // The callbacks above handle all the UI updates
    // After stream completes, check if we need to send tool results back

    if (handler.needsToolResponse()) {
      // Add the assistant's message with tool calls to history
      if (provider === 'anthropic') {
        // Build the assistant message content blocks
        const contentBlocks = [];
        if (fullText) {
          contentBlocks.push({ type: 'text', text: fullText });
        }
        // Add tool_use blocks
        const toolResults = handler.getToolResults();
        for (const tr of toolResults) {
          contentBlocks.push({
            type: 'tool_use',
            id: tr.tool_use_id,
            name: '', // Will be filled from the stream
            input: {},
          });
        }
        if (contentBlocks.length) {
          _conversationHistory.push({ role: 'assistant', content: contentBlocks });
        }
        // Add tool results as user message
        _conversationHistory.push({ role: 'user', content: toolResults });
      } else {
        // OpenAI format
        const assistantMsg = handler.getAssistantToolCallMessage();
        if (assistantMsg) {
          _conversationHistory.push(assistantMsg);
        }
        const toolResults = handler.getToolResults();
        for (const tr of toolResults) {
          _conversationHistory.push(tr);
        }
      }

      handler.clearToolResults();
      _currentAgentBubble = null;
      fullText = '';
      _showTypingIndicator();
      continueLoop = true;
    } else {
      // Add the final text to conversation history
      if (fullText) {
        _conversationHistory.push({ role: 'assistant', content: fullText });
      }
      continueLoop = false;
    }
  }

  _finishStreaming();
}

function _finishStreaming() {
  _isStreaming = false;
  _currentController = null;
  _currentAgentBubble = null;
  _hideTypingIndicator();
  _inputEl.disabled = false;
  _sendBtn.innerHTML = '\u2191';
  _sendBtn.classList.remove('stop');
  _sendBtn.disabled = !_inputEl.value.trim();
  _inputEl.focus();
}

/* ── Message DOM Helpers ── */

/**
 * Add a user message bubble to the chat.
 * @param {string} text
 */
export function addUserMessage(text) {
  const el = document.createElement('div');
  el.className = 'agent-msg-user';
  el.textContent = text;
  _messagesEl.appendChild(el);
  _scrollToBottom();
}

/**
 * Add a complete agent message bubble.
 * @param {string} text
 */
export function addAgentMessage(text) {
  const el = _createAgentBubble();
  _updateAgentBubbleText(el, text);
  _scrollToBottom();
}

function _createAgentBubble() {
  const el = document.createElement('div');
  el.className = 'agent-msg-agent';
  el.innerHTML = `
    <div class="agent-msg-agent-label">
      <span class="agent-msg-agent-dot"></span>
      Agent
    </div>
    <div class="agent-msg-agent-text"></div>
  `;
  _messagesEl.appendChild(el);
  return el;
}

function _updateAgentBubbleText(bubble, text) {
  const textEl = bubble.querySelector('.agent-msg-agent-text');
  if (!textEl) return;

  // Simple markdown-like rendering: paragraphs, code, bold
  const html = _renderMarkdown(text);
  textEl.innerHTML = html;
}

function _renderMarkdown(text) {
  // Split into paragraphs
  const paragraphs = text.split('\n\n');
  return paragraphs.map(p => {
    let html = _escapeHtml(p);
    // Inline code
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    // Bold
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    // Line breaks within paragraph
    html = html.replace(/\n/g, '<br>');
    return `<p>${html}</p>`;
  }).join('');
}

function _escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

/**
 * Add a tool call card to the chat.
 * @param {string} toolName
 * @param {'pending'|'complete'|'error'} status
 * @param {object|null} result
 */
export function addToolCard(toolName, status, result) {
  const el = document.createElement('div');
  el.className = 'agent-tool-card';
  el.dataset.toolName = toolName;
  el.dataset.status = status;

  const icon = status === 'pending' ? '\u{23F3}'
    : status === 'complete' ? '\u2713'
    : '\u2717';

  const desc = _getToolDescription(toolName, status, result);

  el.innerHTML = `
    <div class="agent-tool-icon ${status}">${icon}</div>
    <div class="agent-tool-body">
      <div class="agent-tool-name">${_escapeHtml(toolName)}</div>
      <div class="agent-tool-desc">${desc}</div>
    </div>
  `;

  _messagesEl.appendChild(el);
  _scrollToBottom();
}

function _updateLastToolCard(toolName, status, result) {
  // Find the last tool card with matching name and pending status
  const cards = _messagesEl.querySelectorAll('.agent-tool-card');
  for (let i = cards.length - 1; i >= 0; i--) {
    const card = cards[i];
    if (card.dataset.toolName === toolName && card.dataset.status === 'pending') {
      card.dataset.status = status;
      const iconEl = card.querySelector('.agent-tool-icon');
      const descEl = card.querySelector('.agent-tool-desc');

      if (iconEl) {
        iconEl.className = `agent-tool-icon ${status}`;
        iconEl.textContent = status === 'complete' ? '\u2713' : '\u2717';
      }
      if (descEl) {
        descEl.innerHTML = _getToolDescription(toolName, status, result);
      }

      // If this is a metrics result, also add a metrics card
      if (status === 'complete' && toolName === 'get_metrics' && result) {
        _addMetricsCard(result);
      }
      if (status === 'complete' && toolName === 'search_nodes' && result?.results?.length) {
        descEl.innerHTML = _getToolDescription(toolName, status, result);
      }

      break;
    }
  }
}

function _getToolDescription(toolName, status, result) {
  if (status === 'pending') {
    const labels = {
      search_nodes: 'Searching...',
      navigate_to: 'Navigating...',
      highlight_nodes: 'Highlighting...',
      get_details: 'Loading details...',
      get_submap: 'Expanding submap...',
      get_metrics: 'Computing metrics...',
    };
    return labels[toolName] || 'Executing...';
  }

  if (status === 'error') {
    return `<span style="color:var(--accent-red)">Failed: ${_escapeHtml(result?.error || 'Unknown error')}</span>`;
  }

  // Complete: show summary
  if (toolName === 'search_nodes' && result?.results) {
    const names = result.results.slice(0, 5).map(r => r.label).join(', ');
    return `Found ${result.results.length} result${result.results.length !== 1 ? 's' : ''}: ${_escapeHtml(names)}${result.results.length > 5 ? '...' : ''}`;
  }
  if (toolName === 'navigate_to' && result?.success) {
    return `Navigated to ${_escapeHtml(result.label || result.node_id)}`;
  }
  if (toolName === 'highlight_nodes' && result?.highlighted) {
    return `Highlighted ${result.highlighted.length} node${result.highlighted.length !== 1 ? 's' : ''}`;
  }
  if (toolName === 'get_details' && result?.label) {
    const conns = result.connections
      ? ` (${result.connections.total_incoming} in, ${result.connections.total_outgoing} out)`
      : '';
    return `${_escapeHtml(result.label)}${conns}`;
  }
  if (toolName === 'get_submap' && result) {
    return `${result.node_count} nodes, ${result.edge_count} edges (depth ${result.depth})`;
  }
  if (toolName === 'get_metrics' && result) {
    return `${result.total_nodes} nodes, ${result.total_edges} edges, density ${result.density}`;
  }
  return 'Done';
}

function _addMetricsCard(metrics) {
  const el = document.createElement('div');
  el.className = 'agent-metrics-card';

  const items = [
    { label: 'Nodes', value: metrics.total_nodes },
    { label: 'Edges', value: metrics.total_edges },
    { label: 'Density', value: metrics.density },
    { label: 'Avg Degree', value: metrics.avg_degree },
    { label: 'Max Degree', value: metrics.max_degree },
    { label: 'Modules', value: metrics.drillable_modules },
  ];

  el.innerHTML = `
    <div class="agent-metrics-grid">
      ${items.map(item => `
        <div>
          <div class="agent-metric-label">${item.label}</div>
          <div class="agent-metric-value">${item.value}</div>
        </div>
      `).join('')}
    </div>
  `;

  _messagesEl.appendChild(el);
  _scrollToBottom();
}

function _addErrorCard(message) {
  const el = document.createElement('div');
  el.className = 'agent-error-card';
  el.innerHTML = `
    <div class="agent-error-title">API Error</div>
    <div class="agent-error-body">${_escapeHtml(message)}</div>
    <button class="agent-error-retry" id="agentRetryBtn">Retry</button>
  `;
  _messagesEl.appendChild(el);
  _scrollToBottom();

  el.querySelector('#agentRetryBtn')?.addEventListener('click', () => {
    el.remove();
    // Remove last user message from history and retry
    if (_conversationHistory.length > 1 && _conversationHistory[_conversationHistory.length - 1].role === 'user') {
      const lastMsg = _conversationHistory.pop();
      _inputEl.value = lastMsg.content || '';
      _sendBtn.disabled = false;
      _handleSend();
    }
  });
}

/* ── Typing Indicator ── */

let _typingEl = null;

function _showTypingIndicator() {
  if (_typingEl) return;
  _typingEl = document.createElement('div');
  _typingEl.className = 'agent-typing';
  _typingEl.innerHTML = `
    <div class="agent-typing-dot"></div>
    <div class="agent-typing-dot"></div>
    <div class="agent-typing-dot"></div>
  `;
  _messagesEl.appendChild(_typingEl);
  _scrollToBottom();
}

function _hideTypingIndicator() {
  if (_typingEl) {
    _typingEl.remove();
    _typingEl = null;
  }
}

/* ── Utilities ── */

function _scrollToBottom() {
  if (_messagesEl) {
    _messagesEl.scrollTop = _messagesEl.scrollHeight;
  }
}

function _autoResizeInput() {
  if (!_inputEl) return;
  _inputEl.style.height = 'auto';
  _inputEl.style.height = Math.min(_inputEl.scrollHeight, 120) + 'px';
}

/**
 * Clear all messages and reset conversation.
 */
export function clearChat() {
  _conversationHistory = [];
  _currentAgentBubble = null;
  if (_currentController) {
    _currentController.abort();
    _currentController = null;
  }
  _isStreaming = false;
  _hideTypingIndicator();
  _renderContent();
  _inputEl.disabled = !isConfigured();
  _sendBtn.disabled = true;
  _sendBtn.innerHTML = '\u2191';
  _sendBtn.classList.remove('stop');
}
