"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { fa } from "@/lib/dict";

export function InfoScreen({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <main className="info-screen">
      <div className="info-card">
        <Link className="info-back" href="/">
          {fa.backHome}
        </Link>
        <h1>{title}</h1>
        {children}
      </div>
    </main>
  );
}