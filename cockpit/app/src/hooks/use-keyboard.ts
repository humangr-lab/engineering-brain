import { useEffect } from "react";

type KeyHandler = (e: KeyboardEvent) => void;

interface KeyBinding {
  key: string;
  meta?: boolean;
  ctrl?: boolean;
  shift?: boolean;
  handler: KeyHandler;
}

/**
 * Global keyboard shortcut hook.
 * Registers keybindings and cleans up on unmount.
 */
export function useKeyboard(bindings: KeyBinding[]) {
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      for (const binding of bindings) {
        const keyMatch = e.key.toLowerCase() === binding.key.toLowerCase();
        const metaMatch = binding.meta ? e.metaKey : !e.metaKey;
        const ctrlMatch = binding.ctrl ? e.ctrlKey : !e.ctrlKey;
        const shiftMatch = binding.shift ? e.shiftKey : !e.shiftKey;

        if (keyMatch && metaMatch && ctrlMatch && shiftMatch) {
          e.preventDefault();
          binding.handler(e);
          return;
        }
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [bindings]);
}
