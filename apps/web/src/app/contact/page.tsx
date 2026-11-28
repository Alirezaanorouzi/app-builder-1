"use client";

import { useEffect, useState } from "react";
import { InfoScreen } from "@/components/InfoScreen";
import { fa } from "@/lib/dict";

export default function ContactPage() {
  const [phone, setPhone] = useState<string | null>(null);
  const [tel, setTel] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/site/support")
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        setPhone(typeof data?.phone === "string" ? data.phone : null);
        setTel(typeof data?.tel === "string" ? data.tel : null);
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <InfoScreen title={fa.contactTitle}>
      <p className="info-lead">{fa.contactLead}</p>
      {loading ? (
        <p className="info-muted">…</p>
      ) : phone && tel ? (
        <a className="info-phone" href={`tel:${tel}`} dir="ltr">
          {phone}
        </a>
      ) : (
        <p className="info-muted">{fa.contactPhoneMissing}</p>
      )}
      <p className="info-note">{fa.contactNote}</p>
    </InfoScreen>
  );
}