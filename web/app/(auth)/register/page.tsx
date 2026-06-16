"use client";

import { useState } from "react";
import { authApi, saveTokens } from "@/lib/auth";

export default function RegisterPage() {
  const [orgName, setOrgName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const tokens = await authApi.register(orgName, email, password);
      saveTokens(tokens);
      window.location.href = "/dashboard";
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main
      style={{
        maxWidth: 400,
        margin: "4rem auto",
        fontFamily: "system-ui",
        padding: "0 1rem",
      }}
    >
      <h1>Create your organisation</h1>
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: "1rem" }}>
          <label>Organisation name</label>
          <input
            type="text"
            value={orgName}
            onChange={(e) => setOrgName(e.target.value)}
            required
            style={{
              display: "block",
              width: "100%",
              padding: "0.5rem",
              marginTop: "0.25rem",
            }}
          />
        </div>
        <div style={{ marginBottom: "1rem" }}>
          <label>Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            style={{
              display: "block",
              width: "100%",
              padding: "0.5rem",
              marginTop: "0.25rem",
            }}
          />
        </div>
        <div style={{ marginBottom: "1rem" }}>
          <label>Password (min 10 characters)</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={10}
            style={{
              display: "block",
              width: "100%",
              padding: "0.5rem",
              marginTop: "0.25rem",
            }}
          />
        </div>
        {error && <p style={{ color: "red" }}>{error}</p>}
        <button
          type="submit"
          disabled={loading}
          style={{ padding: "0.5rem 1.5rem" }}
        >
          {loading ? "Creating…" : "Create account"}
        </button>
      </form>
      <p style={{ marginTop: "1rem" }}>
        Already have an account? <a href="/login">Sign in</a>
      </p>
    </main>
  );
}
