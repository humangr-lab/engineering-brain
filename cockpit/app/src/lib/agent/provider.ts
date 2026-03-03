/**
 * BYOK LLM Provider — browser-direct Anthropic/OpenAI streaming.
 * Keys stored in localStorage, never sent anywhere else.
 */

const STORAGE_KEY = "ontology-map-api-key";
const STORAGE_PROVIDER = "ontology-map-provider";

const ANTHROPIC_API = "https://api.anthropic.com/v1/messages";
const OPENAI_API = "https://api.openai.com/v1/chat/completions";

const ANTHROPIC_MODEL = "claude-sonnet-4-20250514";
const OPENAI_MODEL = "gpt-4o";

export type ProviderName = "anthropic" | "openai";

export interface Message {
  role: "system" | "user" | "assistant" | "tool";
  content: string | ContentBlock[];
  tool_call_id?: string;
  tool_calls?: unknown[];
}

export type ContentBlock =
  | { type: "text"; text: string }
  | { type: "tool_use"; id: string; name: string; input: Record<string, unknown> }
  | { type: "tool_result"; tool_use_id: string; content: string };

export interface StreamCallbacks {
  onStream?: (event: unknown) => void;
  onError?: (err: Error) => void;
  onDone?: () => void;
}

// ── State ──

let apiKey: string | null = null;
let provider: ProviderName | null = null;

function detectProvider(key: string): ProviderName | null {
  if (!key) return null;
  if (key.startsWith("sk-ant-")) return "anthropic";
  if (key.startsWith("sk-")) return "openai";
  return "anthropic";
}

// ── Public API ──

export function initProvider(): void {
  try {
    apiKey = localStorage.getItem(STORAGE_KEY);
    const stored = localStorage.getItem(STORAGE_PROVIDER) as ProviderName | null;
    provider = stored || detectProvider(apiKey ?? "");
  } catch {
    apiKey = null;
    provider = null;
  }
}

export function isConfigured(): boolean {
  return !!apiKey;
}

export function getProvider(): ProviderName | null {
  return provider;
}

export function getMaskedKey(): string | null {
  if (!apiKey) return null;
  if (apiKey.length < 12) return "****";
  return apiKey.slice(0, 5) + "..." + apiKey.slice(-4);
}

export function setApiKey(key: string | null): void {
  apiKey = key;
  provider = key ? detectProvider(key) : null;
  try {
    if (apiKey && provider) {
      localStorage.setItem(STORAGE_KEY, apiKey);
      localStorage.setItem(STORAGE_PROVIDER, provider);
    } else {
      localStorage.removeItem(STORAGE_KEY);
      localStorage.removeItem(STORAGE_PROVIDER);
    }
  } catch {
    // localStorage unavailable
  }
}

export function clearApiKey(): void {
  setApiKey(null);
}

// ── Streaming Chat ──

export async function chat(
  messages: Message[],
  tools: unknown[],
  callbacks: StreamCallbacks,
): Promise<AbortController | null> {
  if (!apiKey || !provider) {
    callbacks.onError?.(new Error("No API key configured"));
    return null;
  }

  const controller = new AbortController();

  try {
    if (provider === "anthropic") {
      await chatAnthropic(messages, tools, callbacks, controller);
    } else {
      await chatOpenAI(messages, tools, callbacks, controller);
    }
  } catch (e) {
    if (e instanceof Error && e.name !== "AbortError") {
      callbacks.onError?.(e);
    }
  }

  return controller;
}

async function chatAnthropic(
  messages: Message[],
  tools: unknown[],
  callbacks: StreamCallbacks,
  controller: AbortController,
): Promise<void> {
  const systemMsg = messages.find((m) => m.role === "system");
  const convMessages = messages.filter((m) => m.role !== "system");

  const body: Record<string, unknown> = {
    model: ANTHROPIC_MODEL,
    max_tokens: 4096,
    stream: true,
    messages: convMessages,
  };

  if (systemMsg) body.system = systemMsg.content;
  if (tools?.length) body.tools = tools;

  const response = await fetch(ANTHROPIC_API, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": apiKey!,
      "anthropic-version": "2023-06-01",
      "anthropic-dangerous-direct-browser-access": "true",
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
    } catch {
      /* ignore */
    }
    throw new Error(errorMsg);
  }

  await processSSE(response, callbacks);
}

async function chatOpenAI(
  messages: Message[],
  tools: unknown[],
  callbacks: StreamCallbacks,
  controller: AbortController,
): Promise<void> {
  const body: Record<string, unknown> = {
    model: OPENAI_MODEL,
    stream: true,
    messages: messages.map((m) => ({
      role: m.role,
      content: m.content,
      ...(m.tool_call_id ? { tool_call_id: m.tool_call_id } : {}),
      ...(m.tool_calls ? { tool_calls: m.tool_calls } : {}),
    })),
  };

  if (tools?.length) body.tools = tools;

  const response = await fetch(OPENAI_API, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
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
    } catch {
      /* ignore */
    }
    throw new Error(errorMsg);
  }

  await processSSE(response, callbacks);
}

async function processSSE(
  response: Response,
  callbacks: StreamCallbacks,
): Promise<void> {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const data = line.slice(6).trim();
        if (data === "[DONE]") {
          callbacks.onDone?.();
          return;
        }
        try {
          const event = JSON.parse(data);
          callbacks.onStream?.(event);
        } catch {
          /* skip malformed lines */
        }
      }
    }
  }

  callbacks.onDone?.();
}
