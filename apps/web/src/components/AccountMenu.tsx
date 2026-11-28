"use client";

import { useEffect, useId, useRef, useState } from "react";
import Link from "next/link";
import { fa } from "@/lib/dict";
import { formatIranMobile } from "@/lib/phone";

type Me = { displayName: string | null; phone: string | null };
type Project = { id: string; title: string };

export function AccountMenu({ currentProjectId }: { currentProjectId?: string }) {
  const [open, setOpen] = useState(false);
  const [me, setMe] = useState<Me | null>(null);
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [naming, setNaming] = useState(false);
  const [title, setTitle] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;
    let cancel = false;
    Promise.all([
      fetch("/api/me").then((r) => (r.ok ? r.json() : null)),
      fetch("/api/projects").then((r) => (r.ok ? r.json() : null)),
    ])
      .then(([profile, list]) => {
        if (cancel) return;
        if (profile?.phone) setMe(profile as Me);
        setProjects(Array.isArray(list?.projects) ? list.projects : []);
      })
      .catch(() => {
        if (!cancel) setProjects([]);
      });
    return () => {
      cancel = true;
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onPointer(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      if (naming) {
        setNaming(false);
        setTitle("");
        return;
      }
      setOpen(false);
    }
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, naming]);

  useEffect(() => {
    if (!open) {
      setNaming(false);
      setTitle("");
    }
  }, [open]);

  useEffect(() => {
    if (naming) nameRef.current?.focus();
  }, [naming]);

  async function createProject() {
    const nextTitle = title.trim();
    if (!nextTitle || creating) return;
    setCreating(true);
    try {
      const res = await fetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: nextTitle }),
      });
      if (!res.ok) return;
      const data = (await res.json()) as { id?: string };
      if (data.id) window.location.href = `/projects/${data.id}`;
    } finally {
      setCreating(false);
    }
  }

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.href = "/register";
  }

  const phoneLabel = formatIranMobile(me?.phone);
  const name = me?.displayName?.trim() || phoneLabel || "…";
  const contact = phoneLabel;

  return (
    <div className="account-menu" ref={rootRef}>
      <button
        type="button"
        className="account-menu-button"
        aria-label={fa.account}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
      >
        <AccountIcon />
      </button>
      {open ? (
        <div className="account-menu-panel" id={panelId} role="menu">
          <div className="account-menu-identity">
            <strong>{name}</strong>
            {contact && contact !== name ? <span>{contact}</span> : null}
          </div>
          <p className="account-menu-label">{fa.projects}</p>
          {naming ? (
            <form
              className="account-menu-name"
              onSubmit={(event) => {
                event.preventDefault();
                void createProject();
              }}
            >
              <input
                ref={nameRef}
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder={fa.projectName}
                aria-label={fa.projectName}
                disabled={creating}
                maxLength={80}
              />
              <button type="submit" className="account-menu-create" disabled={creating || !title.trim()}>
                {fa.createProject}
              </button>
            </form>
          ) : (
            <button type="button" className="account-menu-new" role="menuitem" onClick={() => setNaming(true)}>
              <span aria-hidden>+</span>
              {fa.newProject}
            </button>
          )}
          <ul className="account-menu-projects">
            {projects == null ? (
              <li className="account-menu-empty">…</li>
            ) : projects.length === 0 ? (
              <li className="account-menu-empty">{fa.noProjects}</li>
            ) : (
              projects.map((project) => (
                <li key={project.id}>
                  <Link
                    href={`/projects/${project.id}`}
                    role="menuitem"
                    aria-current={project.id === currentProjectId ? "page" : undefined}
                    onClick={() => setOpen(false)}
                  >
                    {project.title}
                  </Link>
                </li>
              ))
            )}
          </ul>
          <button type="button" className="account-menu-logout" role="menuitem" onClick={() => void logout()}>
            {fa.logout}
          </button>
        </div>
      ) : null}
    </div>
  );
}

function AccountIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden>
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        d="M12 12a3.2 3.2 0 1 0-3.2-3.2A3.2 3.2 0 0 0 12 12Zm-6.2 7.2a6.2 6.2 0 0 1 12.4 0"
      />
    </svg>
  );
}
