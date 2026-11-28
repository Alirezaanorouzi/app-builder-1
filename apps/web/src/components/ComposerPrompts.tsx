"use client";

import { useEffect, useRef } from "react";
import { fa } from "@/lib/dict";

const SCROLL_PX_PER_SEC = 32;

export function ComposerPrompts({
  visible,
  onPick,
}: {
  visible: boolean;
  onPick: (text: string) => void;
}) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const pausedRef = useRef(false);
  const rafRef = useRef(0);

  const prompts = fa.composerPrompts;
  const items = [...prompts, ...prompts];

  useEffect(() => {
    if (!visible) return;

    const viewport = viewportRef.current;
    const track = trackRef.current;
    if (!viewport || !track) return;

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reducedMotion) return;

    let lastTs = performance.now();

    const tick = (now: number) => {
      const dt = Math.min(now - lastTs, 48);
      lastTs = now;

      if (!pausedRef.current && track.scrollWidth > 0) {
        viewport.scrollLeft += (SCROLL_PX_PER_SEC * dt) / 1000;
        const loop = track.scrollWidth / 2;
        if (loop > 0 && viewport.scrollLeft >= loop) {
          viewport.scrollLeft -= loop;
        }
      }

      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [visible]);

  if (!visible) return null;

  return (
    <div className="composer-prompts" aria-label={fa.composerPromptsLabel}>
      <div
        ref={viewportRef}
        className="composer-prompts-viewport"
        onMouseEnter={() => {
          pausedRef.current = true;
        }}
        onMouseLeave={() => {
          pausedRef.current = false;
        }}
        onTouchStart={() => {
          pausedRef.current = true;
        }}
        onTouchEnd={() => {
          pausedRef.current = false;
        }}
      >
        <div ref={trackRef} className="composer-prompts-track">
          {items.map((label, index) => (
            <button
              key={`${index}-${label}`}
              type="button"
              className="composer-prompt-chip"
              onClick={() => onPick(label)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}