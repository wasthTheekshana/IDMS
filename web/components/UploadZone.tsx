"use client";

import { useState, useRef, useCallback } from "react";
import { getAccessToken } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const ALLOWED_TYPES = [
  "application/pdf",
  "image/jpeg",
  "image/png",
  "image/tiff",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
];
const MAX_CONCURRENT = 3;

type FileStatus =
  | "pending"
  | "requesting"
  | "uploading"
  | "processing"
  | "done"
  | "error";

interface UploadItem {
  id: string;
  file: File;
  status: FileStatus;
  progress: number;
  error?: string;
  docId?: string;
}

export default function UploadZone({
  onUploadComplete,
}: {
  onUploadComplete?: () => void;
}) {
  const [items, setItems] = useState<UploadItem[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const activeRef = useRef(0);
  const queueRef = useRef<UploadItem[]>([]);

  const updateItem = useCallback((id: string, patch: Partial<UploadItem>) => {
    setItems((prev) =>
      prev.map((it) => (it.id === id ? { ...it, ...patch } : it)),
    );
  }, []);

  const processNext = useCallback(() => {
    if (activeRef.current >= MAX_CONCURRENT) return;
    const next = queueRef.current.shift();
    if (!next) return;
    activeRef.current++;
    uploadFile(next).finally(() => {
      activeRef.current--;
      processNext();
    });
  }, []);

  async function uploadFile(item: UploadItem) {
    const token = getAccessToken();
    try {
      updateItem(item.id, { status: "requesting", progress: 10 });
      const initRes = await fetch(`${API}/api/v1/documents/upload-url`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          filename: item.file.name,
          content_type: item.file.type,
          size_bytes: item.file.size,
        }),
      });
      if (!initRes.ok) {
        updateItem(item.id, { status: "error", error: await initRes.text() });
        return;
      }
      const { document_id, upload_url } = await initRes.json();
      updateItem(item.id, {
        status: "uploading",
        progress: 30,
        docId: document_id,
      });

      const uploadRes = await fetch(upload_url, {
        method: "PUT",
        headers: { "Content-Type": item.file.type },
        body: item.file,
      });
      if (!uploadRes.ok) {
        updateItem(item.id, {
          status: "error",
          error: "Upload to storage failed",
        });
        return;
      }
      updateItem(item.id, { progress: 60 });

      const confirmRes = await fetch(`${API}/api/v1/documents/confirm`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ document_id }),
      });
      if (!confirmRes.ok) {
        updateItem(item.id, {
          status: "error",
          error: await confirmRes.text(),
        });
        return;
      }

      updateItem(item.id, { status: "processing", progress: 80 });

      for (let i = 0; i < 150; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        try {
          const res = await fetch(`${API}/api/v1/documents/${document_id}`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (!res.ok) continue;
          const doc = await res.json();
          if (doc.status === "ready" || doc.status === "indexed") {
            updateItem(item.id, { status: "done", progress: 100 });
            onUploadComplete?.();
            return;
          }
          if (doc.status === "failed") {
            updateItem(item.id, {
              status: "error",
              error: doc.error_message ?? "Processing failed",
            });
            return;
          }
        } catch {
          continue;
        }
      }
    } catch (err) {
      updateItem(item.id, {
        status: "error",
        error: err instanceof Error ? err.message : "Unknown error",
      });
    }
  }

  function handleFiles(files: FileList) {
    const newItems: UploadItem[] = [];
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      if (!ALLOWED_TYPES.includes(file.type)) continue;
      if (file.size > 50 * 1024 * 1024) continue;
      newItems.push({
        id: crypto.randomUUID(),
        file,
        status: "pending",
        progress: 0,
      });
    }
    setItems((prev) => [...prev, ...newItems]);
    queueRef.current.push(...newItems);
    for (let i = 0; i < MAX_CONCURRENT; i++) processNext();
  }

  function cancelPending() {
    queueRef.current = [];
    setItems((prev) => prev.filter((it) => it.status !== "pending"));
  }

  function clearCompleted() {
    setItems((prev) =>
      prev.filter((it) => it.status !== "done" && it.status !== "error"),
    );
  }

  const doneCount = items.filter((it) => it.status === "done").length;
  const totalCount = items.length;
  const hasItems = totalCount > 0;

  const statusIcon: Record<FileStatus, { color: string; symbol: string }> = {
    pending: { color: "var(--gray-400)", symbol: "⏳" },
    requesting: { color: "var(--brand-500)", symbol: "⟳" },
    uploading: { color: "var(--brand-600)", symbol: "↑" },
    processing: { color: "var(--amber-600)", symbol: "⟳" },
    done: { color: "var(--green-600)", symbol: "✓" },
    error: { color: "var(--red-600)", symbol: "✕" },
  };

  return (
    <div>
      <div
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          if (e.dataTransfer.files.length) handleFiles(e.dataTransfer.files);
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        style={{
          border: `2px dashed ${dragOver ? "var(--brand-400)" : "var(--gray-300)"}`,
          borderRadius: "var(--radius-md)",
          padding: "2rem 1.5rem",
          textAlign: "center",
          background: dragOver ? "var(--brand-50)" : "#fff",
          transition: "all 0.15s",
          cursor: "pointer",
        }}
      >
        <svg
          width="40"
          height="40"
          fill="none"
          stroke="var(--gray-400)"
          strokeWidth="1.5"
          viewBox="0 0 24 24"
          style={{ margin: "0 auto 0.75rem" }}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
          />
        </svg>
        <p
          style={{
            fontWeight: 500,
            color: "var(--gray-700)",
            marginBottom: "0.35rem",
          }}
        >
          Drop files here, or{" "}
          <label
            style={{
              color: "var(--brand-600)",
              cursor: "pointer",
              fontWeight: 600,
            }}
          >
            browse
            <input
              type="file"
              multiple
              accept=".pdf,.jpg,.jpeg,.png,.tiff,.docx"
              onChange={(e) => {
                if (e.target.files?.length) handleFiles(e.target.files);
                e.target.value = "";
              }}
              style={{ display: "none" }}
            />
          </label>
        </p>
        <p style={{ fontSize: "0.8rem", color: "var(--gray-400)" }}>
          PDF, JPG, PNG, TIFF, or DOCX up to 50 MB each
        </p>
      </div>

      {hasItems && (
        <div style={{ marginTop: "1rem" }}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "0.5rem",
            }}
          >
            <span
              style={{
                fontSize: "0.85rem",
                color: "var(--gray-600)",
                fontWeight: 500,
              }}
            >
              {doneCount} of {totalCount} uploaded
            </span>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              {queueRef.current.length > 0 && (
                <button
                  onClick={cancelPending}
                  className="btn-ghost"
                  style={{ fontSize: "0.78rem", color: "var(--red-600)" }}
                >
                  Cancel pending
                </button>
              )}
              {(doneCount > 0 || items.some((it) => it.status === "error")) && (
                <button
                  onClick={clearCompleted}
                  className="btn-ghost"
                  style={{ fontSize: "0.78rem" }}
                >
                  Clear finished
                </button>
              )}
            </div>
          </div>

          <div
            style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}
          >
            {items.map((item) => (
              <div
                key={item.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.75rem",
                  padding: "0.5rem 0.75rem",
                  background: "var(--gray-50)",
                  borderRadius: "var(--radius-sm)",
                  border: "1px solid var(--gray-100)",
                }}
              >
                <span
                  style={{
                    color: statusIcon[item.status].color,
                    fontWeight: 700,
                    fontSize: "0.9rem",
                    width: 20,
                    textAlign: "center",
                  }}
                >
                  {statusIcon[item.status].symbol}
                </span>
                <span
                  style={{
                    flex: 1,
                    fontSize: "0.85rem",
                    color: "var(--gray-700)",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {item.file.name}
                </span>
                <div
                  style={{
                    width: 100,
                    height: 6,
                    background: "var(--gray-200)",
                    borderRadius: 3,
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      width: `${item.progress}%`,
                      height: "100%",
                      background:
                        item.status === "error"
                          ? "var(--red-500)"
                          : item.status === "done"
                            ? "var(--green-500)"
                            : "var(--brand-500)",
                      transition: "width 0.3s",
                    }}
                  />
                </div>
                {item.error && (
                  <span
                    style={{
                      fontSize: "0.75rem",
                      color: "var(--red-600)",
                      maxWidth: 150,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                    title={item.error}
                  >
                    {item.error}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
