"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getAccessToken,
  getRefreshToken,
  authApi,
  clearTokens,
} from "@/lib/auth";
import {
  adminApi,
  type AdminDocument,
  type AdminOrganization,
  type AdminOrgUpdate,
} from "@/lib/admin";

const TOGGLE_FIELDS: { key: keyof AdminOrgUpdate; label: string }[] = [
  { key: "ai_qa_enabled", label: "Q&A / Chat" },
  { key: "ai_summarization_enabled", label: "Summarization" },
  { key: "ai_search_answer_enabled", label: "Search AI Answer" },
  { key: "ai_extraction_enabled", label: "Extraction" },
];

export default function AdminPage() {
  const [orgs, setOrgs] = useState<AdminOrganization[] | null>(null);
  const [expandedOrgId, setExpandedOrgId] = useState<string | null>(null);
  const [docs, setDocs] = useState<AdminDocument[]>([]);
  const [error, setError] = useState("");

  const loadOrgs = useCallback(() => {
    adminApi
      .getOrganizations()
      .then(setOrgs)
      .catch(() => {
        window.location.href = "/login";
      });
  }, []);

  useEffect(() => {
    if (!getAccessToken()) {
      window.location.href = "/login";
      return;
    }
    adminApi.getMe().catch(() => {
      window.location.href = "/login";
    });
    loadOrgs();
  }, [loadOrgs]);

  async function handleToggle(
    org: AdminOrganization,
    field: keyof AdminOrgUpdate,
  ) {
    setError("");
    try {
      const updated = await adminApi.updateOrganization(org.id, {
        [field]: !org[field],
      } as AdminOrgUpdate);
      setOrgs((prev) =>
        (prev ?? []).map((o) => (o.id === updated.id ? updated : o)),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    }
  }

  async function handleSuspendToggle(org: AdminOrganization) {
    await handleToggle(org, "is_suspended");
  }

  async function toggleDocuments(orgId: string) {
    if (expandedOrgId === orgId) {
      setExpandedOrgId(null);
      setDocs([]);
      return;
    }
    setExpandedOrgId(orgId);
    try {
      setDocs(await adminApi.getOrgDocuments(orgId));
    } catch {
      setDocs([]);
    }
  }

  async function handleLogout() {
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
  }

  if (!orgs) {
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
  }

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto", padding: "2rem 1.5rem" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "1.5rem",
        }}
      >
        <h1
          style={{
            fontSize: "1.4rem",
            fontWeight: 700,
            color: "var(--gray-900)",
          }}
        >
          Platform Admin — Organizations
        </h1>
        <button onClick={handleLogout} className="btn-secondary">
          Log out
        </button>
      </div>

      {error && (
        <div
          style={{
            padding: "0.6rem 0.85rem",
            background: "var(--red-50)",
            color: "var(--red-700)",
            borderRadius: "var(--radius-sm)",
            fontSize: "0.85rem",
            marginBottom: "1rem",
          }}
        >
          {error}
        </div>
      )}

      <div className="card" style={{ overflowX: "auto" }}>
        <table
          style={{
            width: "100%",
            borderCollapse: "collapse",
            fontSize: "0.85rem",
          }}
        >
          <thead>
            <tr style={{ borderBottom: "1px solid var(--gray-100)" }}>
              <th style={{ textAlign: "left", padding: "0.6rem" }}>
                Organization
              </th>
              <th style={{ textAlign: "left", padding: "0.6rem" }}>Plan</th>
              <th style={{ textAlign: "right", padding: "0.6rem" }}>Users</th>
              <th style={{ textAlign: "right", padding: "0.6rem" }}>Docs</th>
              <th style={{ textAlign: "right", padding: "0.6rem" }}>
                AI Tokens
              </th>
              <th style={{ textAlign: "right", padding: "0.6rem" }}>AI Cost</th>
              <th style={{ textAlign: "right", padding: "0.6rem" }}>
                Quota (used/total)
              </th>
              {TOGGLE_FIELDS.map((f) => (
                <th
                  key={f.key}
                  style={{ textAlign: "center", padding: "0.6rem" }}
                >
                  {f.label}
                </th>
              ))}
              <th style={{ textAlign: "center", padding: "0.6rem" }}>
                Suspended
              </th>
              <th style={{ textAlign: "center", padding: "0.6rem" }}>
                Documents
              </th>
            </tr>
          </thead>
          <tbody>
            {orgs.map((org) => (
              <>
                <tr
                  key={org.id}
                  style={{ borderBottom: "1px solid var(--gray-100)" }}
                >
                  <td style={{ padding: "0.6rem", fontWeight: 500 }}>
                    {org.name}
                  </td>
                  <td style={{ padding: "0.6rem", color: "var(--gray-600)" }}>
                    {org.plan}
                  </td>
                  <td style={{ padding: "0.6rem", textAlign: "right" }}>
                    {org.user_count}
                  </td>
                  <td style={{ padding: "0.6rem", textAlign: "right" }}>
                    {org.document_count}
                  </td>
                  <td style={{ padding: "0.6rem", textAlign: "right" }}>
                    {org.ai_tokens_total.toLocaleString()}
                  </td>
                  <td style={{ padding: "0.6rem", textAlign: "right" }}>
                    ${org.ai_cost_total_usd.toFixed(4)}
                  </td>
                  <td style={{ padding: "0.6rem", textAlign: "right" }}>
                    {org.pages_used_this_month}/{org.monthly_page_quota}
                  </td>
                  {TOGGLE_FIELDS.map((f) => (
                    <td
                      key={f.key}
                      style={{ padding: "0.6rem", textAlign: "center" }}
                    >
                      <input
                        type="checkbox"
                        checked={Boolean(org[f.key])}
                        onChange={() => handleToggle(org, f.key)}
                      />
                    </td>
                  ))}
                  <td style={{ padding: "0.6rem", textAlign: "center" }}>
                    <input
                      type="checkbox"
                      checked={org.is_suspended}
                      onChange={() => handleSuspendToggle(org)}
                    />
                  </td>
                  <td style={{ padding: "0.6rem", textAlign: "center" }}>
                    <button
                      onClick={() => toggleDocuments(org.id)}
                      className="btn-secondary"
                      style={{ fontSize: "0.75rem", padding: "0.3rem 0.6rem" }}
                    >
                      {expandedOrgId === org.id ? "Hide" : "View"}
                    </button>
                  </td>
                </tr>
                {expandedOrgId === org.id && (
                  <tr key={`${org.id}-docs`}>
                    <td
                      colSpan={9 + TOGGLE_FIELDS.length}
                      style={{
                        padding: "0.75rem 1.5rem",
                        background: "var(--gray-50)",
                      }}
                    >
                      {docs.length === 0 ? (
                        <span style={{ color: "var(--gray-500)" }}>
                          No documents.
                        </span>
                      ) : (
                        <table style={{ width: "100%", fontSize: "0.8rem" }}>
                          <thead>
                            <tr>
                              <th
                                style={{ textAlign: "left", padding: "0.3rem" }}
                              >
                                Filename
                              </th>
                              <th
                                style={{ textAlign: "left", padding: "0.3rem" }}
                              >
                                Status
                              </th>
                              <th
                                style={{
                                  textAlign: "right",
                                  padding: "0.3rem",
                                }}
                              >
                                Pages
                              </th>
                              <th
                                style={{ textAlign: "left", padding: "0.3rem" }}
                              >
                                Uploaded By
                              </th>
                              <th
                                style={{ textAlign: "left", padding: "0.3rem" }}
                              >
                                Created
                              </th>
                            </tr>
                          </thead>
                          <tbody>
                            {docs.map((d) => (
                              <tr key={d.id}>
                                <td style={{ padding: "0.3rem" }}>
                                  {d.filename}
                                </td>
                                <td style={{ padding: "0.3rem" }}>
                                  {d.status}
                                </td>
                                <td
                                  style={{
                                    padding: "0.3rem",
                                    textAlign: "right",
                                  }}
                                >
                                  {d.page_count ?? "—"}
                                </td>
                                <td style={{ padding: "0.3rem" }}>
                                  {d.uploaded_by_email}
                                </td>
                                <td style={{ padding: "0.3rem" }}>
                                  {new Date(d.created_at).toLocaleString()}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
