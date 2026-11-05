"use client";

import { useEffect, useState, useCallback } from "react";
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  authApi,
} from "@/lib/auth";
import UploadZone from "@/components/UploadZone";
import SearchBox from "@/components/SearchBox";
import AiChat from "@/components/AiChat";
import UsageIndicator from "@/components/UsageIndicator";
import DocumentList, { type Document } from "@/components/DocumentList";
import DocumentViewer from "@/components/DocumentViewer";
import ExtractionsPanel from "@/components/ExtractionsPanel";
import DocumentCompare from "@/components/DocumentCompare";
import TeamPanel from "@/components/TeamPanel";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface UserProfile {
  id: string;
  org_id: string;
  email: string;
  role: string;
  is_active: boolean;
}

type View =
  | "documents"
  | "search"
  | "ai"
  | "upload"
  | "extract"
  | "compare"
  | "team";

const NAV_ITEMS: { key: View; label: string; icon: string }[] = [
  {
    key: "documents",
    label: "Documents",
    icon: "M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z",
  },
  {
    key: "upload",
    label: "Upload",
    icon: "M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12",
  },
  {
    key: "extract",
    label: "Extractions",
    icon: "M3 10h18M3 14h18m-9-4v8m-7 0h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z",
  },
  {
    key: "compare",
    label: "Compare",
    icon: "M9 5l7 7-7 7M15 5l-7 7 7 7",
  },
  {
    key: "search",
    label: "Search",
    icon: "M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z",
  },
  {
    key: "ai",
    label: "AI Assistant",
    icon: "M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z",
  },
  {
    key: "team",
    label: "Team",
    icon: "M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z",
  },
];

const SEARCH_ICON = NAV_ITEMS.find((n) => n.key === "search")!.icon;

export default function DashboardPage() {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [view, setView] = useState<View>("documents");
  const [selectedDoc, setSelectedDoc] = useState<Document | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

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
        if (!r.ok) throw new Error();
        return r.json() as Promise<UserProfile>;
      })
      .then(setUser)
      .catch(() => {
        window.location.href = "/login";
      });
  }, []);

  const handleLogout = useCallback(async () => {
    const refresh = getRefreshToken();
    if (refresh) {
      try {
        await authApi.logout(refresh);
      } catch {
        /* ok */
      }
    }
    clearTokens();
    window.location.href = "/login";
  }, []);

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
        <div
          style={{
            width: 32,
            height: 32,
            border: "3px solid var(--brand-200)",
            borderTopColor: "var(--brand-500)",
            borderRadius: "50%",
            animation: "spin 0.6s linear infinite",
          }}
        />
      </div>
    );

  const goTo = (key: View) => {
    setView(key);
    setSelectedDoc(null);
  };

  return (
    <div className="layout">
      {/* Top bar */}
      <header className="topbar">
        <div className="topbar-brand">
          <div className="topbar-logo">D</div>
          <span>IDMS</span>
        </div>

        <button
          className="topbar-search"
          onClick={() => goTo("search")}
          aria-label="Search documents"
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
            <path d={SEARCH_ICON} />
          </svg>
          <span>Search documents</span>
        </button>

        <div className="topbar-right">
          <span style={{ color: "var(--navy-300)" }}>
            <UsageIndicator />
          </span>
          <div className="topbar-user">
            <b>{user.email}</b>
            {user.role}
          </div>
          <button onClick={handleLogout} className="topbar-signout">
            Sign out
          </button>
        </div>
      </header>

      {/* Sidebar */}
      <aside className="sidebar">
        <nav aria-label="Main">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.key}
              onClick={() => goTo(item.key)}
              className={`nav-item${view === item.key ? " active" : ""}`}
              aria-current={view === item.key ? "page" : undefined}
              title={item.label}
            >
              <svg
                width="18"
                height="18"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
                viewBox="0 0 24 24"
                style={{ flexShrink: 0 }}
              >
                <path d={item.icon} />
              </svg>
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
      </aside>

      {/* Main content */}
      <main className="main-content">
        <div className="pagebar">
          <h1>
            {selectedDoc
              ? selectedDoc.filename
              : NAV_ITEMS.find((n) => n.key === view)?.label}
          </h1>
          {selectedDoc && (
            <button
              onClick={() => setSelectedDoc(null)}
              className="btn-ghost"
              style={{ marginLeft: "auto", fontSize: "0.8rem" }}
            >
              <svg
                width="14"
                height="14"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                viewBox="0 0 24 24"
                style={{ marginRight: "0.3rem", verticalAlign: "middle" }}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M10 19l-7-7m0 0l7-7m-7 7h18"
                />
              </svg>
              Back to documents
            </button>
          )}
        </div>

        {/* Document split viewer */}
        {selectedDoc ? (
          <DocumentViewer doc={selectedDoc} />
        ) : (
          <div className="page-body">
            {view === "documents" && (
              <div className="fade-in">
                <DocumentList
                  onSelectDocument={(doc) => {
                    if (doc) setSelectedDoc(doc);
                  }}
                  refreshKey={refreshKey}
                />
              </div>
            )}

            {view === "upload" && (
              <div className="card fade-in" style={{ padding: "1.5rem" }}>
                <UploadZone
                  onUploadComplete={() => setRefreshKey((k) => k + 1)}
                />
              </div>
            )}

            {view === "search" && (
              <div className="card fade-in" style={{ padding: "1.5rem" }}>
                <SearchBox />
              </div>
            )}

            {view === "extract" && (
              <div className="card fade-in" style={{ padding: "1.5rem" }}>
                <ExtractionsPanel />
              </div>
            )}

            {view === "compare" && (
              <div className="card fade-in" style={{ padding: "1.5rem" }}>
                <DocumentCompare />
              </div>
            )}

            {view === "ai" && (
              <div className="card fade-in" style={{ padding: "1.5rem" }}>
                <AiChat />
              </div>
            )}

            {view === "team" && user && (
              <div className="card fade-in" style={{ padding: "1.5rem" }}>
                <TeamPanel
                  currentUserId={user.id}
                  currentUserRole={user.role}
                />
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
