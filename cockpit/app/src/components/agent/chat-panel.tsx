import { useState, useRef, useEffect, useCallback } from "react";
import {
  X,
  Key,
  Trash2,
  Send,
  Square,
  MessageCircle,
  Loader2,
  CheckCircle2,
  AlertCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAgent, type ChatMessage } from "@/hooks/use-agent";
import type { Node, Edge } from "@/lib/api";

interface ChatPanelProps {
  open: boolean;
  onClose: () => void;
  nodes: Node[];
  edges: Edge[];
}

export function ChatPanel({ open, onClose, nodes, edges }: ChatPanelProps) {
  const {
    messages,
    isStreaming,
    configured,
    provider,
    maskedKey: _maskedKey,
    suggestions,
    sendMessage,
    stopStreaming,
    clearChat,
    configureKey,
  } = useAgent(nodes, edges);

  const [inputValue, setInputValue] = useState("");
  const [showKeyModal, setShowKeyModal] = useState(false);
  const messagesRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Scroll to bottom on new messages
  useEffect(() => {
    if (messagesRef.current) {
      messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
    }
  }, [messages]);

  // Focus input when panel opens
  useEffect(() => {
    if (open && configured) {
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open, configured]);

  const handleSend = useCallback(() => {
    const text = inputValue.trim();
    if (!text || isStreaming) return;
    sendMessage(text);
    setInputValue("");
  }, [inputValue, isStreaming, sendMessage]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  // Auto-resize textarea
  const handleInput = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setInputValue(e.target.value);
      const el = e.target;
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 120) + "px";
    },
    [],
  );

  if (!open) return null;

  return (
    <>
      <div className="flex h-full w-[380px] shrink-0 flex-col border-l border-[var(--color-border-subtle)] bg-[var(--color-surface-0)]">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[var(--color-border-subtle)] px-4 py-3">
          <div>
            <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
              Ontology Agent
            </h3>
            <div className="mt-0.5 flex items-center gap-1.5">
              <span
                className={`h-1.5 w-1.5 rounded-full ${configured ? "bg-[var(--color-success)]" : "bg-[var(--color-text-tertiary)]"}`}
              />
              <span className="text-[11px] text-[var(--color-text-tertiary)]">
                {configured
                  ? `Using your ${provider === "anthropic" ? "Anthropic" : "OpenAI"} key`
                  : "No key configured"}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setShowKeyModal(true)}
              className="rounded-[var(--radius-sm)] p-1.5 text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text-primary)]"
              title="Configure API key"
            >
              <Key className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={clearChat}
              className="rounded-[var(--radius-sm)] p-1.5 text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text-primary)]"
              title="Clear chat"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={onClose}
              className="rounded-[var(--radius-sm)] p-1.5 text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text-primary)]"
              title="Close"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        {/* Messages */}
        <div
          ref={messagesRef}
          className="flex-1 overflow-y-auto p-4"
        >
          {!configured ? (
            <NoKeyState onConfigure={() => setShowKeyModal(true)} />
          ) : messages.length === 0 ? (
            <EmptyState
              suggestions={suggestions}
              onSuggestion={(s) => {
                setInputValue(s);
                sendMessage(s);
              }}
            />
          ) : (
            <div className="space-y-3">
              {messages.map((msg) => (
                <MessageBubble key={msg.id} message={msg} />
              ))}
              {isStreaming && (
                <div className="flex items-center gap-2 px-1">
                  <div className="flex gap-1">
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--color-accent)] [animation-delay:0ms]" />
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--color-accent)] [animation-delay:150ms]" />
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--color-accent)] [animation-delay:300ms]" />
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Input */}
        <div className="border-t border-[var(--color-border-subtle)] p-3">
          <div className="flex items-end gap-2">
            <textarea
              ref={inputRef}
              value={inputValue}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              placeholder="Ask about the system..."
              disabled={!configured}
              rows={1}
              className="flex-1 resize-none rounded-[var(--radius-md)] border border-[var(--color-border-subtle)] bg-[var(--color-surface-1)] px-3 py-2 text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-tertiary)] focus:border-[var(--color-accent)] focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
            />
            {isStreaming ? (
              <Button
                size="sm"
                variant="destructive"
                onClick={stopStreaming}
                className="shrink-0"
              >
                <Square className="h-3.5 w-3.5" />
              </Button>
            ) : (
              <Button
                size="sm"
                onClick={handleSend}
                disabled={!inputValue.trim() || !configured}
                className="shrink-0"
              >
                <Send className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Key Modal */}
      {showKeyModal && (
        <KeyModal
          onClose={() => setShowKeyModal(false)}
          onSave={(key) => {
            configureKey(key);
            setShowKeyModal(false);
          }}
        />
      )}
    </>
  );
}

// ── Subcomponents ──

function NoKeyState({ onConfigure }: { onConfigure: () => void }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
      <div className="rounded-full bg-[var(--color-surface-2)] p-4">
        <Key className="h-6 w-6 text-[var(--color-text-tertiary)]" />
      </div>
      <div>
        <p className="text-sm font-medium text-[var(--color-text-primary)]">
          Configure your API key
        </p>
        <p className="mt-1 text-[13px] text-[var(--color-text-tertiary)]">
          Supports: Anthropic, OpenAI
        </p>
      </div>
      <Button size="sm" onClick={onConfigure}>
        Configure Key
      </Button>
      <p className="text-[11px] text-[var(--color-text-tertiary)]">
        Your key stays in your browser. Never sent to us.
      </p>
    </div>
  );
}

function EmptyState({
  suggestions,
  onSuggestion,
}: {
  suggestions: string[];
  onSuggestion: (s: string) => void;
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
      <div className="rounded-full bg-[var(--color-surface-2)] p-4">
        <MessageCircle className="h-6 w-6 text-[var(--color-accent)]" />
      </div>
      <p className="text-sm font-medium text-[var(--color-text-primary)]">
        Ask me about this system
      </p>
      <div className="flex flex-col gap-2">
        {suggestions.map((s) => (
          <button
            key={s}
            onClick={() => onSuggestion(s)}
            className="rounded-full border border-[var(--color-border-subtle)] px-4 py-1.5 text-[13px] text-[var(--color-text-secondary)] transition-colors hover:border-[var(--color-accent)] hover:text-[var(--color-text-primary)]"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-[var(--radius-md)] bg-[var(--color-accent)] px-3 py-2 text-sm text-white">
          {message.content}
        </div>
      </div>
    );
  }

  if (message.role === "tool") {
    const StatusIcon =
      message.toolStatus === "pending"
        ? Loader2
        : message.toolStatus === "complete"
          ? CheckCircle2
          : AlertCircle;

    return (
      <div className="flex items-center gap-2 rounded-[var(--radius-sm)] border border-[var(--color-border-subtle)] bg-[var(--color-surface-1)] px-3 py-2">
        <StatusIcon
          className={`h-3.5 w-3.5 shrink-0 ${
            message.toolStatus === "pending"
              ? "animate-spin text-[var(--color-text-tertiary)]"
              : message.toolStatus === "complete"
                ? "text-[var(--color-success)]"
                : "text-[var(--color-destructive)]"
          }`}
        />
        <div className="min-w-0">
          <span className="text-[12px] font-medium text-[var(--color-text-secondary)]">
            {message.toolName}
          </span>
          {message.toolStatus === "pending" && (
            <span className="ml-1.5 text-[11px] text-[var(--color-text-tertiary)]">
              Executing...
            </span>
          )}
        </div>
      </div>
    );
  }

  // Assistant message
  return (
    <div className="flex gap-2">
      <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-accent)]" />
      <div className="min-w-0 flex-1">
        <p className="mb-0.5 text-[10px] font-medium text-[var(--color-text-tertiary)]">
          Agent
        </p>
        <div className="text-sm leading-relaxed text-[var(--color-text-secondary)]">
          <MarkdownText text={message.content} />
        </div>
      </div>
    </div>
  );
}

function MarkdownText({ text }: { text: string }) {
  if (!text) return null;

  const paragraphs = text.split("\n\n");
  return (
    <>
      {paragraphs.map((p, i) => {
        let html = p
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;");
        html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
        html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
        html = html.replace(/\n/g, "<br>");
        return (
          <p
            key={i}
            className="mb-2 last:mb-0 [&>code]:rounded-sm [&>code]:bg-[var(--color-surface-2)] [&>code]:px-1 [&>code]:py-0.5 [&>code]:text-[12px]"
            dangerouslySetInnerHTML={{ __html: html }}
          />
        );
      })}
    </>
  );
}

function KeyModal({
  onClose,
  onSave,
}: {
  onClose: () => void;
  onSave: (key: string) => void;
}) {
  const [keyValue, setKeyValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    requestAnimationFrame(() => inputRef.current?.focus());
  }, []);

  const detected = keyValue.startsWith("sk-ant-")
    ? "Anthropic (Claude)"
    : keyValue.startsWith("sk-")
      ? "OpenAI (GPT-4)"
      : keyValue
        ? "Will attempt as Anthropic"
        : null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="glass w-full max-w-md rounded-[var(--radius-lg)] p-6">
        <h3 className="mb-2 text-base font-semibold text-[var(--color-text-primary)]">
          Configure API Key
        </h3>
        <p className="mb-4 text-[13px] text-[var(--color-text-tertiary)]">
          Enter your API key to enable the AI agent. Your key is stored locally
          in your browser and sent directly to the provider API.
        </p>
        <input
          ref={inputRef}
          type="password"
          value={keyValue}
          onChange={(e) => setKeyValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && keyValue.trim()) onSave(keyValue.trim());
            if (e.key === "Escape") onClose();
          }}
          placeholder="sk-ant-... or sk-..."
          className="mb-2 w-full rounded-[var(--radius-md)] border border-[var(--color-border-subtle)] bg-[var(--color-surface-1)] px-3 py-2 text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-tertiary)] focus:border-[var(--color-accent)] focus:outline-none"
        />
        {detected && (
          <p className="mb-4 text-[12px] text-[var(--color-accent)]">
            Detected: {detected}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button
            size="sm"
            disabled={!keyValue.trim()}
            onClick={() => onSave(keyValue.trim())}
          >
            Save Key
          </Button>
        </div>
      </div>
    </div>
  );
}
