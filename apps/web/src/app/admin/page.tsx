"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

type Funnel = {
  signups: number;
  projects: number;
  userMessages: number;
  agentReplies: number;
  previewUrls: number;
  previewOpens: number;
  previewCopies: number;
  followUps: number;
};

type Overview = {
  northStar: number;
  previousNorthStar: number;
  funnel: { allTime: Funnel; last7: Funnel };
  runSuccess: { succeeded: number; finished: number; rate: number } | null;
  medianMinutesToFirstOpen: number | null;
  activeLastDay: number;
};

type UserRow = {
  id: string;
  email: string;
  display_name: string | null;
  created_at: string;
  projects: number;
  user_messages: number;
  agent_replies: number;
  preview_opens: number;
  preview_copies: number;
  last_activity: string;
  activated: boolean;
};

type Flag = {
  key: string;
  enabled: boolean;
  note: string;
  updated_at: string;
};

const FUNNEL_ROWS: { key: keyof Funnel; label: string }[] = [
  { key: "signups", label: "Signed up" },
  { key: "projects", label: "Created a project" },
  { key: "userMessages", label: "Sent a message" },
  { key: "agentReplies", label: "Got an agent reply" },
  { key: "previewUrls", label: "Has a preview URL" },
  { key: "previewOpens", label: "Opened the preview" },
  { key: "previewCopies", label: "Copied the link" },
  { key: "followUps", label: "Sent a follow-up" },
];

function when(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-GB", { hour12: false });
}

export default function AdminPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [users, setUsers] = useState<UserRow[] | null>(null);
  const [flags, setFlags] = useState<Flag[] | null>(null);
  const [missing, setMissing] = useState(false);
  const [flagKey, setFlagKey] = useState("");
  const [flagNote, setFlagNote] = useState("");
  const [flagError, setFlagError] = useState("");

  async function loadFlags() {
    const res = await fetch("/api/admin/flags");
    if (!res.ok) return;
    const data = (await res.json()) as { flags: Flag[] };
    setFlags(data.flags);
  }

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetch("/api/admin/overview"),
      fetch("/api/admin/users"),
      fetch("/api/admin/flags"),
    ]).then(async ([overviewRes, usersRes, flagsRes]) => {
      if (cancelled) return;
      if (!overviewRes.ok || !usersRes.ok || !flagsRes.ok) {
        setMissing(true);
        return;
      }
      setOverview((await overviewRes.json()) as Overview);
      setUsers(((await usersRes.json()) as { users: UserRow[] }).users);
      setFlags(((await flagsRes.json()) as { flags: Flag[] }).flags);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  async function saveFlag(key: string, enabled: boolean, note?: string) {
    setFlagError("");
    const res = await fetch("/api/admin/flags", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(note == null ? { key, enabled } : { key, enabled, note }),
    });
    if (!res.ok) {
      setFlagError("Use a short key: letters, numbers, underscore.");
      return;
    }
    setFlagKey("");
    setFlagNote("");
    await loadFlags();
  }

  if (missing) {
    return (
      <main className="admin-shell">
        <p className="admin-muted">Not found.</p>
      </main>
    );
  }

  const delta =
    overview == null ? null : overview.northStar - overview.previousNorthStar;

  return (
    <main className="admin-shell">
      <header className="admin-header">
        <h1>Measurements</h1>
        <Link href="/">App</Link>
      </header>

      <section className="admin-card">
        <p className="admin-kicker">North star · last 7 days</p>
        <p className="admin-star">{overview ? overview.northStar : "…"}</p>
        <p className="admin-muted">
          Activated builders: an agent reply and a preview open or copy in the same week.
          {overview
            ? ` Previous 7 days: ${overview.previousNorthStar} (${delta! >= 0 ? "+" : ""}${delta}).`
            : ""}
        </p>
        <div className="admin-stats">
          <div>
            <span>Active last day</span>
            <strong>{overview ? overview.activeLastDay : "…"}</strong>
          </div>
          <div>
            <span>Run success, 7 days</span>
            <strong>
              {overview?.runSuccess
                ? `${Math.round(overview.runSuccess.rate * 100)}% (${overview.runSuccess.succeeded}/${overview.runSuccess.finished})`
                : overview
                  ? "—"
                  : "…"}
            </strong>
          </div>
          <div>
            <span>Median minutes to first open</span>
            <strong>
              {overview
                ? overview.medianMinutesToFirstOpen == null
                  ? "—"
                  : overview.medianMinutesToFirstOpen.toFixed(1)
                : "…"}
            </strong>
          </div>
        </div>
      </section>

      <section className="admin-card">
        <h2>Funnel</h2>
        <p className="admin-muted">Distinct people at each step.</p>
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Step</th>
                <th>All time</th>
                <th>Last 7 days</th>
              </tr>
            </thead>
            <tbody>
              {FUNNEL_ROWS.map((row) => (
                <tr key={row.key}>
                  <td>{row.label}</td>
                  <td>{overview ? overview.funnel.allTime[row.key] : "…"}</td>
                  <td>{overview ? overview.funnel.last7[row.key] : "…"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="admin-card">
        <h2>People</h2>
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>User</th>
                <th>Signed up</th>
                <th>Projects</th>
                <th>Messages</th>
                <th>Replies</th>
                <th>Opens</th>
                <th>Copies</th>
                <th>Last activity</th>
                <th>Activated</th>
              </tr>
            </thead>
            <tbody>
              {(users ?? []).map((user) => (
                <tr key={user.id}>
                  <td>
                    <Link href={`/admin/users/${user.id}`}>
                      {user.display_name || user.email}
                    </Link>
                    <div className="admin-muted">{user.email}</div>
                  </td>
                  <td>{when(user.created_at)}</td>
                  <td>{user.projects}</td>
                  <td>{user.user_messages}</td>
                  <td>{user.agent_replies}</td>
                  <td>{user.preview_opens}</td>
                  <td>{user.preview_copies}</td>
                  <td>{when(user.last_activity)}</td>
                  <td>{user.activated ? "Yes" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {users && users.length === 0 ? <p className="admin-muted">No users yet.</p> : null}
      </section>

      <section className="admin-card">
        <h2>Feature flags</h2>
        <p className="admin-muted">
          Toggles are stored for the app to read. Turning one on does not change the builder by itself.
        </p>
        <ul className="admin-flags">
          {(flags ?? []).map((flag) => (
            <li key={flag.key}>
              <div>
                <strong>{flag.key}</strong>
                {flag.note ? <div className="admin-muted">{flag.note}</div> : null}
              </div>
              <button
                type="button"
                className={flag.enabled ? "admin-toggle admin-toggle-on" : "admin-toggle"}
                onClick={() => void saveFlag(flag.key, !flag.enabled)}
              >
                {flag.enabled ? "On" : "Off"}
              </button>
            </li>
          ))}
        </ul>
        <form
          className="admin-flag-form"
          onSubmit={(event) => {
            event.preventDefault();
            void saveFlag(flagKey.trim().toLowerCase(), true, flagNote.trim());
          }}
        >
          <input
            value={flagKey}
            onChange={(event) => setFlagKey(event.target.value)}
            placeholder="flag_key"
            aria-label="Flag key"
          />
          <input
            value={flagNote}
            onChange={(event) => setFlagNote(event.target.value)}
            placeholder="Note"
            aria-label="Flag note"
          />
          <button type="submit" className="admin-toggle admin-toggle-on">
            Add
          </button>
        </form>
        {flagError ? <p className="admin-error">{flagError}</p> : null}
      </section>
    </main>
  );
}
