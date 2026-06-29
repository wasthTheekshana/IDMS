# Intelligent Document Management System — Demo Script

> Estimated Duration: 10–12 minutes

---

## Opening (1 min)

**"Good [morning/afternoon], everyone. Today I'm going to walk you through our Intelligent Document Management System — a platform that lets organizations upload, understand, search, and extract structured data from their documents using AI."**

**"The system combines OCR, semantic search, and large language models to turn unstructured documents into searchable, queryable knowledge."**

---

## 1. Architecture Overview (1 min)

> Show: `infra/docker-compose.yml` or an architecture diagram

**"Here's what powers the system:"**

- **Frontend** — Next.js (React + TypeScript)
- **Backend API** — FastAPI (Python, async)
- **Database** — PostgreSQL with pgvector for vector embeddings
- **Object Storage** — Cloudflare R2 (S3-compatible)
- **Task Queue** — Celery + Redis for background processing
- **AI Stack** — Mistral (OCR + embeddings), Groq LLaMA 3.3 (LLM), Google Gemini (fallback)

**"Everything runs in Docker containers and is fully multi-tenant — each organization's data is isolated at the database level with row-level security."**

---

## 2. User Registration & Login (1 min)

> Navigate to: `/register`

1. Register a new account — show the form fields (name, email, password, organization)
2. **"When a user registers, an organization is automatically created and the user becomes the owner."**
3. Log in at `/login`
4. **"We use JWT authentication with short-lived access tokens (15 min) and rotating refresh tokens (7 days) for security."**

---

## 3. Document Upload (2 min)

> Navigate to: Dashboard → Upload tab

1. **Drag and drop** a PDF file into the upload zone
2. **"The upload uses presigned URLs — the file goes directly to Cloudflare R2 storage, never passing through our API server. This keeps our backend lightweight."**
3. Show the **real-time status updates** as the document processes:
   - `uploading` → `processing` → `ocr_done` → `indexed` → `ready`
4. **"Behind the scenes, a Celery pipeline kicks off: first, Mistral's OCR API extracts text page by page. Then the text is split into overlapping chunks of 500 tokens each. Finally, each chunk gets a 1024-dimensional embedding stored in pgvector."**
5. Upload a second document (image or TIFF) to show format support
6. **"We support PDF, JPEG, PNG, TIFF, and DOCX — up to 50 MB per file."**

---

## 4. Document Management (1 min)

> Navigate to: Dashboard → Documents tab

1. Show the **document list** — sortable table with filename, type, status, size, date
2. **Select multiple documents** using checkboxes
3. Show **bulk actions**:
   - **Download as ZIP** — bundles selected files
   - **Export to XLSX** — exports metadata spreadsheet (with formula injection protection)
   - **Bulk Delete** — with confirmation modal
4. Click a document to open the **preview modal** — show PDF/image rendering

---

## 5. Hybrid Search (1.5 min)

> Navigate to: Dashboard → Search tab

1. Type a natural language query, e.g., _"payment terms and conditions"_
2. **"Our search combines two approaches: semantic search using vector similarity (70% weight) and traditional full-text search using PostgreSQL tsvector (30% weight). Results are merged using Reciprocal Rank Fusion."**
3. Show results — each result shows:
   - Matched text chunk
   - Source document and page number
   - Relevance score
4. Try a second query with different wording to demonstrate **semantic understanding**
   - e.g., _"how much do we need to pay"_ should match the same content
5. **"This means users can search by meaning, not just keywords."**

---

## 6. AI Chat — RAG Q&A (2 min)

> Navigate to: Dashboard → AI Assistant tab

### Single Document Q&A

1. Select a specific document from the dropdown
2. Ask: _"What are the key points in this document?"_
3. **"The system finds the most relevant chunks using semantic search, then feeds them as context to the LLM. This is Retrieval-Augmented Generation — the AI answers based on your actual documents, not its training data."**
4. Show the **source attribution** — page numbers and excerpts

### Organization-Wide Chat

5. Switch to **All Documents** mode
6. Ask a question that spans multiple documents
7. **"Now the AI searches across every document in your organization to find answers."**

### Document Summarization

8. Click **Summarize** on a document
9. **"One-click AI summarization gives you the key takeaways without reading the full document."**

---

## 7. Document Comparison (1 min)

> Navigate to: Dashboard → Compare tab

1. Select **two documents** to compare
2. **"The system shows extracted text from both documents side by side."**
3. Show the **AI-generated comparison summary**
4. **"The AI highlights the key differences — useful for comparing contract versions, policy updates, or any document revisions."**

---

## 8. Structured Data Extraction (1.5 min)

> Navigate to: Dashboard → Extractions tab

### Create a Template

1. Create a new extraction template, e.g., "Invoice Template" with fields:
   - `invoice_number` (string)
   - `date` (string)
   - `total_amount` (string)
   - `vendor_name` (string)
2. **"Templates define what data you want to pull from documents. Once created, you can reuse them across any number of documents."**

### Run Extraction

3. Select a document and run the extraction
4. Show the **extracted fields with confidence scores**
5. **"The AI reads the document and fills in each field. Confidence scores tell you how certain the extraction is."**

### Export Results

6. Export extractions to **CSV or XLSX**
7. **"This turns unstructured documents into structured data you can use in spreadsheets, databases, or downstream systems."**

---

## 9. Security & Multi-Tenancy (30 sec)

**"A few things I want to highlight on the security side:"**

- **Row-Level Security** — PostgreSQL policies ensure no data leaks between organizations
- **Presigned URLs** — credentials never exposed to the browser
- **Account Protection** — brute-force detection with account lockout
- **Export Safety** — CSV/XLSX outputs are sanitized against formula injection
- **MFA Infrastructure** — TOTP-based two-factor authentication is wired in

---

## Closing (30 sec)

**"To recap — this system takes your documents from upload through OCR, indexing, search, AI-powered Q&A, comparison, and structured extraction. It's built on a modern async stack, scales horizontally with Celery workers, and keeps data secure with multi-tenant isolation."**

**"Questions?"**

---

## Demo Checklist

Prepare these before the demo:

- [ ] Docker containers running (`docker compose up`)
- [ ] 3–4 sample documents ready (PDF invoice, scanned image, contract, policy doc)
- [ ] API server healthy (`GET /readyz`)
- [ ] Fresh user account or clean demo org
- [ ] Browser open to `http://localhost:3000`
- [ ] Terminal open showing Celery worker logs (optional, for showing pipeline in action)
