import type { KeyboardEvent } from "react";
import { fa } from "@/lib/dict";

type Props = {
  text: string;
  busy: boolean;
  warming?: boolean;
  activeStatus: string | null;
  modelLabel: string;
  onTextChange: (v: string) => void;
  onSend: () => void;
  onStop: () => void;
};

export function Composer({
  text,
  busy,
  warming = false,
  activeStatus,
  modelLabel,
  onTextChange,
  onSend,
  onStop,
}: Props) {
  const blocked = busy || warming;

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!blocked && text.trim()) onSend();
    }
  }

  return (
    <div className="composer-shell" role="region" aria-label={fa.chat}>
      <div className="composer-card">
        {busy ? (
          <p className="composer-busy-line">
            {activeStatus === "queued" ? fa.waiting : fa.running}
          </p>
        ) : warming ? (
          <p className="composer-busy-line">{fa.sandboxWarmingComposer}</p>
        ) : (
          <textarea
            className="composer-input"
            rows={1}
            value={text}
            onChange={(e) => onTextChange(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder={fa.composerPlaceholder}
            aria-label={fa.composerPlaceholder}
          />
        )}

        <ComposerFooter
          busy={blocked}
          modelLabel={modelLabel}
          onSend={onSend}
          onStop={onStop}
          text={text}
        />
      </div>
    </div>
  );
}

function ComposerFooter({
  busy,
  modelLabel,
  onSend,
  onStop,
  text,
}: {
  busy: boolean;
  modelLabel: string;
  onSend: () => void;
  onStop: () => void;
  text: string;
}) {
  return (
    <div className="composer-footer">
      <div className="composer-model-wrap" title={modelLabel}>
        <span className="composer-model">{modelLabel}</span>
      </div>

      <div className="composer-actions">
        {busy ? (
          <button type="button" className="composer-stop" onClick={onStop}>
            {fa.stop}
          </button>
        ) : (
          <button
            type="button"
            className="composer-send"
            onClick={onSend}
            disabled={!text.trim()}
            aria-label={fa.send}
          >
            <SendIcon />
          </button>
        )}
      </div>
    </div>
  );
}

function SendIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M3.4 20.6 22 12 3.4 3.4v7.2L15.6 12 3.4 13.4v7.2z" />
    </svg>
  );
}