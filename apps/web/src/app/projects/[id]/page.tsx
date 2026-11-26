"use client";

import { useEffect, useRef, useState } from "react";
import { useProjectStream } from "@/hooks/useProjectStream";
import { useParams } from "next/navigation";
import { ActivityRail } from "@/components/ActivityRail";
import { ChatMessage } from "@/components/ChatMessage";
import { Composer } from "@/components/Composer";
import { ThinkingLoader } from "@/components/ThinkingLoader";
import { fa } from "@/lib/dict";
import { isActivityChipEvent } from "@/lib/run-events";
import { shouldHideThinkingLoader, THINKING_DELAY_MS } from "@/lib/run-thinking";
import { useSandboxWake } from "@/hooks/useSandboxWake";
import { isSandboxStackReady, usesVercelRemoteStack } from "@/lib/sandbox-wake";

type SandboxInfo = {
  preview_url: string | null;
  provider: string | null;
  external_id: string | null;
  status: string | null;
  name: string | null;
  agent_server_status?: string | null;
  session_expires_at?: string | null;
} | null;

function shortModelLabel(model: string) {
  const part = model.split("/").pop() ?? model;
  return part.length > 28 ? `${part.slice(0, 25)}…` : part;
}

export default function ProjectPage() {
  const params = useParams();
  const id = String(params.id);
  const [tab, setTab] = useState<"chat" | "preview">("chat");
  const {
    messages,
    setMessages,
    runEvents,
    previewUrl,
    setPreviewUrl,
    sandbox,
    setSandbox,
    activeStatus,
    setActiveStatus,
    previewWaking,
    liveOutput,
  } = useProjectStream(id);
  const [text, setText] = useState("");
  const [activityOpen, setActivityOpen] = useState(true);
  const [copiedPreview, setCopiedPreview] = useState(false);
  const [sendPending, setSendPending] = useState(false);
  const [runStartedAt, setRunStartedAt] = useState<number | null>(null);
  const [thinkingVisible, setThinkingVisible] = useState(false);
  const activityEndRef = useRef<HTMLDivElement | null>(null);
  const threadEndRef = useRef<HTMLDivElement | null>(null);
  const model =
    process.env.NEXT_PUBLIC_DEFAULT_MODEL ?? "deepseek/deepseek-v4.1-flash-1017";
  const modelLabel = shortModelLabel(model);

  useEffect(() => {
    fetch(`/api/projects/${id}`)
      .then((r) => r.json())
      .then((p) => {
        setPreviewUrl(p.preview_url ?? null);
        if (p.sandbox_status || p.provider) {
          setSandbox({
            preview_url: p.preview_url,
            provider: p.provider,
            external_id: p.external_id,
            status: p.sandbox_status,
            name: p.sandbox_name,
            agent_server_status: p.agent_server_status ?? null,
            session_expires_at: p.session_expires_at ?? null,
          });
        }
      });

  }, [id, setPreviewUrl, setSandbox]);

  const busy =
    sendPending || activeStatus === "queued" || activeStatus === "running";
  const activityChips = runEvents.filter(isActivityChipEvent).slice(-14);
  const wakeInFlight = previewWaking;

  const { requestWake } = useSandboxWake(id, sandbox, previewUrl, { busy, wakeInFlight });

  const stackReady = isSandboxStackReady(sandbox, previewUrl, wakeInFlight);
  const sandboxWarming = usesVercelRemoteStack(sandbox) && !stackReady;

  useEffect(() => {
    if (!busy || !activityOpen) return;
    activityEndRef.current?.scrollIntoView({ behavior: "smooth", inline: "end", block: "nearest" });
  }, [runEvents.length, busy, activityOpen]);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, liveOutput, thinkingVisible]);

  useEffect(() => {
    if (!busy) {
      setRunStartedAt(null);
      setThinkingVisible(false);
      return;
    }
    if (runStartedAt == null) return;
    if (shouldHideThinkingLoader(runEvents, liveOutput)) {
      setThinkingVisible(false);
      return;
    }
    const elapsed = Date.now() - runStartedAt;
    if (elapsed >= THINKING_DELAY_MS) {
      setThinkingVisible(true);
      return;
    }
    const timer = window.setTimeout(
      () => setThinkingVisible(true),
      THINKING_DELAY_MS - elapsed,
    );
    return () => window.clearTimeout(timer);
  }, [busy, runStartedAt, runEvents, liveOutput]);

  async function send() {
    const content = text.trim();
    if (!content || busy || sandboxWarming) return;
    const optimisticId = `opt-${Date.now()}`;
    setSendPending(true);
    setActiveStatus("queued");
    setMessages((prev) => [...prev, { id: optimisticId, role: "user", content }]);
    setText("");
    setRunStartedAt(Date.now());
    setThinkingVisible(false);
    try {
      const res = await fetch(`/api/projects/${id}/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, model }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: string };
        setMessages((prev) => prev.filter((m) => m.id !== optimisticId));
        setActiveStatus(null);
        setRunStartedAt(null);
        alert(body.error ?? "ارسال ناموفق بود");
        return;
      }
    } finally {
      setSendPending(false);
    }
  }

  async function stop() {
    setActiveStatus(null);
    setRunStartedAt(null);
    try {
      await fetch(`/api/projects/${id}/runs`, { method: "DELETE" });
    } catch {
      /* stream will restore status if the run is still active */
    }
  }

  async function copyPreviewUrl() {
    if (!previewUrl) return;
    try {
      await navigator.clipboard.writeText(previewUrl);
      setCopiedPreview(true);
      window.setTimeout(() => setCopiedPreview(false), 2000);
    } catch {
      /* ignore */
    }
  }

  const previewLabel =
    sandbox?.provider === "vercel"
      ? fa.previewVercel
      : sandbox?.provider === "local"
        ? fa.previewLocal
        : null;

  return (
    <div className="project-shell">
      <header className="project-header">
        <div className="tabs">
          <button
            type="button"
            className={`tab ${tab === "chat" ? "tab-active" : ""}`}
            onClick={() => setTab("chat")}
          >
            {fa.chat}
          </button>
          <button
            type="button"
            className={`tab ${tab === "preview" ? "tab-active" : ""}`}
            onClick={() => setTab("preview")}
          >
            {fa.preview}
          </button>
        </div>
      </header>

      <main className="project-main">
        {tab === "chat" ? (
          <section className="chat-thread" aria-label={fa.chat}>
            {sandboxWarming && !busy ? (
              <p className="sandbox-warm-banner" role="status">
                {wakeInFlight ? fa.previewWaking : fa.sandboxWarming}
                <span className="sandbox-warm-hint"> {fa.sandboxWarmingHint}</span>
              </p>
            ) : null}
            <div className="chat-messages">
              {messages.length === 0 ? (
                <p className="chat-empty">{fa.chatEmpty}</p>
              ) : null}
              {messages.map((m) => (
                <ChatMessage key={m.id} role={m.role} content={m.content} />
              ))}
              <ThinkingLoader visible={thinkingVisible} />
              {busy && liveOutput ? (
                <ChatMessage role="assistant" content={liveOutput} streaming />
              ) : null}
              {busy && runEvents.length > 0 ? (
                <ActivityRail
                  events={activityChips}
                  open={activityOpen}
                  onToggle={() => setActivityOpen((v) => !v)}
                  endRef={activityEndRef}
                />
              ) : null}
              <div ref={threadEndRef} className="thread-anchor" />
            </div>
          </section>
        ) : previewUrl ? (
          <section className="preview-pane">
            {previewLabel ? <p className="preview-meta">{previewLabel}</p> : null}
            {sandbox?.external_id ? (
              <p className="preview-meta preview-meta-mono">{sandbox.external_id}</p>
            ) : null}
            <iframe
              className="preview"
              title="preview"
              src={previewUrl}
              sandbox="allow-scripts allow-same-origin"
            />
            <div className="preview-url-bar">
              <a
                className="preview-url-link"
                href={previewUrl}
                target="_blank"
                rel="noopener noreferrer"
                title={fa.previewOpenLink}
              >
                {previewUrl}
              </a>
              <button
                type="button"
                className="preview-url-copy"
                onClick={() => void copyPreviewUrl()}
                aria-label={copiedPreview ? fa.previewCopied : fa.previewCopyLink}
                title={copiedPreview ? fa.previewCopied : fa.previewCopyLink}
              >
                {copiedPreview ? (
                  <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden>
                    <path
                      fill="currentColor"
                      d="M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4L9 16.2z"
                    />
                  </svg>
                ) : (
                  <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden>
                    <path
                      fill="currentColor"
                      d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"
                    />
                  </svg>
                )}
              </button>
            </div>
          </section>
        ) : (
          <p className="preview-placeholder">
            {previewWaking
              ? fa.previewWaking
              : busy
                ? fa.previewPendingVercel
                : fa.previewEmpty}
          </p>
        )}
      </main>

      {tab === "chat" ? (
        <Composer
          text={text}
          busy={busy}
          warming={sandboxWarming}
          activeStatus={activeStatus}
          modelLabel={modelLabel}
          onTextChange={setText}
          onSend={send}
          onStop={stop}
          onRequestWake={requestWake}
        />
      ) : null}
    </div>
  );
}