"use client";

import { useEffect, useState } from "react";
import { getAccessToken } from "@/lib/auth";
import { diff_match_patch } from "diff-match-patch";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface DocOption {
  id: string;
  filename: string;
  status: string;
}
interface CompareDoc {
  id: string;
  filename: string;
  extracted_text: string | null;
  page_count: number | null;
}
interface CompareResult {
  doc_a: CompareDoc;
  doc_b: CompareDoc;
  ai_summary: string | null;
}

export default function DocumentCompare() {
  const [docs, setDocs] = useState<DocOption[]>([]);
  const [docA, setDocA] = useState("");
  const [docB, setDocB] = useState("");
  const [result, setResult] = useState<CompareResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  async function handleCompare() {
    if (!docA || !docB) return;
    setLoading(true);
    setError(null);
    setResult(null);
    const token = getAccessToken();
    try {
      const res = await fetch(`${API}/api/v1/documents/compare`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ doc_a_id: docA, doc_b_id: docB }),
      });
      if (!res.ok) {
        setError(`Compare failed: ${res.status}`);
        return;
      }
      setResult(await res.json());
    } catch {
      setError("Failed to compare documents");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      {/* Document selectors */}
      <div
        style={{
          display: "flex",
          gap: "0.75rem",
          marginBottom: "1rem",
          flexWrap: "wrap",
          alignItems: "flex-end",
        }}
      >
        <div style={{ flex: 1, minWidth: 180 }}>
          <label
            style={{
              fontSize: "0.75rem",
              color: "var(--gray-500)",
              display: "block",
              marginBottom: "0.2rem",
            }}
          >
            Document A
          </label>
          <select
            value={docA}
            onChange={(e) => setDocA(e.target.value)}
            style={{ fontSize: "0.85rem" }}
          >
            <option value="">Select first document...</option>
            {docs.map((d) => (
              <option key={d.id} value={d.id}>
                {d.filename}
              </option>
            ))}
          </select>
        </div>
        <div style={{ flex: 1, minWidth: 180 }}>
          <label
            style={{
              fontSize: "0.75rem",
              color: "var(--gray-500)",
              display: "block",
              marginBottom: "0.2rem",
            }}
          >
            Document B
          </label>
          <select
            value={docB}
            onChange={(e) => setDocB(e.target.value)}
            style={{ fontSize: "0.85rem" }}
          >
            <option value="">Select second document...</option>
            {docs
              .filter((d) => d.id !== docA)
              .map((d) => (
                <option key={d.id} value={d.id}>
                  {d.filename}
                </option>
              ))}
          </select>
        </div>
        <button
          onClick={handleCompare}
          disabled={!docA || !docB || docA === docB || loading}
          className="btn-primary"
          style={{ whiteSpace: "nowrap" }}
        >
          {loading ? "Comparing..." : "Compare"}
        </button>
      </div>

      {error && (
        <div
          style={{
            padding: "0.6rem 0.85rem",
            background: "var(--red-50)",
            color: "var(--red-700)",
            borderRadius: "var(--radius-sm)",
            fontSize: "0.85rem",
            marginBottom: "1rem",
          }}
        >
          {error}
        </div>
      )}

      {result && (
        <div className="fade-in">
          {/* AI Summary */}
          {result.ai_summary && (
            <div
              style={{
                padding: "1rem 1.25rem",
                marginBottom: "1rem",
                background: "var(--brand-50)",
                border: "1px solid var(--brand-200)",
                borderRadius: "var(--radius-md)",
                fontSize: "0.88rem",
                lineHeight: 1.7,
                color: "var(--gray-700)",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.4rem",
                  marginBottom: "0.5rem",
                }}
              >
                <svg
                  width="16"
                  height="16"
                  fill="none"
                  stroke="var(--brand-600)"
                  strokeWidth="2"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M13 10V3L4 14h7v7l9-11h-7z"
                  />
                </svg>
                <span
                  style={{
                    fontWeight: 600,
                    fontSize: "0.82rem",
                    color: "var(--brand-700)",
                  }}
                >
                  AI Comparison Summary
                </span>
              </div>
              <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                {result.ai_summary}
              </p>
            </div>
          )}

          {/* Side-by-side diff */}
          <DiffView
            textA={result.doc_a.extracted_text || ""}
            textB={result.doc_b.extracted_text || ""}
            nameA={result.doc_a.filename}
            nameB={result.doc_b.filename}
          />
        </div>
      )}
    </div>
  );
}

function DiffView({
  textA,
  textB,
  nameA,
  nameB,
}: {
  textA: string;
  textB: string;
  nameA: string;
  nameB: string;
}) {
  const dmp = new diff_match_patch();
  const diffs = dmp.diff_main(textA, textB);
  dmp.diff_cleanupSemantic(diffs);

  const addCount = diffs.filter(([op]) => op === 1).length;
  const removeCount = diffs.filter(([op]) => op === -1).length;

  function renderSide(side: "left" | "right") {
    return diffs.map(([op, text], i) => {
      if (side === "left") {
        if (op === 0) return <span key={i}>{text}</span>;
        if (op === -1)
          return (
            <span
              key={i}
              style={{
                background: "#fecaca",
                textDecoration: "line-through",
                borderRadius: "2px",
              }}
            >
              {text}
            </span>
          );
        return null;
      } else {
        if (op === 0) return <span key={i}>{text}</span>;
        if (op === 1)
          return (
            <span
              key={i}
              style={{ background: "#bbf7d0", borderRadius: "2px" }}
            >
              {text}
            </span>
          );
        return null;
      }
    });
  }

  return (
    <div>
      {/* Stats bar */}
      <div
        style={{
          display: "flex",
          gap: "1rem",
          marginBottom: "0.75rem",
          fontSize: "0.8rem",
          color: "var(--gray-500)",
        }}
      >
        <span style={{ color: "var(--red-600)" }}>- {removeCount} removed</span>
        <span style={{ color: "var(--green-600)" }}>+ {addCount} added</span>
      </div>

      {/* Side by side panels */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "0.75rem",
        }}
      >
        {/* Left — Doc A */}
        <div>
          <div
            style={{
              padding: "0.5rem 0.75rem",
              background: "var(--red-50)",
              borderRadius: "var(--radius-md) var(--radius-md) 0 0",
              border: "1px solid var(--gray-200)",
              borderBottom: "none",
              fontSize: "0.8rem",
              fontWeight: 600,
              color: "var(--red-700)",
            }}
          >
            {nameA}
          </div>
          <div
            style={{
              padding: "0.85rem",
              border: "1px solid var(--gray-200)",
              borderRadius: "0 0 var(--radius-md) var(--radius-md)",
              fontSize: "0.82rem",
              lineHeight: 1.8,
              color: "var(--gray-700)",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              maxHeight: 500,
              overflowY: "auto",
              background: "#fff",
            }}
          >
            {textA ? (
              renderSide("left")
            ) : (
              <span style={{ color: "var(--gray-400)" }}>No text</span>
            )}
          </div>
        </div>

        {/* Right — Doc B */}
        <div>
          <div
            style={{
              padding: "0.5rem 0.75rem",
              background: "var(--green-50)",
              borderRadius: "var(--radius-md) var(--radius-md) 0 0",
              border: "1px solid var(--gray-200)",
              borderBottom: "none",
              fontSize: "0.8rem",
              fontWeight: 600,
              color: "var(--green-700)",
            }}
          >
            {nameB}
          </div>
          <div
            style={{
              padding: "0.85rem",
              border: "1px solid var(--gray-200)",
              borderRadius: "0 0 var(--radius-md) var(--radius-md)",
              fontSize: "0.82rem",
              lineHeight: 1.8,
              color: "var(--gray-700)",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              maxHeight: 500,
              overflowY: "auto",
              background: "#fff",
            }}
          >
            {textB ? (
              renderSide("right")
            ) : (
              <span style={{ color: "var(--gray-400)" }}>No text</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
