import { useState, useEffect, useCallback } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import {
  initProvider,
  isConfigured,
  getProvider,
  getMaskedKey,
  setApiKey,
  type ProviderName,
} from "@/lib/agent/provider";
import {
  isEnrichmentEnabled,
  setEnrichmentEnabled,
} from "@/lib/agent/classifier";

export default function SettingsPage() {
  const [configured, setConfigured] = useState(false);
  const [provider, setProvider] = useState<ProviderName | null>(null);
  const [maskedKey, setMaskedKey] = useState<string | null>(null);
  const [enrichment, setEnrichment] = useState(false);
  const [keyInput, setKeyInput] = useState("");
  const [showKeyInput, setShowKeyInput] = useState(false);

  useEffect(() => {
    initProvider();
    setConfigured(isConfigured());
    setProvider(getProvider());
    setMaskedKey(getMaskedKey());
    setEnrichment(isEnrichmentEnabled());
  }, []);

  const handleSaveKey = useCallback(() => {
    if (keyInput.trim()) {
      setApiKey(keyInput.trim());
      initProvider();
      setConfigured(isConfigured());
      setProvider(getProvider());
      setMaskedKey(getMaskedKey());
      setKeyInput("");
      setShowKeyInput(false);
    }
  }, [keyInput]);

  const handleClearKey = useCallback(() => {
    setApiKey(null);
    setConfigured(false);
    setProvider(null);
    setMaskedKey(null);
    setShowKeyInput(false);
  }, []);

  const handleToggleEnrichment = useCallback(() => {
    const next = !enrichment;
    setEnrichmentEnabled(next);
    setEnrichment(next);
  }, [enrichment]);

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <Card>
        <CardHeader>
          <CardTitle>General</CardTitle>
          <CardDescription>
            Configure your Ontology Map workspace.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-[var(--color-text-primary)]">
                Theme
              </p>
              <p className="text-[13px] text-[var(--color-text-tertiary)]">
                Switch between dark and light mode.
              </p>
            </div>
            <span className="rounded-[var(--radius-sm)] bg-[var(--color-surface-2)] px-3 py-1 text-xs text-[var(--color-text-secondary)]">
              Dark
            </span>
          </div>
          <Separator />
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-[var(--color-text-primary)]">
                Sound Effects
              </p>
              <p className="text-[13px] text-[var(--color-text-tertiary)]">
                Enable ambient and interaction sounds.
              </p>
            </div>
            <span className="rounded-[var(--radius-sm)] bg-[var(--color-surface-2)] px-3 py-1 text-xs text-[var(--color-text-secondary)]">
              Off
            </span>
          </div>
          <Separator />
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-[var(--color-text-primary)]">
                Performance Mode
              </p>
              <p className="text-[13px] text-[var(--color-text-tertiary)]">
                Reduce visual effects for large graphs.
              </p>
            </div>
            <span className="rounded-[var(--radius-sm)] bg-[var(--color-surface-2)] px-3 py-1 text-xs text-[var(--color-text-secondary)]">
              Auto
            </span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>AI Agent</CardTitle>
          <CardDescription>
            Configure your LLM provider and API keys. BYOK — keys stored
            locally, never sent to our servers.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Provider */}
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-[var(--color-text-primary)]">
                Provider
              </p>
              <p className="text-[13px] text-[var(--color-text-tertiary)]">
                Auto-detected from API key prefix.
              </p>
            </div>
            <span className="rounded-[var(--radius-sm)] bg-[var(--color-surface-2)] px-3 py-1 text-xs text-[var(--color-text-secondary)]">
              {provider
                ? provider.charAt(0).toUpperCase() + provider.slice(1)
                : "None"}
            </span>
          </div>
          <Separator />

          {/* API Key */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-[var(--color-text-primary)]">
                  API Key
                </p>
                <p className="text-[13px] text-[var(--color-text-tertiary)]">
                  {configured
                    ? `Active: ${maskedKey}`
                    : "Paste your Anthropic or OpenAI API key."}
                </p>
              </div>
              {configured ? (
                <div className="flex gap-2">
                  <button
                    onClick={() => setShowKeyInput(!showKeyInput)}
                    className="rounded-[var(--radius-sm)] bg-[var(--color-surface-2)] px-3 py-1 text-xs text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-3)]"
                  >
                    Change
                  </button>
                  <button
                    onClick={handleClearKey}
                    className="rounded-[var(--radius-sm)] bg-[var(--color-surface-2)] px-3 py-1 text-xs text-[var(--color-destructive)] transition-colors hover:bg-[var(--color-surface-3)]"
                  >
                    Remove
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setShowKeyInput(!showKeyInput)}
                  className="rounded-[var(--radius-sm)] bg-[var(--color-accent)] px-3 py-1 text-xs text-white transition-opacity hover:opacity-90"
                >
                  Add Key
                </button>
              )}
            </div>

            {showKeyInput && (
              <div className="flex gap-2">
                <input
                  type="password"
                  value={keyInput}
                  onChange={(e) => setKeyInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleSaveKey();
                  }}
                  placeholder="sk-ant-... or sk-..."
                  className="flex-1 rounded-[var(--radius-sm)] border border-[var(--color-border-subtle)] bg-[var(--color-surface-1)] px-3 py-1.5 text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-tertiary)] focus:border-[var(--color-accent)] focus:outline-none"
                  autoFocus
                />
                <button
                  onClick={handleSaveKey}
                  disabled={!keyInput.trim()}
                  className="rounded-[var(--radius-sm)] bg-[var(--color-accent)] px-4 py-1.5 text-xs text-white transition-opacity hover:opacity-90 disabled:opacity-40"
                >
                  Save
                </button>
              </div>
            )}
          </div>
          <Separator />

          {/* LLM Enrichment Toggle */}
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-[var(--color-text-primary)]">
                LLM Node Enrichment
              </p>
              <p className="text-[13px] text-[var(--color-text-tertiary)]">
                When enabled, nodes are classified by an LLM after analysis.
                Uses Haiku/GPT-4o-mini for low cost.
              </p>
            </div>
            <button
              onClick={handleToggleEnrichment}
              className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full transition-colors ${
                enrichment
                  ? "bg-[var(--color-accent)]"
                  : "bg-[var(--color-surface-3)]"
              }`}
            >
              <span
                className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${
                  enrichment ? "translate-x-[18px]" : "translate-x-[3px]"
                }`}
              />
            </button>
          </div>

          {enrichment && !configured && (
            <p className="rounded-[var(--radius-sm)] bg-amber-500/10 px-3 py-2 text-[12px] text-amber-400">
              Enrichment is enabled but no API key is set. Add a key above.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
