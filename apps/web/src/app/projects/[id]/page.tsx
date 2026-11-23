"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { fa } from "@/lib/dict";

type Message = { id: string; role: string; content: string };

type RunEvent = { seq: number; event_class: string; tool_name: string | null; summary: string };

type SandboxInfo = {
  preview_url: string | null;
  provider: string | null;
  external_id: string | null;
  status: string | null;
  name: string | null;
} | null;

export default function ProjectPage() {
  const params = useParams();
  const id = String(params.id);
  const [tab, setTab] = useState<"chat" | "preview">("chat");
  const [messages, setMessages] = useState<Message[]>([]);
  const [runEvents, setRunEvents] = useState<RunEvent[]>([]);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [sandbox, setSandbox] = useState<SandboxInfo>(null);
  const [activeStatus, setActiveStatus] = useState<string | null>(null);
  const [text, setText] = useState("");
  const model =
    process.env.NEXT_PUBLIC_DEFAULT_MODEL ?? "deepseek/deepseek-v4.1-flash";

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
          });
        }
      });

    const es = new EventSource(`/api/projects/${id}/stream`);
    es.addEventListener("update", (ev) => {
      const data = JSON.parse((ev as MessageEvent).data);
      setMessages(data.messages ?? []);
      setActiveStatus(data.activeRun?.status ?? null);
      setRunEvents(data.runEvents ?? []);
      if (data.previewUrl) setPreviewUrl(data.previewUrl);
      if (data.sandbox) setSandbox(data.sandbox);
    });
    return () => es.close();
  }, [id]);

  const busy = activeStatus === "queued" || activeStatus === "running";

  async function send() {
    if (!text.trim() || busy) return;
    await fetch(`/api/projects/${id}/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: text, model }),
    });
    setText("");
  }

  async function stop() {
    await fetch(`/api/projects/${id}/runs`, { method: "DELETE" });
  }

  const previewLabel =
    sandbox?.provider === "vercel"
      ? fa.previewVercel
      : sandbox?.provider === "local"
        ? fa.previewLocal
        : null;

  return (
    <main className="container">
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

      {tab === "chat" ? (
        <section>
          {messages.map((m) => (
            <div key={m.id} className={`message ${m.role === "user" ? "message-user" : ""}`}>
              {m.content}
            </div>
          ))}
          {busy && runEvents.length > 0 ? (
            <p className="activity-title">{fa.activity}</p>
          ) : null}
          {busy
            ? runEvents.map((e) => (
                <div key={e.seq} className="activity-line">
                  {e.summary}
                </div>
              ))
            : null}
        </section>
      ) : previewUrl ? (
        <>
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
        </>
      ) : (
        <p>{busy ? fa.previewPendingVercel : fa.previewEmpty}</p>
      )}

      <div className="composer">
        <div className="composer-inner">
          {busy ? (
            <button type="button" className="btn btn-secondary" onClick={stop}>
              {fa.stop}
            </button>
          ) : (
            <>
              <textarea
                className="input"
                rows={2}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="پیام خود را بنویسید…"
              />
              <button type="button" className="btn" onClick={send}>
                {fa.send}
              </button>
            </>
          )}
          {busy ? <span>{activeStatus === "queued" ? fa.waiting : fa.running}</span> : null}
        </div>
      </div>
    </main>
  );
}