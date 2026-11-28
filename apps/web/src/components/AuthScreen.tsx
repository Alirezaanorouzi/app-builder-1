"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fa } from "@/lib/dict";

type Step = "phone" | "code";

export function AuthScreen({ mode }: { mode: "login" | "register" }) {
  const purpose = mode === "login" ? "login" : "signup";
  const [step, setStep] = useState<Step>("phone");
  const [phone, setPhone] = useState("");
  const [phoneDisplay, setPhoneDisplay] = useState("");
  const [code, setCode] = useState("");
  const [challengeId, setChallengeId] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [resendIn, setResendIn] = useState(0);
  const isLogin = mode === "login";

  useEffect(() => {
    if (resendIn <= 0) return;
    const timer = window.setInterval(() => {
      setResendIn((value) => (value > 0 ? value - 1 : 0));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [resendIn]);

  async function sendOtp() {
    const nextPhone = phone.trim();
    if (!nextPhone || pending) return;
    setError("");
    setPending(true);
    try {
      const res = await fetch("/api/auth/otp/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone: nextPhone, purpose }),
      });
      const data = (await res.json().catch(() => null)) as {
        challengeId?: string;
        phoneDisplay?: string;
        resendAfterSec?: number;
        error?: string;
      } | null;
      if (!res.ok) {
        setError(data?.error ?? "خطا");
        return;
      }
      if (!data?.challengeId) {
        setError("خطا");
        return;
      }
      setChallengeId(data.challengeId);
      setPhoneDisplay(data.phoneDisplay?.trim() || nextPhone);
      setResendIn(data.resendAfterSec ?? 60);
      setCode("");
      setStep("code");
    } finally {
      setPending(false);
    }
  }

  async function verifyOtp(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending || !challengeId) return;
    setError("");
    setPending(true);
    try {
      const res = await fetch("/api/auth/otp/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ challengeId, code, purpose }),
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
      {step === "phone" ? (
        <form
          className="auth-card"
          onSubmit={(event) => {
            event.preventDefault();
            void sendOtp();
          }}
        >
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
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            required
          />
          {error ? <p className="auth-error">{error}</p> : null}
          <button className="auth-submit" type="submit" disabled={pending || !phone.trim()}>
            {fa.sendOtp}
          </button>
          <Link href={isLogin ? "/register" : "/login"}>{isLogin ? fa.register : fa.login}</Link>
        </form>
      ) : (
        <form className="auth-card" onSubmit={verifyOtp}>
          <h1>{fa.appName}</h1>
          <p>
            {fa.otpSent}
            {phoneDisplay ? (
              <>
                {" "}
                <span dir="ltr">({phoneDisplay})</span>
              </>
            ) : null}
          </p>
          <input
            className="auth-field"
            name="code"
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            placeholder={fa.otpCode}
            aria-label={fa.otpCode}
            dir="ltr"
            value={code}
            onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
            required
            maxLength={6}
          />
          {error ? <p className="auth-error">{error}</p> : null}
          <button className="auth-submit" type="submit" disabled={pending || code.length !== 6}>
            {isLogin ? fa.login : fa.register}
          </button>
          <button
            type="button"
            className="auth-text-btn"
            disabled={pending || resendIn > 0}
            onClick={() => void sendOtp()}
          >
            {resendIn > 0 ? `${fa.resendOtp} (${resendIn})` : fa.resendOtp}
          </button>
          <button
            type="button"
            className="auth-text-btn"
            onClick={() => {
              setStep("phone");
              setError("");
              setCode("");
              setChallengeId("");
              setPhoneDisplay("");
            }}
          >
            {fa.changePhone}
          </button>
        </form>
      )}
    </main>
  );
}