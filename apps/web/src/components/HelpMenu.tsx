"use client";

import { useEffect, useId, useRef, useState } from "react";
import Link from "next/link";
import { fa } from "@/lib/dict";

export function HelpMenu() {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const panelId = useId();

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

  return (
    <div className="help-menu" ref={rootRef}>
      <button
        type="button"
        className="help-menu-button"
        aria-label={fa.supportMenu}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
      >
        <HeadphoneIcon />
      </button>
      {open ? (
        <div className="help-menu-panel" id={panelId} role="menu">
          <Link href="/contact" role="menuitem" onClick={() => setOpen(false)}>
            {fa.contactUs}
          </Link>
          <Link href="/about" role="menuitem" onClick={() => setOpen(false)}>
            {fa.aboutUs}
          </Link>
        </div>
      ) : null}
    </div>
  );
}

function HeadphoneIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden>
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M4 14v-2a8 8 0 0 1 16 0v2M5 14h2v5H5v-5Zm12 0h2v5h-2v-5Z"
      />
    </svg>
  );
}