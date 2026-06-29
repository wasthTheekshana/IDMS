"use client";

import { useState, useRef, useEffect } from "react";
import { getAccessToken } from "@/lib/auth";
import DocumentSelector from "@/components/DocumentSelector";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface AiSource {
  page: number;
  excerpt: string;
  document_id?: string;
  filename?: string;
}

interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
  sources?: AiSource[];
}

export default function AiChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [docFilter, setDocFilter] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const question = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setLoading(true);

    try {
      const token = getAccessToken();
      let url: string;
      if (docFilter) {
        url = `${API}/api/v1/ai/documents/${docFilter}/ask`;
      } else {
        url = `${API}/api/v1/ai/chat`;
      }
      const resp = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ question }),
      });
      setLoading(false);
      if (!resp.ok) {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: `Sorry, something went wrong (${resp.status}).`,
          },
        ]);
        return;
      }
      const data = await resp.json();
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.answer, sources: data.sources },
      ]);
    } catch {
      setLoading(false);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Failed to connect to the AI service." },
      ]);
    }
  }

  async function handleSummarize() {
    if (!docFilter || loading) return;
    setLoading(true);
    setMessages((prev) => [
      ...prev,
      { role: "system", content: "Generating summary..." },
    ]);

    try {
      const token = getAccessToken();
      const resp = await fetch(
        `${API}/api/v1/ai/documents/${docFilter}/summarize`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        },
      );
      setLoading(false);
      if (!resp.ok) {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: `Summary failed (${resp.status}).` },
        ]);
        return;
      }
      const data = await resp.json();
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.summary },
      ]);
    } catch {
      setLoading(false);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Failed to generate summary." },
      ]);
    }
  }

  return (
    <div>
      <DocumentSelector
        value={docFilter}
        onChange={(id) => {
          setDocFilter(id);
          setMessages([]);
        }}
      />

      {docFilter && (
        <div style={{ marginBottom: "0.75rem" }}>
          <button
            onClick={handleSummarize}
            disabled={loading}
            className="btn-secondary"
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.4rem",
              fontSize: "0.85rem",
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
                d="M4 6h16M4 12h16M4 18h7"
              />
            </svg>
            Summarize document
          </button>
        </div>
      )}

      {/* Chat area */}
      <div
        style={{
          borderRadius: "var(--radius-md)",
          border: "1px solid var(--gray-200)",
          background: "var(--gray-50)",
          minHeight: 280,
          maxHeight: 420,
          overflowY: "auto",
          padding: "1rem",
          marginBottom: "0.75rem",
        }}
      >
        {messages.length === 0 && (
          <div style={{ padding: "2.5rem 1rem", textAlign: "center" }}>
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
                d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"
              />
            </svg>
            <p style={{ color: "var(--gray-500)", fontWeight: 500 }}>
              {docFilter
                ? "Ask a question about this document"
                : "Ask anything about your documents"}
            </p>
            <p
              style={{
                color: "var(--gray-400)",
                fontSize: "0.85rem",
                marginTop: "0.25rem",
              }}
            >
              {docFilter
                ? "Select 'All documents' to search across everything"
                : "Or select a specific document to focus your questions"}
            </p>
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            style={{
              display: "flex",
              justifyContent: msg.role === "user" ? "flex-end" : "flex-start",
              marginBottom: "0.75rem",
            }}
          >
            {msg.role !== "user" && (
              <div
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: "50%",
                  background:
                    msg.role === "system"
                      ? "var(--gray-100)"
                      : "var(--brand-100)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  marginRight: "0.5rem",
                  flexShrink: 0,
                  marginTop: "0.15rem",
                }}
              >
                <svg
                  width="14"
                  height="14"
                  fill="none"
                  stroke={
                    msg.role === "system"
                      ? "var(--gray-500)"
                      : "var(--brand-600)"
                  }
                  strokeWidth="2"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M13 10V3L4 14h7v7l9-11h-7z"
                  />
                </svg>
              </div>
            )}
            <div
              style={{
                maxWidth: "80%",
                padding: "0.6rem 0.9rem",
                borderRadius:
                  msg.role === "user"
                    ? "var(--radius-md) var(--radius-md) 4px var(--radius-md)"
                    : "var(--radius-md) var(--radius-md) var(--radius-md) 4px",
                background:
                  msg.role === "user"
                    ? "var(--brand-500)"
                    : msg.role === "system"
                      ? "var(--gray-100)"
                      : "#fff",
                color: msg.role === "user" ? "#fff" : "var(--gray-700)",
                border:
                  msg.role === "assistant"
                    ? "1px solid var(--gray-200)"
                    : "none",
                fontSize: "0.9rem",
                lineHeight: 1.6,
                boxShadow: "var(--shadow-sm)",
                fontStyle: msg.role === "system" ? "italic" : "normal",
              }}
            >
              <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{msg.content}</p>
              {msg.sources && msg.sources.length > 0 && (
                <div
                  style={{
                    marginTop: "0.5rem",
                    paddingTop: "0.4rem",
                    borderTop: "1px solid var(--gray-100)",
                    fontSize: "0.78rem",
                    color: "var(--gray-400)",
                  }}
                >
                  Sources:{" "}
                  {msg.sources.map((s, j) => (
                    <span
                      key={j}
                      style={{
                        background: "var(--gray-50)",
                        padding: "0.1rem 0.35rem",
                        borderRadius: "4px",
                        marginRight: "0.3rem",
                      }}
                    >
                      {s.filename ?? "doc"} p.{s.page}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              color: "var(--gray-400)",
              fontSize: "0.85rem",
            }}
          >
            <div
              style={{
                width: 28,
                height: 28,
                borderRadius: "50%",
                background: "var(--brand-100)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
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
            </div>
            <span style={{ animation: "pulse 1.5s infinite" }}>
              Thinking...
            </span>
            <style>{`@keyframes pulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 1; } }`}</style>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} style={{ display: "flex", gap: "0.5rem" }}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={
            docFilter
              ? "Ask about this document..."
              : "Ask about all your documents..."
          }
          disabled={loading}
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="btn-primary"
          style={{ whiteSpace: "nowrap" }}
        >
          <svg
            width="16"
            height="16"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            viewBox="0 0 24 24"
            style={{
              display: "inline",
              verticalAlign: "middle",
              marginRight: "0.3rem",
            }}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
            />
          </svg>
          Send
        </button>
      </form>
    </div>
  );
}
