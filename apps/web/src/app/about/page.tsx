"use client";

import { InfoScreen } from "@/components/InfoScreen";
import { fa } from "@/lib/dict";

export default function AboutPage() {
  return (
    <InfoScreen title={fa.aboutTitle}>
      <p className="info-lead">{fa.aboutLead}</p>
      <ul className="info-list">
        {fa.aboutPoints.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </InfoScreen>
  );
}