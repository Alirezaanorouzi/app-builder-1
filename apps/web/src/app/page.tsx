"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AccountMenu } from "@/components/AccountMenu";
import { fa } from "@/lib/dict";

export default function HomePage() {
  const [title, setTitle] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    fetch("/api/me")
      .then((res) => {
        if (res.status === 401) window.location.href = "/login";
        else setReady(res.ok);
      })
      .catch(() => {
        window.location.href = "/login";
      });
  }, []);

  async function createProject(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextTitle = title.trim();
    if (!nextTitle || creating) return;
    setError("");
    setCreating(true);
    try {
      const res = await fetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: nextTitle }),
      });
      if (!res.ok) {
        setError("ساخت پروژه نشد");
        return;
      }
      const data = (await res.json()) as { id?: string };
      if (data.id) window.location.href = `/projects/${data.id}`;
    } finally {
      setCreating(false);
    }
  }

  if (!ready) {
    return <main className="home-screen" aria-busy="true" />;
  }

  return (
    <main className="home-screen">
      <header className="home-top">
        <AccountMenu />
      </header>
      <form className="home-card" onSubmit={createProject}>
        <h1>{fa.appName}</h1>
        <p>{fa.homeCreateProject}</p>
        <input
          className="auth-field"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder={fa.projectName}
          aria-label={fa.projectName}
          disabled={creating}
          maxLength={80}
        />
        {error ? <p className="auth-error">{error}</p> : null}
        <button className="auth-submit" type="submit" disabled={creating || !title.trim()}>
          {fa.createProject}
        </button>
        <div className="home-links">
          <Link className="home-link" href="/contact">
            {fa.contactUs}
          </Link>
          <Link className="home-link" href="/about">
            {fa.aboutUs}
          </Link>
        </div>
      </form>
    </main>
  );
}