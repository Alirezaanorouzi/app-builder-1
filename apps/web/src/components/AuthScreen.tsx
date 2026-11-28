"use client";

import { useState } from "react";
import Link from "next/link";
import { fa } from "@/lib/dict";

export function AuthScreen({ mode }: { mode: "login" | "register" }) {
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const isLogin = mode === "login";

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setError("");
    setPending(true);
    const phone = new FormData(event.currentTarget).get("phone");
    try {
      const res = await fetch(isLogin ? "/api/auth/login" : "/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone }),
      });
      const data = (await res.json().catch(() => null)) as { projectId?: string; error?: string } | null;
      if (res.ok) {
        if (data?.projectId) window.location.href = `/projects/${data.projectId}`;
        else window.location.href = "/";
        return;
      }
      setError(data?.error ?? "خطا");
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="auth-screen">
      <form className="auth-card" onSubmit={onSubmit}>
        <h1>{fa.appName}</h1>
        <p>{isLogin ? fa.phoneLogin : fa.phoneRegister}</p>
        <input
          className="auth-field"
          name="phone"
          type="tel"
          inputMode="numeric"
          autoComplete="tel"
          placeholder={fa.phone}
          aria-label={fa.phone}
          dir="ltr"
          required
        />
        {error ? <p className="auth-error">{error}</p> : null}
        <button className="auth-submit" type="submit" disabled={pending}>
          {isLogin ? fa.login : fa.register}
        </button>
        <Link href={isLogin ? "/register" : "/login"}>{isLogin ? fa.register : fa.login}</Link>
      </form>
    </main>
  );
}
