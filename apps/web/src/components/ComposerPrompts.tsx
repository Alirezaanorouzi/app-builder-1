"use client";

import { fa } from "@/lib/dict";

export function ComposerPrompts({
  visible,
  onPick,
}: {
  visible: boolean;
  onPick: (text: string) => void;
}) {
  if (!visible) return null;
  const items = [...fa.composerPrompts, ...fa.composerPrompts];

  return (
    <div className="composer-prompts" aria-label={fa.composerPromptsLabel}>
      <div className="composer-prompts-viewport">
        <div className="composer-prompts-track">
          {items.map((label, index) => (
            <button
              key={`${index}-${label}`}
              type="button"
              className="composer-prompt-chip"
              onClick={() => onPick(label)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}