"use client";

import { useState } from "react";
import { getAccessToken } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const ALLOWED_TYPES = [
  "application/pdf",
  "image/jpeg",
  "image/png",
  "image/tiff",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
];

type UploadStatus =
  | "idle"
  | "requesting"
  | "uploading"
  | "processing"
  | "ready"
  | "error";

interface UploadState {
  status: UploadStatus;
  message?: string;
  docId?: string;
}

export default function UploadZone() {
  const [state, setState] = useState<UploadState>({ status: "idle" });

  async function handleFile(file: File) {
    if (!ALLOWED_TYPES.includes(file.type)) {
      setState({ status: "error", message: `Unsupported type: ${file.type}` });
      return;
    }
    if (file.size > 50 * 1024 * 1024) {
      setState({ status: "error", message: "File exceeds 50 MB limit" });
      return;
    }

    const token = getAccessToken();
    setState({ status: "requesting" });

    const initRes = await fetch(`${API}/api/v1/documents/upload-url`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        filename: file.name,
        content_type: file.type,
        size_bytes: file.size,
      }),
    });
    if (!initRes.ok) {
      setState({ status: "error", message: await initRes.text() });
      return;
    }
    const { document_id, upload_url } = await initRes.json();

    setState({ status: "uploading" });
    const uploadRes = await fetch(upload_url, {
      method: "PUT",
      headers: { "Content-Type": file.type },
      body: file,
    });
    if (!uploadRes.ok) {
      setState({ status: "error", message: "Upload to storage failed" });
      return;
    }

    const confirmRes = await fetch(`${API}/api/v1/documents/confirm`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ document_id }),
    });
    if (!confirmRes.ok) {
      setState({ status: "error", message: await confirmRes.text() });
      return;
    }

    setState({ status: "processing", docId: document_id });

    const evtSource = new EventSource(
      `${API}/api/v1/documents/${document_id}/status`,
    );
    evtSource.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.status === "ready") {
        setState({ status: "ready", docId: document_id });
        evtSource.close();
      } else if (data.status === "failed") {
        setState({
          status: "error",
          message: data.error_message ?? "Processing failed",
        });
        evtSource.close();
      }
    };
    evtSource.onerror = () => evtSource.close();
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }

  return (
    <div
      onDrop={handleDrop}
      onDragOver={(e) => e.preventDefault()}
      style={{
        border: "2px dashed #ccc",
        borderRadius: 8,
        padding: "2rem",
        textAlign: "center",
        marginTop: "1.5rem",
        background: state.status === "error" ? "#fff0f0" : "#fafafa",
      }}
    >
      {state.status === "idle" && (
        <>
          <p style={{ marginBottom: "1rem" }}>
            Drag a PDF, image, or DOCX here — or choose a file
          </p>
          <input
            type="file"
            accept=".pdf,.jpg,.jpeg,.png,.tiff,.docx"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleFile(f);
            }}
          />
        </>
      )}
      {state.status === "requesting" && <p>Preparing upload…</p>}
      {state.status === "uploading" && <p>Uploading to storage…</p>}
      {state.status === "processing" && (
        <p>Processing document — OCR in progress…</p>
      )}
      {state.status === "ready" && (
        <div>
          <p style={{ color: "green", fontWeight: "bold" }}>Document ready!</p>
          <p>
            ID: <code>{state.docId}</code>
          </p>
          <button
            onClick={() => setState({ status: "idle" })}
            style={{ marginTop: "0.5rem" }}
          >
            Upload another
          </button>
        </div>
      )}
      {state.status === "error" && (
        <div>
          <p style={{ color: "red" }}>Error: {state.message}</p>
          <button onClick={() => setState({ status: "idle" })}>
            Try again
          </button>
        </div>
      )}
    </div>
  );
}
