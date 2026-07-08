"use client";

import { useCallback, useEffect, useState } from "react";
import { getAccessToken } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface TeamUser {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

interface Props {
  currentUserId: string;
  currentUserRole: string;
}

const ASSIGNABLE: Record<string, string[]> = {
  owner: ["admin", "member", "viewer"],
  admin: ["member", "viewer"],
};

export default function TeamPanel({ currentUserId, currentUserRole }: Props) {
  const [users, setUsers] = useState<TeamUser[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("member");
  const [creating, setCreating] = useState(false);

  const assignable = ASSIGNABLE[currentUserRole] ?? [];
  const canManage = assignable.length > 0;

  const authHeaders = useCallback(
    (): Record<string, string> => ({
      Authorization: `Bearer ${getAccessToken()}`,
      "Content-Type": "application/json",
    }),
    [],
  );

  const load = useCallback(async () => {
    const res = await fetch(`${API}/api/v1/users`, { headers: authHeaders() });
    if (res.ok) setUsers(await res.json());
  }, [authHeaders]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setCreating(true);
    try {
      const res = await fetch(`${API}/api/v1/users`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ email, password, role }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `Failed (${res.status})`);
      }
      setEmail("");
      setPassword("");
      setRole("member");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create user");
    } finally {
      setCreating(false);
    }
  }

  async function patchUser(id: string, body: Record<string, unknown>) {
    setError(null);
    const res = await fetch(`${API}/api/v1/users/${id}`, {
      method: "PATCH",
      headers: authHeaders(),
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      setError(data?.detail ?? `Update failed (${res.status})`);
      return;
    }
    await load();
  }

  const manageable = (u: TeamUser) =>
    canManage &&
    u.id !== currentUserId &&
    u.role !== "owner" &&
    assignable.includes(u.role);

  return (
    <div style={{ maxWidth: 720 }}>
      {canManage && (
        <form
          onSubmit={handleCreate}
          style={{
            display: "flex",
            gap: "0.5rem",
            flexWrap: "wrap",
            alignItems: "center",
            marginBottom: "1.25rem",
            padding: "1rem",
            border: "1px solid var(--gray-200)",
            borderRadius: 8,
            background: "#fff",
          }}
        >
          <strong style={{ width: "100%", fontSize: "0.85rem" }}>
            Add a team member
          </strong>
          <input
            type="email"
            required
            placeholder="email@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            style={{ flex: 2, minWidth: 180, padding: "0.45rem 0.6rem" }}
          />
          <input
            type="password"
            required
            minLength={10}
            placeholder="Initial password (min 10 chars)"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={{ flex: 2, minWidth: 180, padding: "0.45rem 0.6rem" }}
          />
          <select
            value={role}
            onChange={(e) => setRole(e.target.value)}
            style={{ flex: 1, minWidth: 100, padding: "0.45rem 0.4rem" }}
          >
            {assignable.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
          <button type="submit" className="btn-primary" disabled={creating}>
            {creating ? "Creating…" : "Create account"}
          </button>
          <span
            style={{
              width: "100%",
              fontSize: "0.72rem",
              color: "var(--gray-500)",
            }}
          >
            Share the password with the user directly — no email is sent.
          </span>
        </form>
      )}

      {error && (
        <div
          style={{
            color: "var(--red-600, #dc2626)",
            fontSize: "0.8rem",
            marginBottom: "0.75rem",
          }}
        >
          {error}
        </div>
      )}

      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr
            style={{
              textAlign: "left",
              fontSize: "0.72rem",
              color: "var(--gray-500)",
              textTransform: "uppercase",
            }}
          >
            <th style={{ padding: "0.5rem" }}>Email</th>
            <th style={{ padding: "0.5rem" }}>Role</th>
            <th style={{ padding: "0.5rem" }}>Status</th>
            {canManage && <th style={{ padding: "0.5rem" }}>Actions</th>}
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr
              key={u.id}
              style={{
                borderTop: "1px solid var(--gray-200)",
                fontSize: "0.85rem",
                opacity: u.is_active ? 1 : 0.55,
              }}
            >
              <td style={{ padding: "0.55rem 0.5rem" }}>
                {u.email}
                {u.id === currentUserId && (
                  <span style={{ color: "var(--gray-400)" }}> (you)</span>
                )}
              </td>
              <td style={{ padding: "0.55rem 0.5rem" }}>
                {manageable(u) ? (
                  <select
                    value={u.role}
                    onChange={(e) => patchUser(u.id, { role: e.target.value })}
                    style={{ padding: "0.25rem" }}
                  >
                    {assignable.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                ) : (
                  u.role
                )}
              </td>
              <td style={{ padding: "0.55rem 0.5rem" }}>
                {u.is_active ? "Active" : "Deactivated"}
              </td>
              {canManage && (
                <td style={{ padding: "0.55rem 0.5rem" }}>
                  {manageable(u) && (
                    <button
                      className="btn-ghost"
                      style={{ fontSize: "0.75rem" }}
                      onClick={() =>
                        patchUser(u.id, { is_active: !u.is_active })
                      }
                    >
                      {u.is_active ? "Deactivate" : "Reactivate"}
                    </button>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
