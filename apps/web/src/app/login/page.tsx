"use client";

import { useState } from "react";
import Link from "next/link";
import { fa } from "@/lib/dict";

export default function LoginPage() {
  const [error, setError] = useState("");

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: fd.get("email"),
        password: fd.get("password"),
      }),
    });
    if (res.ok) window.location.href = "/";
    else setError((await res.json()).error ?? "خطا");
  }

  return (
    <main className="container">
      <h1>{fa.login}</h1>
      <form onSubmit={onSubmit}>
        <input className="input" name="email" type="email" placeholder={fa.email} required />
        <input className="input" name="password" type="password" placeholder={fa.password} required />
        {error ? <p style={{ color: "#f87171" }}>{error}</p> : null}
        <button className="btn" type="submit">
          {fa.login}
        </button>
      </form>
      <p>
        <Link href="/register">{fa.register}</Link>
      </p>
    </main>
  );
}