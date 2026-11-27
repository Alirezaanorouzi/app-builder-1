"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

type Detail = {
  user: {
    id: string;
    email: string;
    display_name: string | null;
    created_at: string;
  };
  projects: {
    id: string;
    title: string;
    status: string;
    preview_url: string | null;
    opens: number;
    copies: number;
  }[];
  messages: {
    id: string;
    role: string;
    content: string;
    created_at: string;
    project_id: string;
    title: string;
  }[];
  usage?: {
    toman: number;
    usd: number;
    promptTokens: number;
    completionTokens: number;
    cacheReadTokens: number;
    reasoningTokens: number;
    calls: number;
  };
};

function when(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-GB", { hour12: false });
}

export default function AdminUserPage() {
  const params = useParams();
  const id = String(params.id);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/admin/users/${id}`)
      .then(async (res) => {
        if (cancelled) return;
        if (!res.ok) {
          setMissing(true);
          return;
        }
        setDetail((await res.json()) as Detail);
      })
      .catch(() => {
        if (!cancelled) setMissing(true);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (missing) {
    return (
      <main className="admin-shell">
        <p className="admin-muted">Not found.</p>
      </main>
    );
  }

  return (
    <main className="admin-shell">
      <header className="admin-header">
        <div>
          <p className="admin-kicker">
            <Link href="/admin">Measurements</Link>
          </p>
          <h1>{detail ? detail.user.display_name || detail.user.email : "…"}</h1>
          {detail ? (
            <p className="admin-muted">
              {detail.user.email} · signed up {when(detail.user.created_at)}
              {detail.usage
                ? ` · ${detail.usage.toman.toLocaleString("en-US", { maximumFractionDigits: 1 })} toman · ${detail.usage.calls} calls · ${detail.usage.promptTokens.toLocaleString("en-US")} prompt · ${detail.usage.completionTokens.toLocaleString("en-US")} completion · ${detail.usage.cacheReadTokens.toLocaleString("en-US")} cached`
                : ""}
            </p>
          ) : null}
        </div>
      </header>

      <section className="admin-card">
        <h2>Projects</h2>
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Project</th>
                <th>Status</th>
                <th>Opens</th>
                <th>Copies</th>
                <th>Preview</th>
              </tr>
            </thead>
            <tbody>
              {(detail?.projects ?? []).map((project) => (
                <tr key={project.id}>
                  <td>{project.title}</td>
                  <td>{project.status}</td>
                  <td>{project.opens}</td>
                  <td>{project.copies}</td>
                  <td className="admin-url-cell">
                    {project.preview_url ? (
                      <a
                        className="admin-url"
                        href={project.preview_url}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        {project.preview_url}
                      </a>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="admin-card">
        <h2>Messages</h2>
        <p className="admin-muted">Latest 200 user and agent messages, oldest first.</p>
        <ol className="admin-thread">
          {(detail?.messages ?? []).map((message) => (
            <li key={message.id} className={`admin-msg admin-msg-${message.role}`}>
              <div className="admin-msg-meta">
                <span>{message.role === "user" ? "User" : "Agent"}</span>
                <span>{message.title}</span>
                <span>{when(message.created_at)}</span>
              </div>
              <pre>{message.content}</pre>
            </li>
          ))}
        </ol>
        {detail && detail.messages.length === 0 ? (
          <p className="admin-muted">No messages yet.</p>
        ) : null}
      </section>
    </main>
  );
}
