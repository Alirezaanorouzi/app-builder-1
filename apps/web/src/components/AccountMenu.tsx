"use client";

import { useEffect, useId, useRef, useState } from "react";
import Link from "next/link";
import { fa } from "@/lib/dict";

type Me = { email: string; displayName: string | null };
type Project = { id: string; title: string };

export function AccountMenu({ currentProjectId }: { currentProjectId?: string }) {
  const [open, setOpen] = useState(false);
  const [me, setMe] = useState<Me | null>(null);
  const [projects, setProjects] = useState<Project[] | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
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
        if (profile?.email) setMe(profile as Me);
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
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.href = "/login";
  }

  const name = me?.displayName?.trim() || me?.email || "…";

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
            {me?.email ? <span>{me.email}</span> : null}
          </div>
          <p className="account-menu-label">{fa.projects}</p>
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
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden>
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
