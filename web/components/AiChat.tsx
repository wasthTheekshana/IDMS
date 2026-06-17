"use client";

import { useState } from "react";
import { getAccessToken } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface AiSource {
  page: number;
  excerpt: string;
  document_id?: string;
  filename?: string;
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: AiSource[];
}

export default function AiChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const question = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setLoading(true);

    const token = getAccessToken();
    const resp = await fetch(`${API}/api/v1/ai/chat`, {
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
        { role: "assistant", content: `Error: ${resp.status}` },
      ]);
      return;
    }

    const data = await resp.json();
    setMessages((prev) => [
      ...prev,
      {
        role: "assistant",
        content: data.answer,
        sources: data.sources,
      },
    ]);
  }

  return (
    <div style={{ marginTop: "2rem" }}>
      <div
        style={{
          border: "1px solid #e0e0e0",
          borderRadius: 8,
          maxHeight: 400,
          overflowY: "auto",
          padding: "1rem",
          marginBottom: "0.75rem",
          background: "#fafafa",
        }}
      >
        {messages.length === 0 && (
          <p style={{ color: "#999" }}>Ask a question about your documents…</p>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            style={{
              marginBottom: "1rem",
              textAlign: msg.role === "user" ? "right" : "left",
            }}
          >
            <div
              style={{
                display: "inline-block",
                padding: "0.5rem 1rem",
                borderRadius: 8,
                background: msg.role === "user" ? "#0070f3" : "#fff",
                color: msg.role === "user" ? "#fff" : "#333",
                border: msg.role === "assistant" ? "1px solid #ddd" : "none",
                maxWidth: "80%",
                textAlign: "left",
              }}
            >
              <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{msg.content}</p>
              {msg.sources && msg.sources.length > 0 && (
                <div
                  style={{
                    marginTop: "0.5rem",
                    fontSize: "0.8rem",
                    color: "#888",
                  }}
                >
                  Sources:{" "}
                  {msg.sources.map((s, j) => (
                    <span key={j}>
                      {s.filename ?? "doc"} p.{s.page}
                      {j < msg.sources!.length - 1 ? ", " : ""}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <p style={{ color: "#999", fontStyle: "italic" }}>Thinking…</p>
        )}
      </div>
      <form onSubmit={handleSubmit} style={{ display: "flex", gap: "0.5rem" }}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about your documents…"
          style={{ flex: 1, padding: "0.5rem", fontSize: "1rem" }}
          disabled={loading}
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          style={{ padding: "0.5rem 1.5rem" }}
        >
          Send
        </button>
      </form>
    </div>
  );
}
