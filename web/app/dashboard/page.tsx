"use client";

import { useEffect, useState } from "react";
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  authApi,
} from "@/lib/auth";
import UploadZone from "@/components/UploadZone";

interface UserProfile {
  id: string;
  org_id: string;
  email: string;
  role: string;
  is_active: boolean;
}

export default function DashboardPage() {
  const [user, setUser] = useState<UserProfile | null>(null);

  useEffect(() => {
    const token = getAccessToken();
    if (!token) {
      window.location.href = "/login";
      return;
    }
    fetch("http://localhost:8000/api/v1/users/me", {
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
        // continue even if logout call fails
      }
    }
    clearTokens();
    window.location.href = "/login";
  }

  if (!user) return <p style={{ padding: "2rem" }}>Loading…</p>;

  return (
    <main
      style={{
        maxWidth: 800,
        margin: "2rem auto",
        fontFamily: "system-ui",
        padding: "0 1rem",
      }}
    >
      <h1>Dashboard</h1>
      <p>
        Welcome, <strong>{user.email}</strong>{" "}
        <span style={{ color: "#666" }}>({user.role})</span>
      </p>
      <p>
        Organisation ID: <code>{user.org_id}</code>
      </p>
      <button
        onClick={handleLogout}
        style={{ padding: "0.5rem 1.5rem", marginTop: "1rem" }}
      >
        Sign out
      </button>

      <hr style={{ margin: "2rem 0" }} />
      <h2>Upload Document</h2>
      <UploadZone />
    </main>
  );
}
