import { getAccessToken } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface AdminOrganization {
  id: string;
  name: string;
  slug: string;
  plan: string;
  is_suspended: boolean;
  monthly_page_quota: number;
  pages_used_this_month: number;
  user_count: number;
  document_count: number;
  ai_tokens_total: number;
  ai_cost_total_usd: number;
  ai_qa_enabled: boolean;
  ai_summarization_enabled: boolean;
  ai_search_answer_enabled: boolean;
  ai_extraction_enabled: boolean;
}

export interface AdminOrgUpdate {
  is_suspended?: boolean;
  ai_qa_enabled?: boolean;
  ai_summarization_enabled?: boolean;
  ai_search_answer_enabled?: boolean;
  ai_extraction_enabled?: boolean;
}

export interface AdminDocument {
  id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  status: string;
  page_count: number | null;
  uploaded_by_email: string;
  created_at: string;
}

export interface AdminProfile {
  id: string;
  email: string;
}

function authHeaders(): HeadersInit {
  return { Authorization: `Bearer ${getAccessToken()}` };
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<T>;
}

export const adminApi = {
  getMe: () => get<AdminProfile>("/api/v1/platform-admin/me"),
  getOrganizations: () =>
    get<AdminOrganization[]>("/api/v1/platform-admin/organizations"),
  getOrgDocuments: (orgId: string) =>
    get<AdminDocument[]>(
      `/api/v1/platform-admin/organizations/${orgId}/documents`,
    ),
  updateOrganization: async (
    orgId: string,
    body: AdminOrgUpdate,
  ): Promise<AdminOrganization> => {
    const res = await fetch(
      `${API}/api/v1/platform-admin/organizations/${orgId}`,
      {
        method: "PATCH",
        headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    );
    if (!res.ok) throw new Error(await res.text());
    return res.json() as Promise<AdminOrganization>;
  },
};
