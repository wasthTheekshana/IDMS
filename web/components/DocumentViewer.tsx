"use client";

import { useEffect, useState } from "react";
import { getAccessToken } from "@/lib/auth";
import type { Document } from "./DocumentList";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface DocDetail extends Document {
  preview_url?: string | null;
}

const BADGE_CLASS: Record<string, string> = {
  ready: "badge-ready",
  indexed: "badge-indexed",
  processing: "badge-processing",
  uploaded: "badge-uploaded",
  failed: "badge-failed",
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DocumentViewer({ doc }: { doc: Document }) {
  const [detail, setDetail] = useState<DocDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"preview" | "text">("preview");
  const [textSearch, setTextSearch] = useState("");

  useEffect(() => {
    const token = getAccessToken();
    fetch(`${API}/api/v1/documents/${doc.id}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((data) => {
        setDetail(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [doc.id]);

  if (loading) {
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: "calc(100vh - 56px)",
        }}
      >
        <div style={{ textAlign: "center" }}>
          <div
            style={{
              width: 32,
              height: 32,
              border: "3px solid var(--brand-200)",
              borderTopColor: "var(--brand-500)",
              borderRadius: "50%",
              animation: "spin 0.6s linear infinite",
              margin: "0 auto 0.75rem",
            }}
          />
          <p style={{ color: "var(--gray-400)", fontSize: "0.85rem" }}>
            Loading document...
          </p>
        </div>
      </div>
    );
  }

  const isPdf = doc.mime_type === "application/pdf";
  const isImage = doc.mime_type.startsWith("image/");
  const canPreview = (isPdf || isImage) && detail?.preview_url;

  const extractedText = detail?.extracted_text || "";
  const pages = extractedText.split("\n\n---PAGE---\n\n").filter(Boolean);

  function highlightText(text: string, search: string) {
    if (!search.trim()) return text;
    const regex = new RegExp(
      `(${search.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`,
      "gi",
    );
    const parts = text.split(regex);
    return parts.map((part, i) =>
      regex.test(part) ? (
        <mark
          key={i}
          style={{
            background: "#fef08a",
            padding: "0 2px",
            borderRadius: "2px",
          }}
        >
          {part}
        </mark>
      ) : (
        part
      ),
    );
  }

  return (
    <div className="split-view fade-in">
      {/* Left: Original document preview */}
      <div className="split-left">
        <div
          style={{
            padding: "0.75rem 1rem",
            borderBottom: "1px solid var(--gray-200)",
            background: "#fff",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div style={{ display: "flex", gap: "4px" }}>
            {canPreview && (
              <button
                onClick={() => setActiveTab("preview")}
                className={
                  activeTab === "preview" ? "btn-primary" : "btn-secondary"
                }
                style={{ fontSize: "0.78rem", padding: "0.3rem 0.7rem" }}
              >
                Original
              </button>
            )}
            <button
              onClick={() => setActiveTab("text")}
              className={
                activeTab === "text" || !canPreview
                  ? "btn-primary"
                  : "btn-secondary"
              }
              style={{ fontSize: "0.78rem", padding: "0.3rem 0.7rem" }}
            >
              Extracted Text
            </button>
          </div>
          {activeTab === "text" && (
            <input
              type="text"
              value={textSearch}
              onChange={(e) => setTextSearch(e.target.value)}
              placeholder="Find in text..."
              style={{
                width: 180,
                fontSize: "0.8rem",
                padding: "0.3rem 0.6rem",
              }}
            />
          )}
        </div>

        {activeTab === "preview" && canPreview ? (
          <div style={{ height: "calc(100% - 49px)" }}>
            {isPdf ? (
              <iframe
                src={detail!.preview_url!}
                style={{ width: "100%", height: "100%", border: "none" }}
                title="Document preview"
              />
            ) : (
              <div
                style={{
                  padding: "1rem",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  height: "100%",
                }}
              >
                <img
                  src={detail!.preview_url!}
                  alt={doc.filename}
                  style={{
                    maxWidth: "100%",
                    maxHeight: "100%",
                    objectFit: "contain",
                    borderRadius: "var(--radius-sm)",
                  }}
                />
              </div>
            )}
          </div>
        ) : (
          <div
            style={{
              padding: "1rem",
              height: "calc(100% - 49px)",
              overflowY: "auto",
            }}
          >
            {pages.length === 0 ? (
              <div
                style={{
                  textAlign: "center",
                  padding: "3rem 1rem",
                  color: "var(--gray-400)",
                }}
              >
                <p>No extracted text available</p>
                <p style={{ fontSize: "0.85rem", marginTop: "0.25rem" }}>
                  {doc.status === "processing"
                    ? "Document is still being processed..."
                    : ""}
                </p>
              </div>
            ) : (
              pages.map((page, i) => (
                <div key={i} style={{ marginBottom: "1.5rem" }}>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.5rem",
                      marginBottom: "0.5rem",
                      padding: "0.3rem 0.6rem",
                      background: "var(--brand-50)",
                      borderRadius: "var(--radius-sm)",
                      fontSize: "0.75rem",
                      fontWeight: 600,
                      color: "var(--brand-700)",
                    }}
                  >
                    Page {i + 1}
                  </div>
                  <div
                    style={{
                      background: "#fff",
                      border: "1px solid var(--gray-200)",
                      borderRadius: "var(--radius-md)",
                      padding: "1rem",
                      fontSize: "0.85rem",
                      lineHeight: 1.8,
                      color: "var(--gray-700)",
                      whiteSpace: "pre-wrap",
                      wordBreak: "break-word",
                    }}
                  >
                    {highlightText(page, textSearch)}
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* Right: Document info + actions */}
      <div className="split-right">
        <div style={{ padding: "1.25rem" }}>
          {/* Meta info */}
          <div style={{ marginBottom: "1.5rem" }}>
            <h3
              style={{
                fontSize: "0.95rem",
                fontWeight: 600,
                color: "var(--gray-900)",
                marginBottom: "1rem",
              }}
            >
              Details
            </h3>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "0.75rem",
              }}
            >
              {[
                {
                  label: "Type",
                  value: doc.mime_type.split("/").pop()?.toUpperCase(),
                },
                { label: "Size", value: formatBytes(doc.size_bytes) },
                { label: "Pages", value: doc.page_count ?? "—" },
                { label: "Status", value: null, badge: doc.status },
                {
                  label: "Uploaded",
                  value: new Date(doc.created_at).toLocaleDateString(),
                },
                { label: "Chunks", value: pages.length || "—" },
              ].map((item, i) => (
                <div
                  key={i}
                  style={{
                    padding: "0.6rem 0.75rem",
                    background: "var(--gray-50)",
                    borderRadius: "var(--radius-sm)",
                  }}
                >
                  <p
                    style={{
                      fontSize: "0.7rem",
                      color: "var(--gray-400)",
                      textTransform: "uppercase",
                      letterSpacing: "0.04em",
                      marginBottom: "0.15rem",
                    }}
                  >
                    {item.label}
                  </p>
                  {item.badge ? (
                    <span
                      className={`badge ${BADGE_CLASS[item.badge] ?? "badge-uploaded"}`}
                    >
                      {item.badge}
                    </span>
                  ) : (
                    <p
                      style={{
                        fontSize: "0.85rem",
                        fontWeight: 500,
                        color: "var(--gray-800)",
                      }}
                    >
                      {item.value}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Actions */}
          <div style={{ marginBottom: "1.5rem" }}>
            <h3
              style={{
                fontSize: "0.95rem",
                fontWeight: 600,
                color: "var(--gray-900)",
                marginBottom: "0.75rem",
              }}
            >
              Actions
            </h3>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "0.4rem",
              }}
            >
              {detail?.preview_url && (
                <a
                  href={detail.preview_url}
                  download={doc.filename}
                  target="_blank"
                  rel="noreferrer"
                  style={{ textDecoration: "none" }}
                >
                  <button
                    className="btn-secondary"
                    style={{
                      width: "100%",
                      display: "flex",
                      alignItems: "center",
                      gap: "0.4rem",
                      justifyContent: "center",
                      fontSize: "0.82rem",
                    }}
                  >
                    <svg
                      width="14"
                      height="14"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                      />
                    </svg>
                    Download Original
                  </button>
                </a>
              )}
              <DocExportButton docId={doc.id} />
            </div>
          </div>

          {/* Quick AI actions */}
          <div style={{ marginBottom: "1.5rem" }}>
            <h3
              style={{
                fontSize: "0.95rem",
                fontWeight: 600,
                color: "var(--gray-900)",
                marginBottom: "0.75rem",
              }}
            >
              AI Actions
            </h3>
            <DocAiPanel docId={doc.id} />
          </div>
        </div>
      </div>
    </div>
  );
}

function DocAiPanel({ docId }: { docId: string }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<"ask" | "summarize">("ask");

  async function handleAsk() {
    if (mode === "ask" && !question.trim()) return;
    setLoading(true);
    setAnswer(null);
    const token = getAccessToken();

    try {
      const url =
        mode === "summarize"
          ? `${API}/api/v1/ai/documents/${docId}/summarize`
          : `${API}/api/v1/ai/documents/${docId}/ask`;

      const resp = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: mode === "ask" ? JSON.stringify({ question }) : undefined,
      });

      if (resp.ok) {
        const data = await resp.json();
        setAnswer(data.answer || data.summary || "No response");
      } else {
        setAnswer(`Error: ${resp.status}`);
      }
    } catch {
      setAnswer("Failed to connect");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <div style={{ display: "flex", gap: "4px", marginBottom: "0.75rem" }}>
        <button
          onClick={() => setMode("ask")}
          className={mode === "ask" ? "btn-primary" : "btn-secondary"}
          style={{ fontSize: "0.78rem", padding: "0.3rem 0.7rem" }}
        >
          Ask Question
        </button>
        <button
          onClick={() => {
            setMode("summarize");
          }}
          className={mode === "summarize" ? "btn-primary" : "btn-secondary"}
          style={{ fontSize: "0.78rem", padding: "0.3rem 0.7rem" }}
        >
          Summarize
        </button>
      </div>

      {mode === "ask" && (
        <div
          style={{ display: "flex", gap: "0.4rem", marginBottom: "0.75rem" }}
        >
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask about this document..."
            onKeyDown={(e) => {
              if (e.key === "Enter") handleAsk();
            }}
            style={{ fontSize: "0.85rem" }}
          />
          <button
            onClick={handleAsk}
            disabled={loading || !question.trim()}
            className="btn-primary"
            style={{ whiteSpace: "nowrap" }}
          >
            {loading ? "..." : "Ask"}
          </button>
        </div>
      )}

      {mode === "summarize" && !answer && (
        <button
          onClick={handleAsk}
          disabled={loading}
          className="btn-secondary"
          style={{ width: "100%", marginBottom: "0.75rem" }}
        >
          {loading ? "Generating summary..." : "Generate Summary"}
        </button>
      )}

      {answer && (
        <div
          style={{
            padding: "0.85rem",
            background: "var(--brand-50)",
            border: "1px solid var(--brand-200)",
            borderRadius: "var(--radius-md)",
            fontSize: "0.85rem",
            lineHeight: 1.7,
            color: "var(--gray-700)",
            whiteSpace: "pre-wrap",
            maxHeight: 300,
            overflowY: "auto",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.35rem",
              marginBottom: "0.5rem",
            }}
          >
            <svg
              width="14"
              height="14"
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
                fontSize: "0.78rem",
                color: "var(--brand-700)",
              }}
            >
              {mode === "summarize" ? "Summary" : "Answer"}
            </span>
          </div>
          {answer}
        </div>
      )}
    </div>
  );
}

function DocExportButton({ docId }: { docId: string }) {
  const [loading, setLoading] = useState(false);

  async function handleExport() {
    setLoading(true);
    const token = getAccessToken();
    try {
      const res = await fetch(`${API}/api/v1/documents/bulk/export`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ document_ids: [docId] }),
      });
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download =
          res.headers
            .get("content-disposition")
            ?.split("filename=")[1]
            ?.replace(/"/g, "") || "document-export.xlsx";
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }

  return (
    <button
      onClick={handleExport}
      disabled={loading}
      className="btn-secondary"
      style={{
        width: "100%",
        display: "flex",
        alignItems: "center",
        gap: "0.4rem",
        justifyContent: "center",
        fontSize: "0.82rem",
      }}
    >
      <svg
        width="14"
        height="14"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
        />
      </svg>
      {loading ? "Exporting..." : "Export to Excel"}
    </button>
  );
}
