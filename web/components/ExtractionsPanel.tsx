"use client";

import { useEffect, useState, useCallback } from "react";
import { getAccessToken } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface FieldDef {
  key: string;
  label: string;
  type: string;
}
interface Template {
  id: string;
  name: string;
  description: string | null;
  fields: FieldDef[];
}
interface DocOption {
  id: string;
  filename: string;
  status: string;
}
interface ExtractionRow {
  document_id: string;
  filename: string;
  template_name: string;
  data: Record<string, unknown>;
  created_at: string;
}

export default function ExtractionsPanel() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [extractions, setExtractions] = useState<ExtractionRow[]>([]);
  const [docs, setDocs] = useState<DocOption[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<Template | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<string>("");
  const [selectedDoc, setSelectedDoc] = useState<string>("");
  const [extracting, setExtracting] = useState(false);
  const [exportLoading, setExportLoading] = useState<string | null>(null);

  const token = getAccessToken();

  const fetchAll = useCallback(async () => {
    if (!token) return;
    const headers = { Authorization: `Bearer ${token}` };
    const [tRes, eRes, dRes] = await Promise.all([
      fetch(`${API}/api/v1/templates`, { headers }),
      fetch(`${API}/api/v1/templates/extractions`, { headers }),
      fetch(`${API}/api/v1/documents`, { headers }),
    ]);
    if (tRes.ok) setTemplates(await tRes.json());
    if (eRes.ok) setExtractions(await eRes.json());
    if (dRes.ok) {
      const all = await dRes.json();
      setDocs(
        all.filter(
          (d: DocOption) => d.status === "ready" || d.status === "indexed",
        ),
      );
    }
  }, [token]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  async function handleExtract() {
    if (!selectedDoc || !selectedTemplate) return;
    setExtracting(true);
    try {
      const res = await fetch(`${API}/api/v1/templates/extract`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          document_id: selectedDoc,
          template_id: selectedTemplate,
        }),
      });
      if (res.ok) await fetchAll();
    } catch {
      /* ignore */
    } finally {
      setExtracting(false);
    }
  }

  async function handleDeleteTemplate(id: string) {
    if (!confirm("Delete this template? Existing extractions will remain."))
      return;
    try {
      await fetch(`${API}/api/v1/templates/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (selectedTemplate === id) setSelectedTemplate("");
      await fetchAll();
    } catch {
      /* ignore */
    }
  }

  async function handleExport(format: "csv" | "excel") {
    setExportLoading(format);
    try {
      const res = await fetch(
        `${API}/api/v1/templates/extractions/export/${format}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (res.ok) {
        const blob = await res.blob();
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = format === "csv" ? "extractions.csv" : "extractions.xlsx";
        a.click();
        URL.revokeObjectURL(a.href);
      }
    } catch {
      /* ignore */
    } finally {
      setExportLoading(null);
    }
  }

  const allFieldKeys = Array.from(
    new Set(
      extractions.flatMap((e) =>
        Object.keys(e.data).filter((k) => !k.startsWith("_")),
      ),
    ),
  );

  return (
    <div>
      {/* Template management */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "1rem",
        }}
      >
        <h3
          style={{
            fontSize: "0.95rem",
            fontWeight: 600,
            color: "var(--gray-900)",
          }}
        >
          Templates ({templates.length})
        </h3>
        <button
          onClick={() => {
            setShowCreate(true);
            setEditingTemplate(null);
          }}
          className="btn-primary"
          style={{ fontSize: "0.8rem" }}
        >
          + New Template
        </button>
      </div>

      {/* Create / Edit form */}
      {(showCreate || editingTemplate) && (
        <TemplateForm
          initial={editingTemplate}
          onSaved={() => {
            setShowCreate(false);
            setEditingTemplate(null);
            fetchAll();
          }}
          onCancel={() => {
            setShowCreate(false);
            setEditingTemplate(null);
          }}
        />
      )}

      {/* Template cards */}
      {templates.length > 0 && !editingTemplate && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "0.5rem",
            marginBottom: "1.5rem",
          }}
        >
          {templates.map((t) => (
            <div
              key={t.id}
              style={{
                padding: "0.65rem 0.85rem",
                background: "var(--gray-50)",
                border: "1px solid var(--gray-200)",
                borderRadius: "var(--radius-md)",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.5rem",
                  }}
                >
                  <span
                    style={{
                      fontWeight: 500,
                      fontSize: "0.88rem",
                      color: "var(--gray-800)",
                    }}
                  >
                    {t.name}
                  </span>
                  <span
                    style={{
                      fontSize: "0.72rem",
                      color: "var(--gray-400)",
                      background: "var(--gray-100)",
                      padding: "0.1rem 0.4rem",
                      borderRadius: "999px",
                    }}
                  >
                    {t.fields.length} field{t.fields.length !== 1 ? "s" : ""}
                  </span>
                </div>
                {t.description && (
                  <p
                    style={{
                      fontSize: "0.78rem",
                      color: "var(--gray-500)",
                      marginTop: "0.15rem",
                    }}
                  >
                    {t.description}
                  </p>
                )}
                <div
                  style={{
                    display: "flex",
                    gap: "0.3rem",
                    marginTop: "0.3rem",
                    flexWrap: "wrap",
                  }}
                >
                  {t.fields.map((f) => (
                    <span
                      key={f.key}
                      style={{
                        fontSize: "0.7rem",
                        padding: "0.1rem 0.35rem",
                        background: "var(--brand-50)",
                        color: "var(--brand-700)",
                        borderRadius: "4px",
                        fontWeight: 500,
                      }}
                    >
                      {f.label}
                    </span>
                  ))}
                </div>
              </div>
              <div
                style={{
                  display: "flex",
                  gap: "0.25rem",
                  flexShrink: 0,
                  marginLeft: "0.5rem",
                }}
              >
                <button
                  onClick={() => {
                    setEditingTemplate(t);
                    setShowCreate(false);
                  }}
                  className="btn-ghost"
                  style={{ padding: "0.3rem 0.5rem", fontSize: "0.78rem" }}
                  title="Edit template"
                >
                  <svg
                    width="14"
                    height="14"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                    />
                  </svg>
                </button>
                <button
                  onClick={() => handleDeleteTemplate(t.id)}
                  className="btn-ghost"
                  style={{
                    padding: "0.3rem 0.5rem",
                    fontSize: "0.78rem",
                    color: "var(--red-500)",
                  }}
                  title="Delete template"
                >
                  <svg
                    width="14"
                    height="14"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                    />
                  </svg>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Extract form */}
      <div className="card" style={{ padding: "1rem", marginBottom: "1.5rem" }}>
        <h3
          style={{
            fontSize: "0.9rem",
            fontWeight: 600,
            color: "var(--gray-900)",
            marginBottom: "0.75rem",
          }}
        >
          Run Extraction
        </h3>
        <div
          style={{
            display: "flex",
            gap: "0.5rem",
            flexWrap: "wrap",
            alignItems: "flex-end",
          }}
        >
          <div style={{ flex: 1, minWidth: 150 }}>
            <label
              style={{
                fontSize: "0.75rem",
                color: "var(--gray-500)",
                display: "block",
                marginBottom: "0.2rem",
              }}
            >
              Document
            </label>
            <select
              value={selectedDoc}
              onChange={(e) => setSelectedDoc(e.target.value)}
              style={{ fontSize: "0.85rem" }}
            >
              <option value="">Select document...</option>
              {docs.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.filename}
                </option>
              ))}
            </select>
          </div>
          <div style={{ flex: 1, minWidth: 150 }}>
            <label
              style={{
                fontSize: "0.75rem",
                color: "var(--gray-500)",
                display: "block",
                marginBottom: "0.2rem",
              }}
            >
              Template
            </label>
            <select
              value={selectedTemplate}
              onChange={(e) => setSelectedTemplate(e.target.value)}
              style={{ fontSize: "0.85rem" }}
            >
              <option value="">Select template...</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>
          <button
            onClick={handleExtract}
            disabled={!selectedDoc || !selectedTemplate || extracting}
            className="btn-primary"
            style={{ whiteSpace: "nowrap" }}
          >
            {extracting ? "Extracting..." : "Extract"}
          </button>
        </div>
      </div>

      {/* Results table */}
      {extractions.length > 0 && (
        <div>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "0.75rem",
            }}
          >
            <h3
              style={{
                fontSize: "0.95rem",
                fontWeight: 600,
                color: "var(--gray-900)",
              }}
            >
              Extracted Data ({extractions.length})
            </h3>
            <div style={{ display: "flex", gap: "0.35rem" }}>
              <button
                onClick={() => handleExport("csv")}
                disabled={exportLoading === "csv"}
                className="btn-secondary"
                style={{
                  fontSize: "0.78rem",
                  padding: "0.3rem 0.65rem",
                  display: "flex",
                  alignItems: "center",
                  gap: "0.3rem",
                }}
              >
                <svg
                  width="14"
                  height="14"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                  />
                </svg>
                {exportLoading === "csv" ? "..." : "CSV"}
              </button>
              <button
                onClick={() => handleExport("excel")}
                disabled={exportLoading === "excel"}
                className="btn-secondary"
                style={{
                  fontSize: "0.78rem",
                  padding: "0.3rem 0.65rem",
                  display: "flex",
                  alignItems: "center",
                  gap: "0.3rem",
                }}
              >
                <svg
                  width="14"
                  height="14"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                  />
                </svg>
                {exportLoading === "excel" ? "..." : "Excel"}
              </button>
            </div>
          </div>

          <div
            style={{
              overflowX: "auto",
              borderRadius: "var(--radius-md)",
              border: "1px solid var(--gray-200)",
            }}
          >
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontSize: "0.82rem",
              }}
            >
              <thead>
                <tr style={{ background: "var(--gray-50)" }}>
                  <th
                    style={{
                      padding: "0.55rem 0.6rem",
                      textAlign: "left",
                      fontWeight: 600,
                      color: "var(--gray-600)",
                      fontSize: "0.73rem",
                      textTransform: "uppercase",
                      letterSpacing: "0.03em",
                      borderBottom: "1px solid var(--gray-200)",
                    }}
                  >
                    Document
                  </th>
                  <th
                    style={{
                      padding: "0.55rem 0.6rem",
                      textAlign: "left",
                      fontWeight: 600,
                      color: "var(--gray-600)",
                      fontSize: "0.73rem",
                      textTransform: "uppercase",
                      letterSpacing: "0.03em",
                      borderBottom: "1px solid var(--gray-200)",
                    }}
                  >
                    Template
                  </th>
                  {allFieldKeys.map((key) => (
                    <th
                      key={key}
                      style={{
                        padding: "0.55rem 0.6rem",
                        textAlign: "left",
                        fontWeight: 600,
                        color: "var(--gray-600)",
                        fontSize: "0.73rem",
                        textTransform: "uppercase",
                        letterSpacing: "0.03em",
                        borderBottom: "1px solid var(--gray-200)",
                      }}
                    >
                      {key}
                    </th>
                  ))}
                  <th
                    style={{
                      padding: "0.55rem 0.6rem",
                      textAlign: "left",
                      fontWeight: 600,
                      color: "var(--gray-600)",
                      fontSize: "0.73rem",
                      textTransform: "uppercase",
                      letterSpacing: "0.03em",
                      borderBottom: "1px solid var(--gray-200)",
                    }}
                  >
                    Date
                  </th>
                  <th
                    style={{
                      padding: "0.55rem 0.6rem",
                      textAlign: "center",
                      fontWeight: 600,
                      color: "var(--gray-600)",
                      fontSize: "0.73rem",
                      textTransform: "uppercase",
                      letterSpacing: "0.03em",
                      borderBottom: "1px solid var(--gray-200)",
                      width: 60,
                    }}
                  ></th>
                </tr>
              </thead>
              <tbody>
                {extractions.map((row, i) => (
                  <tr
                    key={i}
                    style={{ borderBottom: "1px solid var(--gray-100)" }}
                  >
                    <td
                      style={{
                        padding: "0.5rem 0.6rem",
                        color: "var(--gray-800)",
                        maxWidth: 180,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {row.filename}
                    </td>
                    <td
                      style={{
                        padding: "0.5rem 0.6rem",
                        color: "var(--gray-500)",
                      }}
                    >
                      {row.template_name}
                    </td>
                    {allFieldKeys.map((key) => (
                      <td
                        key={key}
                        style={{
                          padding: "0.5rem 0.6rem",
                          color: "var(--gray-700)",
                        }}
                      >
                        {row.data[key] != null ? (
                          String(row.data[key])
                        ) : (
                          <span style={{ color: "var(--gray-300)" }}>—</span>
                        )}
                      </td>
                    ))}
                    <td
                      style={{
                        padding: "0.5rem 0.6rem",
                        color: "var(--gray-400)",
                        fontSize: "0.78rem",
                      }}
                    >
                      {new Date(row.created_at).toLocaleDateString()}
                    </td>
                    <td
                      style={{ padding: "0.5rem 0.3rem", textAlign: "center" }}
                    >
                      <RowDownloadButton row={row} fieldKeys={allFieldKeys} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {extractions.length === 0 && templates.length > 0 && (
        <div
          style={{
            padding: "2rem",
            textAlign: "center",
            color: "var(--gray-400)",
          }}
        >
          <p>
            No extractions yet. Select a document and template above to extract
            data.
          </p>
        </div>
      )}
    </div>
  );
}

function TemplateForm({
  initial,
  onSaved,
  onCancel,
}: {
  initial: Template | null;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const isEdit = !!initial;
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [fields, setFields] = useState<FieldDef[]>(
    initial?.fields.length
      ? initial.fields
      : [{ key: "", label: "", type: "text" }],
  );
  const [saving, setSaving] = useState(false);

  function addField() {
    setFields([...fields, { key: "", label: "", type: "text" }]);
  }
  function removeField(i: number) {
    setFields(fields.filter((_, idx) => idx !== i));
  }
  function updateField(i: number, patch: Partial<FieldDef>) {
    setFields(fields.map((f, idx) => (idx === i ? { ...f, ...patch } : f)));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const validFields = fields.filter((f) => f.key && f.label);
    if (!name || validFields.length === 0) return;
    setSaving(true);
    const token = getAccessToken();
    try {
      const url = isEdit
        ? `${API}/api/v1/templates/${initial!.id}`
        : `${API}/api/v1/templates`;
      const res = await fetch(url, {
        method: isEdit ? "PATCH" : "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name,
          description: description || null,
          fields: validFields,
        }),
      });
      if (res.ok) onSaved();
    } catch {
      /* ignore */
    } finally {
      setSaving(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="card"
      style={{ padding: "1rem", marginBottom: "1.5rem" }}
    >
      <h4
        style={{
          fontSize: "0.9rem",
          fontWeight: 600,
          color: "var(--gray-800)",
          marginBottom: "0.75rem",
        }}
      >
        {isEdit ? "Edit Template" : "New Template"}
      </h4>

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem" }}>
        <div style={{ flex: 1 }}>
          <label
            style={{
              fontSize: "0.75rem",
              color: "var(--gray-500)",
              display: "block",
              marginBottom: "0.2rem",
            }}
          >
            Name
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Invoice"
            required
            style={{ fontSize: "0.85rem" }}
          />
        </div>
        <div style={{ flex: 2 }}>
          <label
            style={{
              fontSize: "0.75rem",
              color: "var(--gray-500)",
              display: "block",
              marginBottom: "0.2rem",
            }}
          >
            Description
          </label>
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Optional description"
            style={{ fontSize: "0.85rem" }}
          />
        </div>
      </div>

      <label
        style={{
          fontSize: "0.75rem",
          color: "var(--gray-500)",
          display: "block",
          marginBottom: "0.35rem",
        }}
      >
        Fields
      </label>
      {fields.map((f, i) => (
        <div
          key={i}
          style={{
            display: "flex",
            gap: "0.4rem",
            marginBottom: "0.4rem",
            alignItems: "center",
          }}
        >
          <input
            type="text"
            value={f.key}
            onChange={(e) =>
              updateField(i, {
                key: e.target.value.replace(/\s/g, "_").toLowerCase(),
              })
            }
            placeholder="key"
            style={{ flex: 1, fontSize: "0.82rem" }}
          />
          <input
            type="text"
            value={f.label}
            onChange={(e) => updateField(i, { label: e.target.value })}
            placeholder="Label"
            style={{ flex: 2, fontSize: "0.82rem" }}
          />
          <select
            value={f.type}
            onChange={(e) => updateField(i, { type: e.target.value })}
            style={{ width: 90, fontSize: "0.82rem" }}
          >
            <option value="text">Text</option>
            <option value="number">Number</option>
            <option value="date">Date</option>
            <option value="currency">Currency</option>
          </select>
          {fields.length > 1 && (
            <button
              type="button"
              onClick={() => removeField(i)}
              className="btn-ghost"
              style={{
                color: "var(--red-500)",
                padding: "0.2rem 0.4rem",
                fontSize: "0.85rem",
              }}
            >
              ×
            </button>
          )}
        </div>
      ))}

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginTop: "0.75rem",
        }}
      >
        <button
          type="button"
          onClick={addField}
          className="btn-ghost"
          style={{ fontSize: "0.8rem" }}
        >
          + Add field
        </button>
        <div style={{ display: "flex", gap: "0.35rem" }}>
          <button
            type="button"
            onClick={onCancel}
            className="btn-secondary"
            style={{ fontSize: "0.8rem" }}
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            className="btn-primary"
            style={{ fontSize: "0.8rem" }}
          >
            {saving ? "Saving..." : isEdit ? "Save Changes" : "Create Template"}
          </button>
        </div>
      </div>
    </form>
  );
}

function RowDownloadButton({
  row,
  fieldKeys,
}: {
  row: ExtractionRow;
  fieldKeys: string[];
}) {
  function download() {
    const headers = ["Filename", "Template", "Extracted At", ...fieldKeys];
    const values = [
      row.filename,
      row.template_name,
      new Date(row.created_at).toISOString(),
      ...fieldKeys.map((k) => (row.data[k] != null ? String(row.data[k]) : "")),
    ];

    function csvEscape(v: string): string {
      if (v.includes(",") || v.includes('"') || v.includes("\n")) {
        return '"' + v.replace(/"/g, '""') + '"';
      }
      return v;
    }

    const csv = [
      headers.map(csvEscape).join(","),
      values.map(csvEscape).join(","),
    ].join("\n");

    const bom = "﻿";
    const blob = new Blob([bom + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const safeName = row.filename.replace(/\.[^.]+$/, "");
    a.download = `${safeName}-extraction.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <button
      onClick={download}
      className="btn-ghost"
      style={{ padding: "0.25rem 0.4rem" }}
      title="Download this extraction"
    >
      <svg
        width="14"
        height="14"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
        />
      </svg>
    </button>
  );
}
