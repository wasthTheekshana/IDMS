"use client";

import { useEffect, useState } from "react";
import { getAccessToken } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Props {
  documentId: string;
  filename: string;
  mimeType: string;
  extractedText?: string | null;
  onClose: () => void;
}

const DOCX_TYPE =
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

export default function DocumentPreviewModal({
  documentId,
  filename,
  mimeType,
  extractedText,
  onClose,
}: Props) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [contentType, setContentType] = useState<string>(mimeType);

  useEffect(() => {
    const controller = new AbortController();
    let blobUrl: string | null = null;

    async function fetchPreviewUrl() {
      const token = getAccessToken();
      if (!token) {
        setError("Not authenticated");
        setLoading(false);
        return;
      }
      try {
        const res = await fetch(
          `${API}/api/v1/documents/${documentId}/preview-url`,
          {
            headers: { Authorization: `Bearer ${token}` },
            signal: controller.signal,
          },
        );
        if (!res.ok) {
          setError(
            res.status === 404
              ? "Document not found"
              : "Failed to load preview",
          );
          setLoading(false);
          return;
        }
        const data = await res.json();
        setContentType(data.content_type);
        if (data.preview_url) {
          if (data.preview_url.startsWith("/")) {
            const blobRes = await fetch(`${API}${data.preview_url}`, {
              headers: { Authorization: `Bearer ${token}` },
              signal: controller.signal,
            });
            if (!blobRes.ok) throw new Error("Failed to load preview image");
            const blob = await blobRes.blob();
            blobUrl = URL.createObjectURL(blob);
            setPreviewUrl(blobUrl);
          } else {
            setPreviewUrl(data.preview_url);
          }
        }
      } catch (err: unknown) {
        if (err instanceof Error && err.name !== "AbortError") {
          setError("Network error loading preview");
        }
      } finally {
        setLoading(false);
      }
    }

    fetchPreviewUrl();
    return () => {
      controller.abort();
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
  }, [documentId]);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  function renderContent() {
    if (loading) {
      return (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            height: "100%",
            color: "#fff",
          }}
        >
          <div style={{ textAlign: "center" }}>
            <div
              style={{
                width: 40,
                height: 40,
                border: "3px solid rgba(255,255,255,0.2)",
                borderTopColor: "#fff",
                borderRadius: "50%",
                animation: "spin 0.8s linear infinite",
                margin: "0 auto 1rem",
              }}
            />
            <p>Loading preview...</p>
          </div>
        </div>
      );
    }

    if (error) {
      return (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            height: "100%",
            color: "#fff",
          }}
        >
          <div style={{ textAlign: "center" }}>
            <p style={{ fontSize: "1.1rem", marginBottom: "0.5rem" }}>
              {error}
            </p>
            {extractedText && (
              <p
                style={{ fontSize: "0.85rem", color: "rgba(255,255,255,0.6)" }}
              >
                Showing extracted text as fallback
              </p>
            )}
          </div>
        </div>
      );
    }

    if (contentType === "application/pdf" && previewUrl) {
      return (
        <iframe
          src={previewUrl}
          style={{
            width: "100%",
            height: "100%",
            border: "none",
            borderRadius: "var(--radius-sm)",
          }}
          title={`Preview: ${filename}`}
        />
      );
    }

    if (
      (contentType === "image/jpeg" ||
        contentType === "image/png" ||
        contentType === "image/tiff" ||
        contentType === "image/x-tiff") &&
      previewUrl
    ) {
      return (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            height: "100%",
            padding: "1rem",
          }}
        >
          <img
            src={previewUrl}
            alt={filename}
            style={{
              maxWidth: "100%",
              maxHeight: "100%",
              objectFit: "contain",
              borderRadius: "var(--radius-sm)",
            }}
          />
        </div>
      );
    }

    // DOCX or unsupported — show extracted text
    if (extractedText) {
      return (
        <div
          style={{
            maxWidth: 720,
            margin: "0 auto",
            padding: "2rem",
            height: "100%",
            overflowY: "auto",
          }}
        >
          <div
            style={{
              background: "#fff",
              borderRadius: "var(--radius-md)",
              padding: "2rem",
              fontSize: "0.92rem",
              lineHeight: 1.8,
              color: "var(--gray-700)",
              whiteSpace: "pre-wrap",
              boxShadow: "0 4px 24px rgba(0,0,0,0.3)",
            }}
          >
            {extractedText}
          </div>
        </div>
      );
    }

    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: "100%",
          color: "#fff",
        }}
      >
        <p>No preview available for this document.</p>
      </div>
    );
  }

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9999,
        background: "rgba(0,0,0,0.85)",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Spinner keyframes */}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

      {/* Header bar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0.75rem 1.25rem",
          borderBottom: "1px solid rgba(255,255,255,0.1)",
          flexShrink: 0,
        }}
      >
        <p
          style={{
            color: "#fff",
            fontWeight: 600,
            fontSize: "0.95rem",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            marginRight: "1rem",
          }}
        >
          {filename}
        </p>
        <button
          onClick={onClose}
          style={{
            background: "none",
            border: "none",
            color: "#fff",
            fontSize: "1.5rem",
            cursor: "pointer",
            padding: "0.25rem 0.5rem",
            lineHeight: 1,
            borderRadius: "var(--radius-sm)",
            flexShrink: 0,
          }}
          aria-label="Close preview"
        >
          &#x2715;
        </button>
      </div>

      {/* Content area */}
      <div style={{ flex: 1, overflow: "hidden" }}>{renderContent()}</div>
    </div>
  );
}
