"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { getAccessToken } from "@/lib/auth";
import ConfirmDeleteModal from "./ConfirmDeleteModal";
import DocumentCompareModal from "./DocumentCompareModal";
import DocumentPreviewModal from "./DocumentPreviewModal";

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

interface Props {
  onSelectDocument?: (doc: Document | null) => void;
  selectedId?: string | null;
  refreshKey?: number;
}

export default function DocumentList({
  onSelectDocument,
  selectedId,
  refreshKey,
}: Props) {
  const [docs, setDocs] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [detail, setDetail] = useState<Document | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Selection state
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const lastClickedRef = useRef<string | null>(null);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [previewDoc, setPreviewDoc] = useState<Document | null>(null);
  const [showCompare, setShowCompare] = useState(false);

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

  function handleCheckbox(docId: string, e: React.MouseEvent) {
    e.stopPropagation();
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (e.shiftKey && lastClickedRef.current) {
        const ids = docs.map((d) => d.id);
        const start = ids.indexOf(lastClickedRef.current);
        const end = ids.indexOf(docId);
        const [lo, hi] = start < end ? [start, end] : [end, start];
        for (let i = lo; i <= hi; i++) next.add(ids[i]);
      } else if (next.has(docId)) {
        next.delete(docId);
      } else {
        next.add(docId);
      }
      return next;
    });
    lastClickedRef.current = docId;
  }

  function handleSelectAll() {
    if (selectedIds.size === docs.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(docs.map((d) => d.id)));
    }
  }

  async function handleSelect(doc: Document) {
    if (detail?.id === doc.id) {
      setDetail(null);
      onSelectDocument?.(null);
      return;
    }
    setDetailLoading(true);
    const token = getAccessToken();
    try {
      const res = await fetch(`${API}/api/v1/documents/${doc.id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const full = await res.json();
        setDetail(full);
        onSelectDocument?.(full);
      }
    } catch {
      /* ignore */
    } finally {
      setDetailLoading(false);
    }
  }

  async function handleBulkDelete() {
    const token = getAccessToken();
    const ids = Array.from(selectedIds);
    try {
      const res = await fetch(`${API}/api/v1/documents/bulk/delete`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ document_ids: ids }),
      });
      if (res.ok) {
        setSelectedIds(new Set());
        setShowDeleteModal(false);
        setDetail(null);
        await fetchDocs();
      }
    } catch {
      /* ignore */
    }
  }

  async function handleBulkDownload() {
    const token = getAccessToken();
    const ids = Array.from(selectedIds);
    setActionLoading("download");
    try {
      const res = await fetch(`${API}/api/v1/documents/bulk/download`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ document_ids: ids }),
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
            ?.replace(/"/g, "") || "documents.zip";
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch {
      /* ignore */
    } finally {
      setActionLoading(null);
    }
  }

  async function handleBulkExport() {
    const token = getAccessToken();
    const ids = Array.from(selectedIds);
    setActionLoading("export");
    try {
      const res = await fetch(`${API}/api/v1/documents/bulk/export`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ document_ids: ids }),
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
            ?.replace(/"/g, "") || "documents.xlsx";
        a.click();
        URL.revokeObjectURL(url);
      }
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
          padding: "2rem",
          textAlign: "center",
          color: "var(--gray-400)",
        }}
      >
        Loading documents...
      </div>
    );

  if (docs.length === 0) {
    return (
      <div style={{ padding: "2.5rem", textAlign: "center" }}>
        <svg
          width="48"
          height="48"
          fill="none"
          stroke="var(--gray-300)"
          strokeWidth="1.5"
          viewBox="0 0 24 24"
          style={{ margin: "0 auto 0.75rem" }}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
          />
        </svg>
        <p style={{ color: "var(--gray-500)", fontWeight: 500 }}>
          No documents yet
        </p>
        <p style={{ color: "var(--gray-400)", fontSize: "0.85rem" }}>
          Upload your first document to get started
        </p>
      </div>
    );
  }

  const selectAllState =
    selectedIds.size === 0
      ? "none"
      : selectedIds.size === docs.length
        ? "all"
        : "some";

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "0.75rem",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <input
            type="checkbox"
            checked={selectAllState === "all"}
            ref={(el) => {
              if (el) el.indeterminate = selectAllState === "some";
            }}
            onChange={handleSelectAll}
            style={{
              width: 16,
              height: 16,
              cursor: "pointer",
              accentColor: "var(--brand-500)",
            }}
          />
          <span style={{ color: "var(--gray-500)", fontSize: "0.85rem" }}>
            {selectedIds.size > 0
              ? `${selectedIds.size} selected`
              : `${docs.length} document${docs.length !== 1 ? "s" : ""}`}
          </span>
        </div>
        <button
          onClick={fetchDocs}
          className="btn-ghost"
          style={{ fontSize: "0.8rem" }}
        >
          Refresh
        </button>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        {docs.map((doc) => {
          const isExpanded = detail?.id === doc.id || selectedId === doc.id;
          const isChecked = selectedIds.has(doc.id);
          return (
            <div key={doc.id}>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "0.75rem 1rem",
                  background: isChecked
                    ? "var(--brand-50)"
                    : isExpanded
                      ? "var(--brand-50)"
                      : "var(--gray-50)",
                  borderRadius: "var(--radius-md)",
                  border: isChecked
                    ? "1.5px solid var(--brand-300)"
                    : isExpanded
                      ? "1.5px solid var(--brand-300)"
                      : "1px solid var(--gray-100)",
                  cursor: "pointer",
                  transition: "all 0.15s",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.75rem",
                    flex: 1,
                    minWidth: 0,
                  }}
                >
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onClick={(e) => handleCheckbox(doc.id, e)}
                    onChange={() => {}}
                    style={{
                      width: 16,
                      height: 16,
                      cursor: "pointer",
                      accentColor: "var(--brand-500)",
                      flexShrink: 0,
                    }}
                  />
                  <div
                    onClick={() => handleSelect(doc)}
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
                        width: 36,
                        height: 36,
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
                      <svg
                        width="18"
                        height="18"
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
                    </div>
                    <div style={{ minWidth: 0 }}>
                      <p
                        style={{
                          fontWeight: 500,
                          fontSize: "0.9rem",
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
                          fontSize: "0.78rem",
                          color: "var(--gray-400)",
                        }}
                      >
                        {formatBytes(doc.size_bytes)}
                        {doc.page_count
                          ? ` · ${doc.page_count} pages`
                          : ""} ·{" "}
                        {new Date(doc.created_at).toLocaleDateString()}
                      </p>
                    </div>
                  </div>
                </div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.5rem",
                  }}
                  onClick={() => handleSelect(doc)}
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
                    stroke="var(--gray-400)"
                    strokeWidth="2"
                    viewBox="0 0 24 24"
                    style={{
                      transform: isExpanded ? "rotate(180deg)" : "rotate(0)",
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

              {isExpanded && detail && detail.id === doc.id && (
                <div
                  style={{
                    margin: "0.25rem 0 0.5rem",
                    padding: "1rem 1.25rem",
                    background: "#fff",
                    border: "1px solid var(--gray-200)",
                    borderRadius: "var(--radius-md)",
                    fontSize: "0.88rem",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      gap: "2rem",
                      marginBottom: "1rem",
                      flexWrap: "wrap",
                    }}
                  >
                    <div>
                      <span
                        style={{
                          color: "var(--gray-400)",
                          fontSize: "0.78rem",
                        }}
                      >
                        Type
                      </span>
                      <p style={{ fontWeight: 500, color: "var(--gray-700)" }}>
                        {detail.mime_type}
                      </p>
                    </div>
                    <div>
                      <span
                        style={{
                          color: "var(--gray-400)",
                          fontSize: "0.78rem",
                        }}
                      >
                        Pages
                      </span>
                      <p style={{ fontWeight: 500, color: "var(--gray-700)" }}>
                        {detail.page_count ?? "—"}
                      </p>
                    </div>
                    <div>
                      <span
                        style={{
                          color: "var(--gray-400)",
                          fontSize: "0.78rem",
                        }}
                      >
                        Status
                      </span>
                      <p style={{ fontWeight: 500, color: "var(--gray-700)" }}>
                        {detail.status}
                      </p>
                    </div>
                  </div>
                  {(detail.status === "ready" ||
                    detail.status === "indexed") && (
                    <div style={{ marginBottom: "1rem" }}>
                      <button
                        onClick={() => setPreviewDoc(detail)}
                        className="btn-primary"
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "0.4rem",
                          padding: "0.45rem 1rem",
                          fontSize: "0.82rem",
                        }}
                      >
                        <svg
                          width="16"
                          height="16"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                          />
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
                          />
                        </svg>
                        Preview
                      </button>
                    </div>
                  )}
                  {detail.extracted_text ? (
                    <div>
                      <p
                        style={{
                          fontWeight: 600,
                          color: "var(--gray-700)",
                          marginBottom: "0.5rem",
                          fontSize: "0.85rem",
                        }}
                      >
                        Extracted Content
                      </p>
                      <div
                        style={{
                          maxHeight: 300,
                          overflowY: "auto",
                          padding: "0.75rem",
                          background: "var(--gray-50)",
                          borderRadius: "var(--radius-sm)",
                          border: "1px solid var(--gray-100)",
                          whiteSpace: "pre-wrap",
                          fontSize: "0.82rem",
                          lineHeight: 1.7,
                          color: "var(--gray-600)",
                        }}
                      >
                        {detail.extracted_text}
                      </div>
                    </div>
                  ) : (
                    <p
                      style={{ color: "var(--gray-400)", fontSize: "0.85rem" }}
                    >
                      {detail.status === "processing"
                        ? "Document is still being processed..."
                        : "No extracted text available."}
                    </p>
                  )}
                </div>
              )}

              {isExpanded && detailLoading && (
                <div
                  style={{
                    padding: "1rem",
                    textAlign: "center",
                    color: "var(--gray-400)",
                    fontSize: "0.85rem",
                  }}
                >
                  Loading details...
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Bulk Action Toolbar */}
      {selectedIds.size > 0 && (
        <div
          style={{
            position: "sticky",
            bottom: 0,
            marginTop: "1rem",
            padding: "0.75rem 1rem",
            background: "#fff",
            borderRadius: "var(--radius-lg)",
            border: "1px solid var(--gray-200)",
            boxShadow: "0 -4px 20px rgba(0,0,0,0.08)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <span
            style={{
              fontSize: "0.85rem",
              fontWeight: 600,
              color: "var(--gray-700)",
            }}
          >
            {selectedIds.size} selected
          </span>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button
              onClick={() => setShowDeleteModal(true)}
              style={{
                padding: "0.45rem 1rem",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--red-200)",
                background: "var(--red-50)",
                color: "var(--red-700)",
                fontWeight: 500,
                fontSize: "0.82rem",
                cursor: "pointer",
              }}
            >
              Delete
            </button>
            {selectedIds.size === 2 && (
              <button
                onClick={() => setShowCompare(true)}
                className="btn-secondary"
                style={{
                  padding: "0.45rem 1rem",
                  fontSize: "0.82rem",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "0.35rem",
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
                    d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
                  />
                </svg>
                Compare
              </button>
            )}
            <button
              onClick={handleBulkDownload}
              disabled={actionLoading === "download"}
              className="btn-secondary"
              style={{ padding: "0.45rem 1rem", fontSize: "0.82rem" }}
            >
              {actionLoading === "download" ? "Zipping..." : "Download ZIP"}
            </button>
            <button
              onClick={handleBulkExport}
              disabled={actionLoading === "export"}
              className="btn-primary"
              style={{ padding: "0.45rem 1rem", fontSize: "0.82rem" }}
            >
              {actionLoading === "export" ? "Exporting..." : "Export Excel"}
            </button>
          </div>
        </div>
      )}

      {showDeleteModal && (
        <ConfirmDeleteModal
          documentNames={docs
            .filter((d) => selectedIds.has(d.id))
            .map((d) => d.filename)}
          onConfirm={handleBulkDelete}
          onCancel={() => setShowDeleteModal(false)}
        />
      )}

      {previewDoc && (
        <DocumentPreviewModal
          documentId={previewDoc.id}
          filename={previewDoc.filename}
          mimeType={previewDoc.mime_type}
          extractedText={previewDoc.extracted_text}
          onClose={() => setPreviewDoc(null)}
        />
      )}

      {showCompare && selectedIds.size === 2 && (
        <DocumentCompareModal
          documentIds={Array.from(selectedIds) as [string, string]}
          onClose={() => setShowCompare(false)}
        />
      )}
    </div>
  );
}
