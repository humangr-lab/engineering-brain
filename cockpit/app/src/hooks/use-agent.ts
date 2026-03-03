import { useState, useCallback, useRef, useEffect } from "react";
import {
  initProvider,
  isConfigured,
  getProvider,
  getMaskedKey,
  setApiKey,
  chat,
  type Message,
  type ProviderName,
} from "@/lib/agent/provider";
import {
  getToolsForAnthropic,
  getToolsForOpenAI,
  executeTool,
  type ToolContext,
} from "@/lib/agent/tools";
import type { Node, Edge } from "@/lib/api";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  toolName?: string;
  toolStatus?: "pending" | "complete" | "error";
  toolResult?: unknown;
  timestamp: number;
}

const SUGGESTIONS = [
  "What does this system do?",
  "Find the most connected node",
  "Explain the architecture",
];

function uid() {
  return Math.random().toString(36).slice(2, 10);
}

export function useAgent(nodes: Node[], edges: Edge[]) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [configured, setConfigured] = useState(false);
  const [provider, setProvider] = useState<ProviderName | null>(null);
  const [maskedKey, setMaskedKey] = useState<string | null>(null);

  const controllerRef = useRef<AbortController | null>(null);
  const historyRef = useRef<Message[]>([]);
  const streamTextRef = useRef("");

  // Initialize provider on mount
  useEffect(() => {
    initProvider();
    setConfigured(isConfigured());
    setProvider(getProvider());
    setMaskedKey(getMaskedKey());
  }, []);

  const toolCtx: ToolContext = {
    nodes,
    edges,
  };

  const configureKey = useCallback((key: string) => {
    setApiKey(key);
    setConfigured(isConfigured());
    setProvider(getProvider());
    setMaskedKey(getMaskedKey());
  }, []);

  const clearKey = useCallback(() => {
    setApiKey(null);
    setConfigured(false);
    setProvider(null);
    setMaskedKey(null);
  }, []);

  const buildSystemPrompt = useCallback(() => {
    const nodeCount = nodes.length;
    const edgeCount = edges.length;
    const layers = new Set(nodes.map((n) => n.layerName));
    const techs = new Set(nodes.flatMap((n) => n.technologies || []));

    return `You are the Ontology Map Agent — an AI assistant that helps users understand and navigate their knowledge graph.

Current graph: ${nodeCount} nodes, ${edgeCount} edges.
Layers: ${[...layers].join(", ") || "none"}.
Technologies: ${[...techs].slice(0, 20).join(", ") || "none"}.

You have tools to search, navigate, highlight, inspect nodes, explore subgraphs, and compute metrics.
Use tools proactively when the user asks about the graph. Be concise and helpful.
When showing results, reference node IDs so the user can click them.`;
  }, [nodes, edges]);

  const sendMessage = useCallback(
    async (text: string) => {
      if (!text.trim() || isStreaming) return;

      // Initialize history with system prompt if fresh
      if (historyRef.current.length === 0) {
        historyRef.current.push({
          role: "system",
          content: buildSystemPrompt(),
        });
      }

      // Add user message
      const userMsg: ChatMessage = {
        id: uid(),
        role: "user",
        content: text,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, userMsg]);
      historyRef.current.push({ role: "user", content: text });

      setIsStreaming(true);
      streamTextRef.current = "";

      const currentProvider = getProvider();
      const tools =
        currentProvider === "anthropic"
          ? getToolsForAnthropic()
          : getToolsForOpenAI();

      // Create assistant message placeholder
      const assistantId = uid();
      const assistantMsg: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, assistantMsg]);

      let toolCalls: { id: string; name: string; input: string }[] = [];
      let currentToolCallId = "";
      let currentToolInput = "";

      const controller = await chat(historyRef.current, tools, {
        onStream: (event: unknown) => {
          const evt = event as Record<string, unknown>;

          // Anthropic format
          if (evt.type === "content_block_delta") {
            const delta = evt.delta as Record<string, unknown>;
            if (delta.type === "text_delta") {
              streamTextRef.current += delta.text as string;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, content: streamTextRef.current }
                    : m,
                ),
              );
            }
            if (delta.type === "input_json_delta") {
              currentToolInput += (delta.partial_json as string) || "";
            }
          }

          if (evt.type === "content_block_start") {
            const block = evt.content_block as Record<string, unknown>;
            if (block.type === "tool_use") {
              currentToolCallId = block.id as string;
              currentToolInput = "";
              const toolMsg: ChatMessage = {
                id: uid(),
                role: "tool",
                content: "",
                toolName: block.name as string,
                toolStatus: "pending",
                timestamp: Date.now(),
              };
              setMessages((prev) => [...prev, toolMsg]);
            }
          }

          if (evt.type === "content_block_stop") {
            if (currentToolCallId && currentToolInput) {
              try {
                const parsed = JSON.parse(currentToolInput);
                toolCalls.push({
                  id: currentToolCallId,
                  name:
                    toolCalls.length > 0
                      ? toolCalls[toolCalls.length - 1].name
                      : "",
                  input: currentToolInput,
                });
                // Execute tool
                const result = executeTool(
                  getToolName(currentToolCallId),
                  parsed,
                  toolCtx,
                );
                setMessages((prev) =>
                  prev.map((m) =>
                    m.toolStatus === "pending" &&
                    m.toolName === getToolName(currentToolCallId)
                      ? { ...m, toolStatus: "complete", toolResult: result }
                      : m,
                  ),
                );
              } catch {
                // parse error
              }
              currentToolCallId = "";
              currentToolInput = "";
            }
          }

          // OpenAI format
          if (evt.choices) {
            const choices = evt.choices as {
              delta?: { content?: string; tool_calls?: unknown[] };
            }[];
            const delta = choices[0]?.delta;
            if (delta?.content) {
              streamTextRef.current += delta.content;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, content: streamTextRef.current }
                    : m,
                ),
              );
            }
          }
        },
        onError: (err) => {
          setMessages((prev) => [
            ...prev,
            {
              id: uid(),
              role: "assistant",
              content: `Error: ${err.message}`,
              timestamp: Date.now(),
            },
          ]);
          setIsStreaming(false);
        },
        onDone: () => {
          if (streamTextRef.current) {
            historyRef.current.push({
              role: "assistant",
              content: streamTextRef.current,
            });
          }
          setIsStreaming(false);
        },
      });

      controllerRef.current = controller;

      // Helper to get tool name from pending messages
      function getToolName(toolCallId: string): string {
        // Look at the most recent pending tool message
        const msgs = messages;
        for (let i = msgs.length - 1; i >= 0; i--) {
          if (msgs[i].toolStatus === "pending" && msgs[i].toolName) {
            return msgs[i].toolName!;
          }
        }
        void toolCallId;
        return "unknown";
      }
    },
    [isStreaming, buildSystemPrompt, toolCtx, messages],
  );

  const stopStreaming = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    setIsStreaming(false);
  }, []);

  const clearChat = useCallback(() => {
    historyRef.current = [];
    setMessages([]);
    stopStreaming();
  }, [stopStreaming]);

  return {
    messages,
    isStreaming,
    configured,
    provider,
    maskedKey,
    suggestions: SUGGESTIONS,
    sendMessage,
    stopStreaming,
    clearChat,
    configureKey,
    clearKey,
  };
}
