"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { getAccessToken } from "@/lib/auth";
import diff_match_patch from "diff-match-patch";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface DocDetail {
  id: string;
  filename: string;
  extracted_text: string | null;
}

interface Props {
  documentIds: [string, string];
  onClose: () => void;
}

type DiffOp = [number, string];

export default function DocumentCompareModal({ documentIds, onClose }: Props) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [docA, setDocA] = useState<DocDetail | null>(null);
  const [docB, setDocB] = useState<DocDetail | null>(null);
  const [diffs, setDiffs] = useState<DiffOp[]>([]);

  const leftRef = useRef<HTMLDivElement>(null);
  const rightRef = useRef<HTMLDivElement>(null);
  const syncing = useRef(false);

  useEffect(() => {
    const controller = new AbortController();

    async function fetchAndDiff() {
      const token = getAccessToken();
      if (!token) {
        setError("Not authenticated");
        setLoading(false);
        return;
      }
      try {
        const [resA, resB] = await Promise.all(
          documentIds.map((id) =>
            fetch(`${API}/api/v1/documents/${id}`, {
              headers: { Authorization: `Bearer ${token}` },
              signal: controller.signal,
            }),
          ),
        );
        if (!resA.ok || !resB.ok) {
          setError("Failed to load one or both documents");
          setLoading(false);
          return;
        }
        const a: DocDetail = await resA.json();
        const b: DocDetail = await resB.json();
        setDocA(a);
        setDocB(b);

        const textA = a.extracted_text ?? "";
        const textB = b.extracted_text ?? "";
        if (textA || textB) {
          const dmp = new diff_match_patch();
          const d = dmp.diff_main(textA, textB);
          dmp.diff_cleanupSemantic(d);
          setDiffs(d);
        }
      } catch (err: unknown) {
        if (err instanceof Error && err.name !== "AbortError") {
          setError("Network error loading documents");
        }
      } finally {
        setLoading(false);
      }
    }

    fetchAndDiff();
    return () => controller.abort();
  }, [documentIds]);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const handleScroll = useCallback((source: "left" | "right") => {
    if (syncing.current) return;
    syncing.current = true;
    const from = source === "left" ? leftRef.current : rightRef.current;
    const to = source === "left" ? rightRef.current : leftRef.current;
    if (from && to) {
      const ratio =
        from.scrollTop / (from.scrollHeight - from.clientHeight || 1);
      to.scrollTop = ratio * (to.scrollHeight - to.clientHeight);
    }
    requestAnimationFrame(() => {
      syncing.current = false;
    });
  }, []);

  function renderDiffPanel(side: "left" | "right") {
    if (!docA || !docB) return null;

    const noTextA = !docA.extracted_text;
    const noTextB = !docB.extracted_text;

    if (noTextA && noTextB) {
      return (
        <p
          style={{
            color: "var(--gray-400)",
            padding: "2rem",
            textAlign: "center",
          }}
        >
          No extracted text available for comparison
        </p>
      );
    }

    if ((side === "left" && noTextA) || (side === "right" && noTextB)) {
      return (
        <p
          style={{
            color: "var(--gray-400)",
            padding: "2rem",
            textAlign: "center",
          }}
        >
          No extracted text available
        </p>
      );
    }

    // EQUAL = 0, DELETE = -1, INSERT = 1
    return diffs.map((diff, i) => {
      const [op, text] = diff;
      if (op === 0) {
        return <span key={i}>{text}</span>;
      }
      if (op === -1 && side === "left") {
        return (
          <span
            key={i}
            style={{
              background: "rgba(239, 68, 68, 0.15)",
              color: "var(--red-700)",
              textDecoration: "line-through",
            }}
          >
            {text}
          </span>
        );
      }
      if (op === 1 && side === "right") {
        return (
          <span
            key={i}
            style={{
              background: "rgba(34, 197, 94, 0.15)",
              color: "var(--green-700)",
            }}
          >
            {text}
          </span>
        );
      }
      return null;
    });
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
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

      {/* Header */}
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
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "1.5rem",
            flex: 1,
            minWidth: 0,
          }}
        >
          <p
            style={{
              color: "rgba(255,255,255,0.7)",
              fontSize: "0.85rem",
              fontWeight: 500,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              flex: 1,
            }}
          >
            <span
              style={{ color: "rgba(239, 68, 68, 0.8)", marginRight: "0.4rem" }}
            >
              &#9644;
            </span>
            {docA?.filename ?? "Document A"}
          </p>
          <span style={{ color: "rgba(255,255,255,0.3)", fontSize: "0.85rem" }}>
            vs
          </span>
          <p
            style={{
              color: "rgba(255,255,255,0.7)",
              fontSize: "0.85rem",
              fontWeight: 500,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              flex: 1,
            }}
          >
            <span
              style={{ color: "rgba(34, 197, 94, 0.8)", marginRight: "0.4rem" }}
            >
              &#9644;
            </span>
            {docB?.filename ?? "Document B"}
          </p>
        </div>
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
            marginLeft: "1rem",
          }}
          aria-label="Close comparison"
        >
          &#x2715;
        </button>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: "hidden", display: "flex" }}>
        {loading && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              width: "100%",
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
              <p>Loading documents...</p>
            </div>
          </div>
        )}

        {error && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              width: "100%",
              color: "#fff",
            }}
          >
            <p style={{ fontSize: "1.1rem" }}>{error}</p>
          </div>
        )}

        {!loading && !error && (
          <>
            {/* Left panel */}
            <div
              ref={leftRef}
              onScroll={() => handleScroll("left")}
              style={{
                flex: 1,
                overflowY: "auto",
                padding: "1.5rem",
                background: "#fff",
                margin: "0.75rem 0 0.75rem 0.75rem",
                borderRadius: "var(--radius-md) 0 0 var(--radius-md)",
              }}
            >
              <div
                style={{
                  fontSize: "0.88rem",
                  lineHeight: 1.8,
                  color: "var(--gray-700)",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                }}
              >
                {renderDiffPanel("left")}
              </div>
            </div>

            {/* Divider */}
            <div
              style={{
                width: 2,
                background: "rgba(255,255,255,0.15)",
                marginTop: "0.75rem",
                marginBottom: "0.75rem",
              }}
            />

            {/* Right panel */}
            <div
              ref={rightRef}
              onScroll={() => handleScroll("right")}
              style={{
                flex: 1,
                overflowY: "auto",
                padding: "1.5rem",
                background: "#fff",
                margin: "0.75rem 0.75rem 0.75rem 0",
                borderRadius: "0 var(--radius-md) var(--radius-md) 0",
              }}
            >
              <div
                style={{
                  fontSize: "0.88rem",
                  lineHeight: 1.8,
                  color: "var(--gray-700)",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                }}
              >
                {renderDiffPanel("right")}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
