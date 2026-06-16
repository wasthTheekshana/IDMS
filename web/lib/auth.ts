const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text);
  }
  return res.json() as Promise<T>;
}

export const authApi = {
  register: (orgName: string, email: string, password: string) =>
    post<TokenResponse>("/api/v1/auth/register", {
      org_name: orgName,
      email,
      password,
    }),
  login: (email: string, password: string) =>
    post<TokenResponse>("/api/v1/auth/login", { email, password }),
  logout: (refreshToken: string) =>
    post<void>("/api/v1/auth/logout", { refresh_token: refreshToken }),
};

export function saveTokens(tokens: TokenResponse): void {
  sessionStorage.setItem("access_token", tokens.access_token);
  sessionStorage.setItem("refresh_token", tokens.refresh_token);
}

export function getAccessToken(): string | null {
  return sessionStorage.getItem("access_token");
}

export function getRefreshToken(): string | null {
  return sessionStorage.getItem("refresh_token");
}

export function clearTokens(): void {
  sessionStorage.removeItem("access_token");
  sessionStorage.removeItem("refresh_token");
}
