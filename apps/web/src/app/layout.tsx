import type { Metadata } from "next";
import "./globals.css";
import { fa } from "@/lib/dict";

export const metadata: Metadata = {
  title: fa.appName,
  description: "ساخت اپ با هوش مصنوعی",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fa" dir="rtl">
      <body>{children}</body>
    </html>
  );
}