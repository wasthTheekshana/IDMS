"use client";

import { useState } from "react";

interface Props {
  documentNames: string[];
  onConfirm: () => Promise<void>;
  onCancel: () => void;
}

export default function ConfirmDeleteModal({
  documentNames,
  onConfirm,
  onCancel,
}: Props) {
  const [loading, setLoading] = useState(false);

  async function handleConfirm() {
    setLoading(true);
    try {
      await onConfirm();
    } finally {
      setLoading(false);
    }
  }

  const displayNames = documentNames.slice(0, 10);
  const remaining = documentNames.length - displayNames.length;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 100,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(0,0,0,0.4)",
        backdropFilter: "blur(2px)",
      }}
      onClick={onCancel}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#fff",
          borderRadius: "var(--radius-lg)",
          padding: "1.5rem",
          width: "100%",
          maxWidth: 440,
          boxShadow: "0 20px 60px rgba(0,0,0,0.15)",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.75rem",
            marginBottom: "1rem",
          }}
        >
          <div
            style={{
              width: 40,
              height: 40,
              borderRadius: "50%",
              background: "var(--red-50)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <svg
              width="20"
              height="20"
              fill="none"
              stroke="var(--red-600)"
              strokeWidth="2"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
              />
            </svg>
          </div>
          <div>
            <h3
              style={{
                fontWeight: 600,
                color: "var(--gray-900)",
                fontSize: "1.05rem",
              }}
            >
              Delete {documentNames.length} document
              {documentNames.length !== 1 ? "s" : ""}?
            </h3>
            <p style={{ fontSize: "0.85rem", color: "var(--gray-500)" }}>
              This action cannot be undone.
            </p>
          </div>
        </div>

        <div
          style={{
            maxHeight: 200,
            overflowY: "auto",
            marginBottom: "1.25rem",
            padding: "0.75rem",
            background: "var(--gray-50)",
            borderRadius: "var(--radius-sm)",
            border: "1px solid var(--gray-100)",
          }}
        >
          {displayNames.map((name, i) => (
            <div
              key={i}
              style={{
                fontSize: "0.85rem",
                color: "var(--gray-700)",
                padding: "0.25rem 0",
                borderBottom:
                  i < displayNames.length - 1
                    ? "1px solid var(--gray-100)"
                    : "none",
              }}
            >
              {name}
            </div>
          ))}
          {remaining > 0 && (
            <div
              style={{
                fontSize: "0.82rem",
                color: "var(--gray-400)",
                padding: "0.35rem 0",
                fontStyle: "italic",
              }}
            >
              +{remaining} more
            </div>
          )}
        </div>

        <div
          style={{
            display: "flex",
            gap: "0.75rem",
            justifyContent: "flex-end",
          }}
        >
          <button
            onClick={onCancel}
            disabled={loading}
            className="btn-secondary"
            style={{ padding: "0.5rem 1.25rem" }}
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={loading}
            style={{
              padding: "0.5rem 1.25rem",
              borderRadius: "var(--radius-md)",
              border: "none",
              background: "var(--red-600)",
              color: "#fff",
              fontWeight: 600,
              cursor: loading ? "not-allowed" : "pointer",
              opacity: loading ? 0.6 : 1,
            }}
          >
            {loading ? "Deleting..." : "Delete permanently"}
          </button>
        </div>
      </div>
    </div>
  );
}
