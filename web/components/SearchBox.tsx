"use client";

import { useState } from "react";
import { getAccessToken } from "@/lib/auth";
import DocumentSelector from "@/components/DocumentSelector";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface SearchHit {
  document_id: string;
  filename: string;
  page: number;
  content: string;
  score: number;
}

interface SearchResponse {
  query: string;
  hits: SearchHit[];
  total: number;
  ai_summary: string | null;
}

export default function SearchBox() {
  const [query, setQuery] = useState("");
  const [docFilter, setDocFilter] = useState<string | null>(null);
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setError(null);

    try {
      const token = getAccessToken();
      let url = `${API}/api/v1/search?q=${encodeURIComponent(query)}&limit=10`;
      if (docFilter) url += `&document_id=${docFilter}`;
      const resp = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setLoading(false);
      if (!resp.ok) {
        setError(`Search failed: ${resp.status}`);
        return;
      }
      setResults(await resp.json());
      setExpanded(new Set());
    } catch {
      setLoading(false);
      setError("Search request failed");
    }
  }

  function toggleExpand(index: number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }

  return (
    <div>
      <DocumentSelector value={docFilter} onChange={setDocFilter} />

      <form
        onSubmit={handleSearch}
        style={{ display: "flex", gap: "0.5rem", marginBottom: "1.25rem" }}
      >
        <div style={{ position: "relative", flex: 1 }}>
          <svg
            width="18"
            height="18"
            fill="none"
            stroke="var(--gray-400)"
            strokeWidth="2"
            viewBox="0 0 24 24"
            style={{
              position: "absolute",
              left: "0.75rem",
              top: "50%",
              transform: "translateY(-50%)",
            }}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={
              docFilter
                ? "Search within selected document..."
                : "Search all documents..."
            }
            style={{ paddingLeft: "2.5rem" }}
          />
        </div>
        <button type="submit" disabled={loading} className="btn-primary">
          {loading ? "Searching..." : "Search"}
        </button>
      </form>

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

      {results && (
        <div>
          <p
            style={{
              color: "var(--gray-500)",
              fontSize: "0.85rem",
              marginBottom: "0.75rem",
            }}
          >
            {results.total} result{results.total !== 1 ? "s" : ""} for &ldquo;
            {results.query}&rdquo;
          </p>

          {results.ai_summary && (
            <div
              style={{
                padding: "1rem 1.25rem",
                marginBottom: "1rem",
                background: "var(--brand-50)",
                border: "1px solid var(--brand-200)",
                borderRadius: "var(--radius-md)",
                fontSize: "0.9rem",
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
                  AI Answer
                </span>
              </div>
              <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                {results.ai_summary}
              </p>
            </div>
          )}
          {results.hits.length === 0 && (
            <div style={{ padding: "2rem", textAlign: "center" }}>
              <p style={{ color: "var(--gray-400)" }}>
                No results found. Try different keywords.
              </p>
            </div>
          )}
          <div
            style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}
          >
            {results.hits.map((hit, i) => {
              const isExpanded = expanded.has(i);
              return (
                <div
                  key={i}
                  style={{
                    background: "var(--gray-50)",
                    border: "1px solid var(--gray-100)",
                    borderRadius: "var(--radius-md)",
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "0.65rem 1rem",
                      cursor: "pointer",
                    }}
                    onClick={() => toggleExpand(i)}
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "0.5rem",
                      }}
                    >
                      <svg
                        width="16"
                        height="16"
                        fill="none"
                        stroke="var(--brand-500)"
                        strokeWidth="2"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                        />
                      </svg>
                      <span
                        style={{
                          fontWeight: 500,
                          fontSize: "0.9rem",
                          color: "var(--gray-800)",
                        }}
                      >
                        {hit.filename}
                      </span>
                      <span
                        style={{
                          fontSize: "0.78rem",
                          color: "var(--gray-400)",
                        }}
                      >
                        p.{hit.page}
                      </span>
                    </div>
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "0.75rem",
                      }}
                    >
                      <span
                        style={{
                          fontSize: "0.75rem",
                          color: "var(--gray-400)",
                          background: "var(--gray-100)",
                          padding: "0.15rem 0.5rem",
                          borderRadius: "999px",
                        }}
                      >
                        {(hit.score * 100).toFixed(0)}%
                      </span>
                      <svg
                        width="16"
                        height="16"
                        fill="none"
                        stroke="var(--gray-400)"
                        strokeWidth="2"
                        viewBox="0 0 24 24"
                        style={{
                          transform: isExpanded
                            ? "rotate(180deg)"
                            : "rotate(0)",
                          transition: "transform 0.2s",
                        }}
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M19 9l-7 7-7-7"
                        />
                      </svg>
                    </div>
                  </div>
                  {isExpanded && (
                    <div
                      style={{
                        padding: "0.75rem 1rem",
                        borderTop: "1px solid var(--gray-200)",
                        background: "#fff",
                        fontSize: "0.88rem",
                        color: "var(--gray-600)",
                        lineHeight: 1.7,
                        whiteSpace: "pre-wrap",
                      }}
                    >
                      {hit.content}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
