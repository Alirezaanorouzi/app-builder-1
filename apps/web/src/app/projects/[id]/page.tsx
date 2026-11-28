"use client";

import { useEffect, useRef, useState } from "react";
import { useProjectStream } from "@/hooks/useProjectStream";
import { useParams } from "next/navigation";
import { AccountMenu } from "@/components/AccountMenu";
import { HelpMenu } from "@/components/HelpMenu";
import { ActivityRail } from "@/components/ActivityRail";
import { ChatMessage } from "@/components/ChatMessage";
import { Composer } from "@/components/Composer";
import { ThinkingLoader } from "@/components/ThinkingLoader";
import { fa } from "@/lib/dict";
import type { UsageGate } from "@/lib/usage-limit";
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
  const [activityOpen, setActivityOpen] = useState(false);
  const [copiedPreview, setCopiedPreview] = useState(false);
  const [sendPending, setSendPending] = useState(false);
  const [usage, setUsage] = useState<UsageGate | null>(null);
  const [runStartedAt, setRunStartedAt] = useState<number | null>(null);
  const [thinkingVisible, setThinkingVisible] = useState(false);
  const sendingRef = useRef(false);
  const scrollTurnRef = useRef<string | null>(null);
  const model =
    process.env.NEXT_PUBLIC_DEFAULT_MODEL ?? "deepseek/deepseek-v4.1-flash-1017";

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
  const activityEvents = runEvents.filter(isActivityChipEvent);
  const wakeInFlight = previewWaking;

  const { requestWake } = useSandboxWake(id, sandbox, previewUrl, { busy, wakeInFlight });

  const stackReady = isSandboxStackReady(sandbox, previewUrl, wakeInFlight);
  const sandboxWarming = usesVercelRemoteStack(sandbox) && !stackReady;

  useEffect(() => {
    let cancel = false;
    fetch("/api/me/usage-limit")
      .then((r) => (r.ok ? r.json() : null))
      .then((gate: UsageGate | null) => {
        if (!cancel && gate?.state) setUsage(gate);
      })
      .catch(() => undefined);
    return () => {
      cancel = true;
    };
  }, [id, busy]);

  useEffect(() => {
    if (usage?.state !== "cooldown" || !usage.resumeAt) return;
    const wait = new Date(usage.resumeAt).getTime() - Date.now();
    const timer = window.setTimeout(() => {
      setUsage((prev) =>
        prev?.state === "cooldown" ? { ...prev, state: "open", resumeAt: null } : prev,
      );
    }, Math.max(0, wait));
    return () => window.clearTimeout(timer);
  }, [usage]);

  useEffect(() => {
    setActivityOpen(false);
  }, [busy]);

  useEffect(() => {
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (!lastUser || scrollTurnRef.current === lastUser.id) return;
    const messageId = lastUser.id;
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const el = document.querySelector(
          `[data-msg-id="${CSS.escape(messageId)}"]`,
        );
        if (!(el instanceof HTMLElement)) return;
        scrollTurnRef.current = messageId;
        const header = document.querySelector(".project-header");
        const offset =
          (header instanceof HTMLElement ? header.offsetHeight : 56) + 12;
        const top = el.getBoundingClientRect().top + window.scrollY - offset;
        window.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
      });
    });
  }, [messages]);

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
    if (!content || busy || sendingRef.current || (usage && usage.state !== "open")) return;
    sendingRef.current = true;
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
        const body = (await res.json().catch(() => ({}))) as {
          error?: string;
          usage?: UsageGate;
        };
        setMessages((prev) => prev.filter((m) => m.id !== optimisticId));
        setText(content);
        setActiveStatus(null);
        setRunStartedAt(null);
        if (body.usage?.state && body.usage.state !== "open") {
          setUsage(body.usage);
          return;
        }
        alert(body.error ?? "ارسال ناموفق بود");
        return;
      }
    } finally {
      sendingRef.current = false;
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

  function recordPreviewEvent(name: "preview_open" | "preview_copy") {
    void fetch(`/api/projects/${id}/events`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
  }

  async function copyPreviewUrl() {
    if (!previewUrl) return;
    try {
      await navigator.clipboard.writeText(previewUrl);
      setCopiedPreview(true);
      recordPreviewEvent("preview_copy");
      window.setTimeout(() => setCopiedPreview(false), 2000);
    } catch {
      /* ignore */
    }
  }

  const lastUserIndex = messages.findLastIndex((m) => m.role === "user");
  const historyMessages =
    lastUserIndex > 0
      ? messages.slice(0, lastUserIndex)
      : lastUserIndex < 0
        ? messages
        : [];
  const turnMessages = lastUserIndex >= 0 ? messages.slice(lastUserIndex) : [];
  const turnLast = turnMessages[turnMessages.length - 1];
  const replyAfterActivity =
    turnLast?.role === "assistant" && activityEvents.length > 0 ? turnLast : null;
  const turnBody = replyAfterActivity ? turnMessages.slice(0, -1) : turnMessages;

  return (
    <div className={tab === "preview" ? "project-shell project-shell-preview" : "project-shell"}>
      <header className="project-header">
        <AccountMenu currentProjectId={id} />
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
        <HelpMenu />
      </header>

      <main className={tab === "preview" ? "project-main project-main-preview" : "project-main"}>
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
              {historyMessages.map((m) => (
                <ChatMessage key={m.id} id={m.id} role={m.role} content={m.content} />
              ))}
              {turnMessages.length > 0 ? (
                <div className="chat-turn">
                  {turnBody.map((m) => (
                    <ChatMessage key={m.id} id={m.id} role={m.role} content={m.content} />
                  ))}
                  {activityEvents.length > 0 ? (
                    <ActivityRail
                      events={activityEvents}
                      open={activityOpen}
                      live={busy}
                      onToggle={() => setActivityOpen((v) => !v)}
                    />
                  ) : null}
                  {replyAfterActivity ? (
                    <ChatMessage
                      key={replyAfterActivity.id}
                      role={replyAfterActivity.role}
                      content={replyAfterActivity.content}
                    />
                  ) : null}
                  <ThinkingLoader visible={thinkingVisible} />
                  {busy && liveOutput ? (
                    <ChatMessage role="assistant" content={liveOutput} streaming />
                  ) : null}
                </div>
              ) : null}
            </div>
          </section>
        ) : previewUrl ? (
          <section className="preview-pane">
            <iframe
              className="preview"
              title="preview"
              src={previewUrl}
              sandbox="allow-scripts allow-same-origin"
            />
            <div className="preview-url-bar">
              <a
                className="preview-url-text"
                href={previewUrl}
                target="_blank"
                rel="noopener noreferrer"
                title={previewUrl}
                onClick={() => recordPreviewEvent("preview_open")}
              >
                {previewUrl}
              </a>
              <a
                className="preview-url-copy preview-url-open"
                href={previewUrl}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={fa.previewOpenLink}
                title={fa.previewOpenLink}
                onClick={() => recordPreviewEvent("preview_open")}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden>
                  <path
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M14 5h5v5M19 5l-8 8M10 5H6a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-4"
                  />
                </svg>
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
          hasMessages={messages.length > 0}
          activeStatus={activeStatus}
          usage={usage}
          onTextChange={setText}
          onSend={send}
          onStop={stop}
          onRequestWake={requestWake}
        />
      ) : null}
    </div>
  );
}