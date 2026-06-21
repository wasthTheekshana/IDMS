"use client";

import { useEffect, useState } from "react";
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  authApi,
} from "@/lib/auth";
import UploadZone from "@/components/UploadZone";
import SearchBox from "@/components/SearchBox";
import AiChat from "@/components/AiChat";
import DocumentList from "@/components/DocumentList";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface UserProfile {
  id: string;
  org_id: string;
  email: string;
  role: string;
  is_active: boolean;
}

function DocumentsTab() {
  const [refreshKey, setRefreshKey] = useState(0);
  return (
    <div>
      <div
        className="card"
        style={{ padding: "1.5rem", marginBottom: "1.5rem" }}
      >
        <h2
          style={{
            fontSize: "1.1rem",
            fontWeight: 600,
            color: "var(--gray-900)",
            marginBottom: "1rem",
          }}
        >
          Upload Documents
        </h2>
        <UploadZone onUploadComplete={() => setRefreshKey((k) => k + 1)} />
      </div>
      <div className="card" style={{ padding: "1.5rem" }}>
        <h2
          style={{
            fontSize: "1.1rem",
            fontWeight: 600,
            color: "var(--gray-900)",
            marginBottom: "1rem",
          }}
        >
          Your Documents
        </h2>
        <DocumentList refreshKey={refreshKey} />
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [activeTab, setActiveTab] = useState<"documents" | "search" | "ai">(
    "documents",
  );

  useEffect(() => {
    const token = getAccessToken();
    if (!token) {
      window.location.href = "/login";
      return;
    }
    fetch(`${API}/api/v1/users/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => {
        if (!r.ok) throw new Error("Unauthorized");
        return r.json() as Promise<UserProfile>;
      })
      .then(setUser)
      .catch(() => {
        window.location.href = "/login";
      });
  }, []);

  async function handleLogout() {
    const refresh = getRefreshToken();
    if (refresh) {
      try {
        await authApi.logout(refresh);
      } catch {
        /* continue */
      }
    }
    clearTokens();
    window.location.href = "/login";
  }

  if (!user)
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <div style={{ textAlign: "center" }}>
          <div
            style={{
              width: 36,
              height: 36,
              border: "3px solid var(--brand-200)",
              borderTopColor: "var(--brand-500)",
              borderRadius: "50%",
              animation: "spin 0.7s linear infinite",
              margin: "0 auto 1rem",
            }}
          />
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
          <p style={{ color: "var(--gray-500)" }}>Loading...</p>
        </div>
      </div>
    );

  const tabs = [
    {
      key: "documents" as const,
      label: "Documents",
      icon: "M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z",
    },
    {
      key: "search" as const,
      label: "Search",
      icon: "M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z",
    },
    {
      key: "ai" as const,
      label: "AI Assistant",
      icon: "M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z",
    },
  ];

  return (
    <div style={{ minHeight: "100vh", background: "var(--gray-50)" }}>
      {/* Top Nav */}
      <header
        style={{
          background: "#fff",
          borderBottom: "1px solid var(--gray-200)",
          padding: "0 1.5rem",
          position: "sticky",
          top: 0,
          zIndex: 10,
        }}
      >
        <div
          style={{
            maxWidth: 1100,
            margin: "0 auto",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            height: 56,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
            <div
              style={{
                width: 32,
                height: 32,
                background: "var(--brand-500)",
                borderRadius: "var(--radius-sm)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <span
                style={{ color: "#fff", fontWeight: 700, fontSize: "0.95rem" }}
              >
                D
              </span>
            </div>
            <span
              style={{
                fontWeight: 700,
                fontSize: "1.1rem",
                color: "var(--gray-900)",
              }}
            >
              IDMS
            </span>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
            <div style={{ textAlign: "right" }}>
              <span
                style={{
                  fontSize: "0.85rem",
                  fontWeight: 500,
                  color: "var(--gray-800)",
                }}
              >
                {user.email}
              </span>
              <span
                style={{
                  display: "block",
                  fontSize: "0.75rem",
                  color: "var(--gray-400)",
                }}
              >
                {user.role}
              </span>
            </div>
            <button
              onClick={handleLogout}
              className="btn-secondary"
              style={{ padding: "0.4rem 0.9rem", fontSize: "0.8rem" }}
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      {/* Content */}
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "1.5rem" }}>
        {/* Tab Bar */}
        <div
          style={{
            display: "flex",
            gap: "0.25rem",
            marginBottom: "1.5rem",
            background: "#fff",
            borderRadius: "var(--radius-lg)",
            padding: "0.3rem",
            border: "1px solid var(--gray-200)",
          }}
        >
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              style={{
                flex: 1,
                padding: "0.55rem 1rem",
                borderRadius: "var(--radius-md)",
                border: "none",
                background:
                  activeTab === tab.key ? "var(--brand-500)" : "transparent",
                color: activeTab === tab.key ? "#fff" : "var(--gray-500)",
                fontWeight: 500,
                fontSize: "0.875rem",
                cursor: "pointer",
                transition: "all 0.15s",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "0.4rem",
              }}
            >
              <svg
                width="16"
                height="16"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                viewBox="0 0 24 24"
              >
                <path d={tab.icon} />
              </svg>
              {tab.label}
            </button>
          ))}
        </div>

        {/* Documents Tab */}
        {activeTab === "documents" && <DocumentsTab />}

        {/* Search Tab */}
        {activeTab === "search" && (
          <div className="card" style={{ padding: "1.5rem" }}>
            <h2
              style={{
                fontSize: "1.1rem",
                fontWeight: 600,
                color: "var(--gray-900)",
                marginBottom: "0.25rem",
              }}
            >
              Search Documents
            </h2>
            <p
              style={{
                color: "var(--gray-500)",
                fontSize: "0.85rem",
                marginBottom: "1rem",
              }}
            >
              Search across all your uploaded documents using keywords
            </p>
            <SearchBox />
          </div>
        )}

        {/* AI Tab */}
        {activeTab === "ai" && (
          <div className="card" style={{ padding: "1.5rem" }}>
            <h2
              style={{
                fontSize: "1.1rem",
                fontWeight: 600,
                color: "var(--gray-900)",
                marginBottom: "0.25rem",
              }}
            >
              AI Assistant
            </h2>
            <p
              style={{
                color: "var(--gray-500)",
                fontSize: "0.85rem",
                marginBottom: "1rem",
              }}
            >
              Ask questions about your documents and get AI-powered answers
            </p>
            <AiChat />
          </div>
        )}
      </div>
    </div>
  );
}
