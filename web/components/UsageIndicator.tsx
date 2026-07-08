"use client";

import { useEffect, useState } from "react";
import { getAccessToken } from "@/lib/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Usage {
  plan: string;
  monthly_page_quota: number;
  pages_used_this_month: number;
  remaining_pages: number;
}

export default function UsageIndicator() {
  const [usage, setUsage] = useState<Usage | null>(null);

  useEffect(() => {
    const token = getAccessToken();
    if (!token) return;
    fetch(`${API_BASE}/api/v1/users/me/usage`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((data: Usage | null) => setUsage(data))
      .catch(() => setUsage(null));
  }, []);

  if (!usage) return null;

  const ratio =
    usage.monthly_page_quota > 0
      ? usage.pages_used_this_month / usage.monthly_page_quota
      : 0;
  const exhausted = ratio >= 1;
  const warning = ratio >= 0.8;
  const color = exhausted
    ? "var(--red-600, #dc2626)"
    : warning
      ? "var(--amber-600, #d97706)"
      : "var(--gray-500, #6b7280)";

  return (
    <span
      title={
        exhausted
          ? "Monthly page quota exhausted — uploads are paused until the 1st"
          : `Plan: ${usage.plan} — ${usage.remaining_pages} pages remaining this month`
      }
      style={{
        fontSize: "0.75rem",
        fontWeight: 500,
        color,
        whiteSpace: "nowrap",
      }}
    >
      {usage.pages_used_this_month} / {usage.monthly_page_quota} pages
      {exhausted ? " — quota exhausted" : ""}
    </span>
  );
}
