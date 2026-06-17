"use client";

import { useState } from "react";
import { getAccessToken } from "@/lib/auth";

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
}

export default function SearchBox() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setError(null);

    const token = getAccessToken();
    const resp = await fetch(
      `${API}/api/v1/search?q=${encodeURIComponent(query)}&limit=10`,
      {
        headers: { Authorization: `Bearer ${token}` },
      },
    );

    setLoading(false);

    if (!resp.ok) {
      setError(`Search failed: ${resp.status}`);
      return;
    }

    setResults(await resp.json());
  }

  return (
    <div style={{ marginTop: "2rem" }}>
      <form
        onSubmit={handleSearch}
        style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem" }}
      >
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search documents…"
          style={{ flex: 1, padding: "0.5rem", fontSize: "1rem" }}
        />
        <button
          type="submit"
          disabled={loading}
          style={{ padding: "0.5rem 1.5rem" }}
        >
          {loading ? "Searching…" : "Search"}
        </button>
      </form>

      {error && <p style={{ color: "red" }}>{error}</p>}

      {results && (
        <div>
          <p style={{ color: "#666", fontSize: "0.9rem" }}>
            {results.total} result{results.total !== 1 ? "s" : ""} for &ldquo;
            {results.query}&rdquo;
          </p>
          {results.hits.length === 0 && (
            <p style={{ color: "#999" }}>No results found.</p>
          )}
          <ul style={{ listStyle: "none", padding: 0 }}>
            {results.hits.map((hit, i) => (
              <li
                key={i}
                style={{
                  border: "1px solid #e0e0e0",
                  borderRadius: 6,
                  padding: "0.75rem 1rem",
                  marginBottom: "0.75rem",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    marginBottom: "0.25rem",
                  }}
                >
                  <strong>{hit.filename}</strong>
                  <span style={{ color: "#888", fontSize: "0.85rem" }}>
                    p.{hit.page} · score {hit.score}
                  </span>
                </div>
                <p
                  style={{
                    margin: 0,
                    fontSize: "0.9rem",
                    color: "#444",
                    whiteSpace: "pre-wrap",
                    maxHeight: "4em",
                    overflow: "hidden",
                  }}
                >
                  {hit.content}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
