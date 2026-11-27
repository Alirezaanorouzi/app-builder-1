import type { KeyboardEvent } from "react";
import { fa } from "@/lib/dict";

type UsageGate = {
  state: "open" | "cooldown" | "blocked";
  resumeAt: string | null;
};

type Props = {
  text: string;
  busy: boolean;
  warming?: boolean;
  hasMessages?: boolean;
  activeStatus: string | null;
  usage?: UsageGate | null;
  onTextChange: (v: string) => void;
  onSend: () => void;
  onStop: () => void;
  onRequestWake?: () => void;
};

function limitCopy(usage: UsageGate) {
  if (usage.state === "cooldown" && usage.resumeAt) {
    const time = new Intl.DateTimeFormat("fa-IR", {
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
      timeZone: "Asia/Tehran",
    }).format(new Date(usage.resumeAt));
    return fa.usageLimitCooldown.replace("{time}", time);
  }
  return fa.usageLimitBlocked;
}

export function Composer({
  text,
  busy,
  warming = false,
  hasMessages = false,
  activeStatus,
  usage = null,
  onTextChange,
  onSend,
  onStop,
  onRequestWake,
}: Props) {
  const busyLine =
    activeStatus === "queued" || activeStatus == null ? fa.waiting : fa.running;
  const placeholder = hasMessages
    ? fa.composerPlaceholderFollowUp
    : fa.composerPlaceholderFirst;
  const limited = usage != null && usage.state !== "open";

  function onComposerFocus() {
    if (!busy) onRequestWake?.();
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!busy && !limited && text.trim()) onSend();
    }
  }

  return (
    <div className="composer-shell" role="region" aria-label={fa.chat}>
      {limited && usage ? (
        <div className="usage-limit-bar" role="status">
          <p>{limitCopy(usage)}</p>
          <button type="button" className="usage-limit-upgrade">
            {fa.upgradePlan}
          </button>
        </div>
      ) : null}
      <div className="composer-card">
        {busy ? (
          <div className="composer-row">
            <p className="composer-busy-line" role="status" aria-live="polite">
              {busyLine}
            </p>
            <button type="button" className="composer-stop" onClick={onStop}>
              {fa.stop}
            </button>
          </div>
        ) : (
          <div className="composer-row">
            <div className="composer-field">
              {warming ? (
                <p className="composer-warm-hint" role="status">
                  {fa.sandboxWarmingComposer}
                </p>
              ) : null}
              <textarea
                className="composer-input"
                rows={2}
                value={text}
                onChange={(e) => onTextChange(e.target.value)}
                onFocus={onComposerFocus}
                onKeyDown={onKeyDown}
                placeholder={placeholder}
                aria-label={placeholder}
                disabled={limited}
              />
            </div>
            <button
              type="button"
              className="composer-send"
              onClick={onSend}
              disabled={limited || !text.trim()}
              aria-label={fa.send}
            >
              <SendIcon />
            </button>
          </div>
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