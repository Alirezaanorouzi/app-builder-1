"use client";

import { useEffect } from "react";

export default function HomePage() {
  useEffect(() => {
    fetch("/api/enter")
      .then((res) => {
        if (res.status === 401) {
          window.location.href = "/register";
          return null;
        }
        return res.ok ? res.json() : null;
      })
      .then((data) => {
        if (data?.projectId) window.location.href = `/projects/${data.projectId}`;
      })
      .catch(() => {
        window.location.href = "/register";
      });
  }, []);

  return null;
}