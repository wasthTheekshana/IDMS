"use client";

import { useEffect } from "react";
import { getAccessToken } from "@/lib/auth";

export default function Home() {
  useEffect(() => {
    if (getAccessToken()) {
      window.location.href = "/dashboard";
    } else {
      window.location.href = "/login";
    }
  }, []);

  return (
    <main
      style={{
        fontFamily: "system-ui",
        padding: "4rem",
        textAlign: "center",
      }}
    >
      <p>Redirecting…</p>
    </main>
  );
}
