"use client";

import { useEffect, useState, useCallback } from "react";
import { getAccessToken } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Document {
  id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  status: string;
  page_count: number | null;
  error_message: string | null;
  created_at: string;
  extracted_text?: string | null;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const BADGE_CLASS: Record<string, string> = {
  ready: "badge-ready",
  indexed: "badge-indexed",
  processing: "badge-processing",
  uploaded: "badge-uploaded",
  failed: "badge-failed",
};

const TYPE_ICON: Record<string, string> = {
  "application/pdf": "PDF",
  "image/jpeg": "JPG",
  "image/png": "PNG",
  "image/tiff": "TIFF",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
    "DOCX",
};

interface Props {
  onSelectDocument?: (doc: Document | null) => void;
  selectedId?: string | null;
  refreshKey?: number;
}

async function bulkAction(
  endpoint: string,
  ids: string[],
  downloadFilename?: string,
) {
  const token = getAccessToken();
  const res = await fetch(`${API}/api/v1/documents/bulk/${endpoint}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ document_ids: ids }),
  });
  if (!res.ok) throw new Error(await res.text());
  if (downloadFilename) {
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download =
      res.headers
        .get("content-disposition")
        ?.split("filename=")[1]
        ?.replace(/"/g, "") || downloadFilename;
    a.click();
    URL.revokeObjectURL(url);
  }
  return res;
}

export default function DocumentList({ onSelectDocument, refreshKey }: Props) {
  const [docs, setDocs] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const fetchDocs = useCallback(async () => {
    const token = getAccessToken();
    if (!token) return;
    try {
      const res = await fetch(`${API}/api/v1/documents`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setDocs(await res.json());
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDocs();
  }, [fetchDocs, refreshKey]);

  function toggleSelect(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    if (selected.size === docs.length) setSelected(new Set());
    else setSelected(new Set(docs.map((d) => d.id)));
  }

  async function handleBulkDownload() {
    setActionLoading("download");
    try {
      await bulkAction("download", Array.from(selected), "documents.zip");
    } catch {
      /* ignore */
    } finally {
      setActionLoading(null);
    }
  }

  async function handleBulkExport() {
    setActionLoading("export");
    try {
      await bulkAction("export", Array.from(selected), "documents.xlsx");
    } catch {
      /* ignore */
    } finally {
      setActionLoading(null);
    }
  }

  async function handleBulkDelete() {
    if (!confirm(`Delete ${selected.size} document(s)? This cannot be undone.`))
      return;
    setActionLoading("delete");
    try {
      await bulkAction("delete", Array.from(selected));
      setSelected(new Set());
      await fetchDocs();
    } catch {
      /* ignore */
    } finally {
      setActionLoading(null);
    }
  }

  if (loading)
    return (
      <div
        style={{
          padding: "3rem",
          textAlign: "center",
          color: "var(--gray-400)",
        }}
      >
        Loading...
      </div>
    );

  if (docs.length === 0) {
    return (
      <div style={{ padding: "4rem 2rem", textAlign: "center" }}>
        <svg
          width="56"
          height="56"
          fill="none"
          stroke="var(--gray-300)"
          strokeWidth="1.2"
          viewBox="0 0 24 24"
          style={{ margin: "0 auto 1rem" }}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
          />
        </svg>
        <p
          style={{
            fontWeight: 500,
            color: "var(--gray-500)",
            marginBottom: "0.25rem",
          }}
        >
          No documents yet
        </p>
        <p style={{ fontSize: "0.85rem", color: "var(--gray-400)" }}>
          Upload your first document to get started
        </p>
      </div>
    );
  }

  const hasSelected = selected.size > 0;

  return (
    <div>
      {/* Header + bulk actions bar */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "0.75rem",
          flexWrap: "wrap",
          gap: "0.5rem",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.4rem",
              cursor: "pointer",
              fontSize: "0.8rem",
              color: "var(--gray-500)",
            }}
          >
            <input
              type="checkbox"
              checked={selected.size === docs.length && docs.length > 0}
              onChange={toggleAll}
              style={{ accentColor: "var(--brand-500)" }}
            />
            {hasSelected
              ? `${selected.size} selected`
              : `${docs.length} document${docs.length !== 1 ? "s" : ""}`}
          </label>
        </div>

        <div style={{ display: "flex", gap: "0.35rem", alignItems: "center" }}>
          {hasSelected && (
            <>
              <button
                onClick={handleBulkDownload}
                disabled={actionLoading === "download"}
                className="btn-secondary"
                style={{
                  fontSize: "0.78rem",
                  padding: "0.3rem 0.65rem",
                  display: "flex",
                  alignItems: "center",
                  gap: "0.3rem",
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
                {actionLoading === "download" ? "..." : "Download ZIP"}
              </button>
              <button
                onClick={handleBulkExport}
                disabled={actionLoading === "export"}
                className="btn-secondary"
                style={{
                  fontSize: "0.78rem",
                  padding: "0.3rem 0.65rem",
                  display: "flex",
                  alignItems: "center",
                  gap: "0.3rem",
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
                {actionLoading === "export" ? "..." : "Export Excel"}
              </button>
              <button
                onClick={handleBulkDelete}
                disabled={actionLoading === "delete"}
                className="btn-danger"
                style={{
                  fontSize: "0.78rem",
                  padding: "0.3rem 0.65rem",
                  display: "flex",
                  alignItems: "center",
                  gap: "0.3rem",
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
                    d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                  />
                </svg>
                {actionLoading === "delete" ? "..." : "Delete"}
              </button>
            </>
          )}
          {!hasSelected && (
            <button
              onClick={fetchDocs}
              className="btn-ghost"
              style={{ fontSize: "0.8rem" }}
            >
              Refresh
            </button>
          )}
        </div>
      </div>

      {/* Document cards */}
      <div style={{ display: "grid", gap: "0.5rem" }}>
        {docs.map((doc) => {
          const isChecked = selected.has(doc.id);
          return (
            <div
              key={doc.id}
              className="card"
              style={{
                padding: "0.85rem 1rem",
                cursor: "pointer",
                transition: "all 0.12s",
                display: "flex",
                alignItems: "center",
                gap: "0.75rem",
                borderColor: isChecked ? "var(--brand-300)" : undefined,
                background: isChecked ? "var(--brand-50)" : undefined,
              }}
              onMouseEnter={(e) => {
                if (!isChecked) {
                  e.currentTarget.style.borderColor = "var(--brand-200)";
                  e.currentTarget.style.boxShadow = "var(--shadow-md)";
                }
              }}
              onMouseLeave={(e) => {
                if (!isChecked) {
                  e.currentTarget.style.borderColor = "var(--gray-200)";
                  e.currentTarget.style.boxShadow = "var(--shadow-sm)";
                }
              }}
            >
              {/* Checkbox */}
              <input
                type="checkbox"
                checked={isChecked}
                onClick={(e) => toggleSelect(doc.id, e)}
                onChange={() => {}}
                style={{
                  accentColor: "var(--brand-500)",
                  cursor: "pointer",
                  flexShrink: 0,
                }}
              />

              {/* Card body — click opens viewer */}
              <div
                onClick={() => onSelectDocument?.(doc)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.75rem",
                  flex: 1,
                  minWidth: 0,
                }}
              >
                <div
                  style={{
                    width: 42,
                    height: 42,
                    borderRadius: "var(--radius-sm)",
                    background: isChecked
                      ? "var(--brand-100)"
                      : "var(--brand-50)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                  }}
                >
                  <span
                    style={{
                      fontSize: "0.65rem",
                      fontWeight: 700,
                      color: "var(--brand-600)",
                      letterSpacing: "0.02em",
                    }}
                  >
                    {TYPE_ICON[doc.mime_type] ?? "FILE"}
                  </span>
                </div>

                <div style={{ flex: 1, minWidth: 0 }}>
                  <p
                    style={{
                      fontWeight: 500,
                      fontSize: "0.88rem",
                      color: "var(--gray-800)",
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {doc.filename}
                  </p>
                  <p
                    style={{
                      fontSize: "0.75rem",
                      color: "var(--gray-400)",
                      marginTop: "0.1rem",
                    }}
                  >
                    {formatBytes(doc.size_bytes)}
                    {doc.page_count ? ` · ${doc.page_count} pages` : ""} ·{" "}
                    {new Date(doc.created_at).toLocaleDateString()}
                  </p>
                </div>

                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.6rem",
                    flexShrink: 0,
                  }}
                >
                  <span
                    className={`badge ${BADGE_CLASS[doc.status] ?? "badge-uploaded"}`}
                  >
                    {doc.status}
                  </span>
                  <svg
                    width="16"
                    height="16"
                    fill="none"
                    stroke="var(--gray-300)"
                    strokeWidth="2"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M9 5l7 7-7 7"
                    />
                  </svg>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
