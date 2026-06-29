"use client";

import { useEffect, useState } from "react";
import { getAccessToken } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface DocOption {
  id: string;
  filename: string;
  status: string;
}

interface Props {
  value: string | null;
  onChange: (docId: string | null) => void;
}

export default function DocumentSelector({ value, onChange }: Props) {
  const [docs, setDocs] = useState<DocOption[]>([]);

  useEffect(() => {
    const token = getAccessToken();
    if (!token) return;
    fetch(`${API}/api/v1/documents`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => (r.ok ? r.json() : []))
      .then((data) =>
        setDocs(
          data.filter(
            (d: DocOption) => d.status === "ready" || d.status === "indexed",
          ),
        ),
      )
      .catch(() => {});
  }, []);

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "0.5rem",
        marginBottom: "1rem",
      }}
    >
      <svg
        width="16"
        height="16"
        fill="none"
        stroke="var(--gray-400)"
        strokeWidth="2"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
        />
      </svg>
      <select
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value || null)}
        style={{
          flex: 1,
          padding: "0.5rem 0.75rem",
          border: "1.5px solid var(--gray-200)",
          borderRadius: "var(--radius-md)",
          fontSize: "0.875rem",
          background: "#fff",
          color: "var(--gray-700)",
          outline: "none",
          cursor: "pointer",
        }}
      >
        <option value="">All documents</option>
        {docs.map((d) => (
          <option key={d.id} value={d.id}>
            {d.filename}
          </option>
        ))}
      </select>
    </div>
  );
}
