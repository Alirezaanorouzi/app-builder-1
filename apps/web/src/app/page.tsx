"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fa } from "@/lib/dict";

type Project = { id: string; title: string; status: string };

export default function HomePage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/projects")
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => setProjects(d.projects ?? []))
      .catch(() => setProjects([]))
      .finally(() => setLoading(false));
  }, []);

  async function createProject() {
    const title = prompt("عنوان پروژه", "پروژه جدید");
    if (!title) return;
    const r = await fetch("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    if (r.ok) {
      const d = await r.json();
      window.location.href = `/projects/${d.id}`;
    }
  }

  return (
    <main className="container">
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>{fa.appName}</h1>
        <button
          type="button"
          className="btn btn-secondary"
          style={{ width: "auto" }}
          onClick={() => fetch("/api/auth/logout", { method: "POST" }).then(() => (window.location.href = "/login"))}
        >
          خروج
        </button>
      </header>
      <h2>{fa.projects}</h2>
      {loading ? <p>…</p> : null}
      <ul style={{ listStyle: "none", padding: 0 }}>
        {projects.map((p) => (
          <li key={p.id} style={{ marginBottom: "0.75rem" }}>
            <Link href={`/projects/${p.id}`}>{p.title}</Link>
          </li>
        ))}
      </ul>
      <button type="button" className="btn" onClick={createProject}>
        {fa.newProject}
      </button>
    </main>
  );
}