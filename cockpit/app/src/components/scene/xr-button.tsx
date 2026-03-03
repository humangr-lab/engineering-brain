/**
 * XR Button — enter/exit WebXR immersive mode.
 * Shows VR/AR availability and toggles session.
 */

import { useState, useEffect, useCallback } from "react";
import { Glasses } from "lucide-react";
import { checkXRSupport, type XRStatus } from "@/lib/engine/webxr";

interface XRButtonProps {
  onEnterVR?: () => void;
  onEnterAR?: () => void;
  onExit?: () => void;
}

export function XRButton({ onEnterVR, onEnterAR, onExit }: XRButtonProps) {
  const [status, setStatus] = useState<XRStatus | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    checkXRSupport().then(setStatus);
  }, []);

  const handleVR = useCallback(() => {
    setMenuOpen(false);
    if (status?.sessionActive) {
      onExit?.();
    } else {
      onEnterVR?.();
    }
  }, [status, onEnterVR, onExit]);

  const handleAR = useCallback(() => {
    setMenuOpen(false);
    if (status?.sessionActive) {
      onExit?.();
    } else {
      onEnterAR?.();
    }
  }, [status, onEnterAR, onExit]);

  // Don't render if XR is not available
  if (!status?.available || (!status.vrSupported && !status.arSupported)) {
    return null;
  }

  return (
    <div className="relative">
      <button
        onClick={() => setMenuOpen(!menuOpen)}
        className={`glass flex items-center gap-1.5 rounded-[var(--radius-sm)] px-3 py-1.5 text-[11px] transition-colors ${
          status.sessionActive
            ? "text-[var(--color-accent)]"
            : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
        }`}
        title="WebXR"
      >
        <Glasses className="h-3.5 w-3.5" />
        <span className="hidden sm:inline">
          {status.sessionActive ? "Exit XR" : "XR"}
        </span>
      </button>

      {menuOpen && (
        <div className="absolute bottom-full right-0 z-30 mb-1 w-[140px]">
          <div className="glass rounded-[var(--radius-md)] p-1.5">
            {status.vrSupported && (
              <button
                onClick={handleVR}
                className="flex w-full items-center gap-2 rounded-[var(--radius-sm)] px-2 py-1.5 text-left text-[11px] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-1)] hover:text-[var(--color-text-primary)]"
              >
                Enter VR
              </button>
            )}
            {status.arSupported && (
              <button
                onClick={handleAR}
                className="flex w-full items-center gap-2 rounded-[var(--radius-sm)] px-2 py-1.5 text-left text-[11px] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-1)] hover:text-[var(--color-text-primary)]"
              >
                Enter AR
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
