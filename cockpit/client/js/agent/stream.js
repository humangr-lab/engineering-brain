/* ═══════════════ WP-6: STREAM — SSE response handler for Anthropic & OpenAI ═══════════════
   Parses streaming responses from both providers.
   Handles text deltas, tool_use blocks, and message lifecycle.
   Executes tool calls via executeTool() and feeds results back into the conversation.
   ════════════════════════════════════════════════════════════════════════════════════════ */

import { executeTool } from './tools.js';

/**
 * Handle an Anthropic streaming response.
 * Parses SSE events: content_block_start, content_block_delta, content_block_stop,
 * message_start, message_delta, message_stop.
 *
 * @param {object} callbacks
 *   - onText(text): incremental text chunk
 *   - onToolStart(toolCallId, toolName): tool call started
 *   - onToolResult(toolCallId, toolName, result): tool call completed
 *   - onToolError(toolCallId, toolName, error): tool call failed
 *   - onDone(stopReason): message complete
 *   - onError(error): stream error
 * @returns {{ processEvent(event): void, getToolResults(): Array }} handler object
 */
export function createAnthropicHandler(callbacks) {
  let _currentBlockType = null;
  let _currentBlockIndex = -1;
  let _currentToolName = null;
  let _currentToolId = null;
  let _currentToolInput = '';
  const _toolResults = []; // [{tool_use_id, content}] for feeding back

  function processEvent(event) {
    const type = event.type;

    switch (type) {
      case 'message_start':
        // Message metadata available in event.message
        break;

      case 'content_block_start': {
        _currentBlockIndex = event.index ?? -1;
        const block = event.content_block;
        if (block?.type === 'text') {
          _currentBlockType = 'text';
        } else if (block?.type === 'tool_use') {
          _currentBlockType = 'tool_use';
          _currentToolName = block.name;
          _currentToolId = block.id;
          _currentToolInput = '';
          callbacks.onToolStart?.(_currentToolId, _currentToolName);
        }
        break;
      }

      case 'content_block_delta': {
        const delta = event.delta;
        if (_currentBlockType === 'text' && delta?.type === 'text_delta') {
          callbacks.onText?.(delta.text);
        } else if (_currentBlockType === 'tool_use' && delta?.type === 'input_json_delta') {
          _currentToolInput += delta.partial_json || '';
        }
        break;
      }

      case 'content_block_stop': {
        if (_currentBlockType === 'tool_use' && _currentToolName && _currentToolId) {
          // Parse accumulated tool input and execute
          let args = {};
          try {
            args = _currentToolInput ? JSON.parse(_currentToolInput) : {};
          } catch (e) {
            console.warn('[WP-6] Failed to parse tool input:', _currentToolInput, e);
          }

          try {
            const result = executeTool(_currentToolName, args);
            _toolResults.push({
              type: 'tool_result',
              tool_use_id: _currentToolId,
              content: JSON.stringify(result),
            });
            callbacks.onToolResult?.(_currentToolId, _currentToolName, result);
          } catch (e) {
            _toolResults.push({
              type: 'tool_result',
              tool_use_id: _currentToolId,
              content: JSON.stringify({ error: e.message }),
              is_error: true,
            });
            callbacks.onToolError?.(_currentToolId, _currentToolName, e);
          }
        }
        _currentBlockType = null;
        _currentToolName = null;
        _currentToolId = null;
        _currentToolInput = '';
        break;
      }

      case 'message_delta': {
        // event.delta may contain stop_reason
        const stopReason = event.delta?.stop_reason;
        if (stopReason) {
          callbacks.onDone?.(stopReason);
        }
        break;
      }

      case 'message_stop':
        // Final event -- message is complete
        break;

      case 'error':
        callbacks.onError?.(new Error(event.error?.message || 'Stream error'));
        break;

      case 'ping':
        // Keep-alive, ignore
        break;
    }
  }

  return {
    processEvent,
    /**
     * Get accumulated tool results to feed back to the API for continuation.
     * @returns {Array} tool result messages
     */
    getToolResults() {
      return [..._toolResults];
    },
    /**
     * Check if the last message stopped because it needs tool results.
     * @returns {boolean}
     */
    needsToolResponse() {
      return _toolResults.length > 0;
    },
    /**
     * Clear tool results after they have been sent back.
     */
    clearToolResults() {
      _toolResults.length = 0;
    },
  };
}

/**
 * Handle an OpenAI streaming response.
 * Parses SSE chunks: chat.completion.chunk events with delta objects.
 *
 * @param {object} callbacks - Same as Anthropic handler
 * @returns {{ processEvent(event): void, getToolResults(): Array }} handler object
 */
export function createOpenAIHandler(callbacks) {
  const _toolCalls = {}; // { index: { id, name, arguments } }
  const _toolResults = [];

  function processEvent(event) {
    if (!event.choices || !event.choices.length) return;

    const choice = event.choices[0];
    const delta = choice.delta;
    const finishReason = choice.finish_reason;

    if (delta) {
      // Text content
      if (delta.content) {
        callbacks.onText?.(delta.content);
      }

      // Tool calls
      if (delta.tool_calls) {
        for (const tc of delta.tool_calls) {
          const idx = tc.index ?? 0;
          if (!_toolCalls[idx]) {
            _toolCalls[idx] = { id: '', name: '', arguments: '' };
          }
          if (tc.id) _toolCalls[idx].id = tc.id;
          if (tc.function?.name) {
            _toolCalls[idx].name = tc.function.name;
            callbacks.onToolStart?.(_toolCalls[idx].id, _toolCalls[idx].name);
          }
          if (tc.function?.arguments) {
            _toolCalls[idx].arguments += tc.function.arguments;
          }
        }
      }
    }

    // Finish
    if (finishReason === 'tool_calls' || finishReason === 'stop') {
      // Execute any pending tool calls
      if (finishReason === 'tool_calls') {
        for (const tc of Object.values(_toolCalls)) {
          if (!tc.name) continue;
          let args = {};
          try {
            args = tc.arguments ? JSON.parse(tc.arguments) : {};
          } catch (e) {
            console.warn('[WP-6] Failed to parse OpenAI tool args:', tc.arguments, e);
          }

          try {
            const result = executeTool(tc.name, args);
            _toolResults.push({
              role: 'tool',
              tool_call_id: tc.id,
              content: JSON.stringify(result),
            });
            callbacks.onToolResult?.(tc.id, tc.name, result);
          } catch (e) {
            _toolResults.push({
              role: 'tool',
              tool_call_id: tc.id,
              content: JSON.stringify({ error: e.message }),
            });
            callbacks.onToolError?.(tc.id, tc.name, e);
          }
        }
      }
      callbacks.onDone?.(finishReason);
    }
  }

  return {
    processEvent,
    getToolResults() {
      return [..._toolResults];
    },
    /**
     * Get the assistant message with tool_calls for conversation history.
     * @returns {object|null} assistant message with tool_calls
     */
    getAssistantToolCallMessage() {
      const calls = Object.values(_toolCalls).filter(tc => tc.name);
      if (!calls.length) return null;
      return {
        role: 'assistant',
        content: null,
        tool_calls: calls.map(tc => ({
          id: tc.id,
          type: 'function',
          function: { name: tc.name, arguments: tc.arguments },
        })),
      };
    },
    needsToolResponse() {
      return _toolResults.length > 0;
    },
    clearToolResults() {
      _toolResults.length = 0;
      for (const key of Object.keys(_toolCalls)) delete _toolCalls[key];
    },
  };
}
