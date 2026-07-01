# IDMS — Commercial Launch Strategy & Product Roadmap

## Project Overview

**IDMS (Intelligent Document Management System)** is an enterprise-grade document management platform that combines OCR, semantic search, and AI to help organizations upload, understand, and extract structured data from documents. It is a multi-tenant SaaS system with row-level security and production-ready infrastructure — the technology powering the **auraDOCS** product offered by DOK Solutions Lanka.

---

## Current Product Strengths

| Feature | Status |
|---|---|
| Multi-tenant SaaS architecture | ✅ Done |
| Hybrid semantic + full-text search | ✅ Done |
| AI-powered Q&A (RAG) | ✅ Done |
| OCR pipeline (Mistral) | ✅ Done |
| Document comparison | ✅ Done |
| Structured data extraction with confidence scores | ✅ Done |
| Bulk operations (ZIP download, Excel/CSV export) | ✅ Done |
| JWT auth with MFA infrastructure | ✅ Done |
| Brute-force detection + account lockout | ✅ Done |
| Celery async task queue | ✅ Done |
| Docker containerization | ✅ Done |

---

## The Core Competitive Question

### "Why use IDMS when we already have ChatGPT / Gemini / Claude?"

General-purpose AI tools are powerful but have critical weaknesses for enterprise document management:

| Problem with General AI | IDMS Solution |
|---|---|
| Your confidential documents leave your company and go to US servers | Documents stay in YOUR controlled infrastructure |
| No access control — anyone can ask anything | Role-based access — employees only see what they're authorized to see |
| No memory of your organization's specific documents | Persistent organizational memory across all uploaded documents |
| Can't reliably extract structured data | Extraction templates with AI confidence scores |
| Can't compare two contracts side-by-side | Built-in document comparison with diff view |
| No audit trail — who asked what, when? | Full compliance logging for regulatory requirements |
| General answers, not grounded in your actual policies | RAG answers grounded exclusively in YOUR documents |
| Can't process scanned paper or handwritten documents | OCR pipeline for physical document digitization |
| No organizational workflow support | Approval flows, notifications, deadline tracking (roadmap) |

### The One-Sentence Commercial Pitch

> **"ChatGPT doesn't know your company's documents, can't control who sees what, leaves no audit trail, and sends your confidential files to American servers — IDMS does all of this, runs in your infrastructure, and speaks your language."**

---

## What Needs to Improve (Existing Features)

### 1. UI/UX — Critical Gap
The current frontend uses vanilla CSS which is functionally sound but visually weak for commercial launch. The DOK Solutions marketing website uses Tailwind + Framer Motion and looks premium — the product UI must match this quality.

- Build a proper component design system (consistent typography, colors, spacing)
- Full mobile responsiveness across all pages
- WCAG 2.1 accessibility compliance (required for enterprise and government clients)
- Dark mode support (standard expectation in 2025)
- Loading skeletons instead of spinners for perceived performance

### 2. Search Quality
- Add **query rewriting** — AI rephrases the user's question before searching to improve recall
- Add **search result highlighting** — show exactly which sentence in the document matched
- Add **search filters** — filter by date range, document type, department, uploader
- Add **search history** per user

### 3. AI Answer Quality
- Add **source citations with page numbers** — not just document name, but exact location
- Add **answer confidence indicator** visible to users
- Add **"I don't know" detection** — when no relevant documents exist, say so clearly instead of hallucinating
- Add **multi-turn conversation memory** — chat about a document set across multiple messages
- Add **response streaming** — users see text appear live, not wait 8-10 seconds for a complete answer

### 4. OCR Accuracy & Coverage
- Add **manual correction UI** — let users fix OCR errors on a per-document basis
- Add **OCR quality score** per document so users know which need review
- Add support for **Arabic, Sinhala, and Tamil** text (essential for Sri Lanka and Middle East markets)

### 5. Performance & Cost
- Add **semantic cache** — same or similar AI questions return cached responses (reduces API costs significantly)
- Add **CDN** for document delivery
- Add **query result pagination** with cursor-based pagination for large document sets

---

## New Features Needed for Commercial Launch

### Phase 1 — Foundation (Must Have, 0–3 Months)

#### Billing & Subscription System
- Stripe or Paddle integration for monthly and annual plans
- Usage metering: pages OCR'd, AI queries made, storage used (GB)
- **Free trial (14 days, no credit card required)** — non-negotiable for SaaS adoption
- Customer usage dashboard showing current consumption vs. plan limits
- Automatic upgrade prompts when limits are approached

#### Proper Onboarding Flow
- Step-by-step organization setup wizard
- Sample documents pre-loaded to let new users experience the product in under 2 minutes
- Embedded video walkthrough
- In-app tooltips and guided feature tours (Shepherd.js or Intercom)
- Welcome email sequence

#### Document Versioning
- Every document update preserves the previous version
- Version history timeline per document
- Version comparison — what text changed between v1 and v2 of a contract?
- Ability to restore any previous version

#### Audit Log & Compliance Dashboard
- Every action logged: upload, search, view, download, delete, export, login
- Exportable audit reports in PDF and CSV for external compliance audits
- Configurable data retention policies — auto-archive or delete after X days
- GDPR-ready data deletion requests
- **This feature alone sells IDMS to banks, law firms, hospitals, and government agencies**

#### Granular Role & Permission System
Current architecture is org-level only. Commercial launch requires:
- Viewer / Editor / Admin / Owner roles
- Department-level folders with separate permission sets
- Document-level sharing (share one specific document with one specific person)
- Guest access — share with external parties (auditors, clients) without giving them a full account
- Permission inheritance and override rules

### Phase 2 — Enterprise Ready (3–6 Months)

#### Workflow Automation
- Document approval flows: Upload → Review → Approve → Archive
- Email and in-app notifications at each workflow step
- Deadline tracking on time-sensitive documents (contracts, compliance filings)
- Rejection with reviewer comments and re-submission cycle
- Parallel and sequential approval chains

#### Integrations
Integrations are the #1 reason enterprise clients adopt or reject SaaS products:
- Microsoft 365 / SharePoint two-way connector
- Google Drive / Google Workspace sync
- Email inbox integration — forward an email with attachments and they auto-upload to IDMS
- Slack and Microsoft Teams notifications for document events
- Zapier / Make (Integromat) webhook support for custom automations

#### Public API & Developer Access
- API key management per organization
- Published REST API documentation (FastAPI already generates Swagger — expose it publicly)
- Rate limiting and quota enforcement per API key
- Webhooks for real-time event notifications to third-party systems
- Python and JavaScript SDKs
- This enables enterprise clients to embed IDMS into their own internal systems

#### E-Signature Integration
- DocuSign or Adobe Sign API integration
- Or build lightweight in-house signing for basic use cases
- Critical for contract management, HR onboarding, and procurement workflows

#### Advanced Analytics Dashboard
- Documents processed per month, per department
- Most searched topics across the organization
- Documents with approaching expiry dates (contracts, licenses, certificates)
- AI usage and cost breakdown
- Department-level usage reports for managers and executives

#### Batch Processing & Mass Import
- Upload an entire folder of 500+ documents in one operation
- Import from Google Drive, SharePoint, or Dropbox
- Scheduled ingestion — auto-pull documents from a shared folder every night
- Progress tracking for large imports with error reporting

### Phase 3 — Differentiation & Maximum Competitive Level (6–12 Months)

#### Smart Document Auto-Classification
- AI automatically categorizes uploaded documents: invoice, contract, policy, receipt, ID card, certificate
- Auto-tags documents with relevant extracted keywords
- Suggests the correct extraction template based on detected document type
- Eliminates manual categorization for high-volume document ingestion

#### Contract Intelligence Module
- Extract key contract terms automatically: start date, end date, renewal clause, payment terms, governing law, parties
- Proactive contract expiry alerts — "This contract expires in 30 days"
- Risk clause flagging — AI highlights unusual or potentially risky clauses
- Obligation tracking — track deliverables and deadlines within contracts
- Contract portfolio dashboard for legal and procurement teams
- **This is a standalone product category with massive market demand and high willingness to pay**

#### Anomaly Detection & Security Intelligence
- "This invoice is 300% higher than your organization's average — flag for review"
- Duplicate document detection — alert when the same document is uploaded twice under different names
- Suspicious access pattern detection — an employee downloading 500 documents in one session
- Unusual after-hours access alerts

#### Multi-Language Support (Strategic Competitive Moat)
- Full Sinhala and Tamil UI localization
- OCR trained for Sinhala and Tamil script documents
- AI Q&A responses in Sinhala and Tamil
- Arabic language support for Middle East market expansion
- **No international competitor has this — it is a genuine and defensible moat in the South Asian market**

#### On-Premise / Private Cloud Deployment
- Banks, government ministries, hospitals, and defense organizations will not use cloud-hosted SaaS
- Package IDMS as a self-contained Docker Compose or Kubernetes Helm chart
- Customer runs it entirely on their own servers — IDMS never touches their data
- Premium licensing tier with support SLA
- **This unlocks the highest-revenue customer segment — regulated industries**

#### Mobile Application
- React Native app for iOS and Android
- Scan physical documents with phone camera → auto-uploaded, OCR processed, and indexed
- Approve or reject document workflows from mobile
- Search and read documents on the go
- Offline mode for viewing recently accessed documents
- **Completes the paper-to-digital story end-to-end**

#### Intelligent Document Summarization Upgrades
- Executive summary mode — one paragraph for non-technical decision makers
- Section-by-section structured summaries for long documents
- Comparative summaries — summarize the differences across 5 similar contracts at once
- Meeting minutes extraction from uploaded transcripts or audio files

---

## Target Market Segments (Priority Order)

| Segment | Use Case | Revenue Potential |
|---|---|---|
| Law Firms | Contract review, case file management, discovery | Very High |
| Banks & Financial Institutions | KYC documents, loan files, compliance records | Very High |
| Insurance Companies | Claims processing, policy management | Very High |
| Government & Public Sector | Records management, citizen document processing | High |
| Healthcare / Hospitals | Patient records, compliance documents | High |
| Accounting & Audit Firms | Financial document review, client files | High |
| HR Departments | Employee records, onboarding documents | Medium |
| SMEs with high document volume | General document management | Medium |

---

## Technology Stack Summary (Current)

| Layer | Technology |
|---|---|
| Frontend | Next.js 14.2, React 18, TypeScript |
| Backend API | FastAPI (Python 3.12, async) |
| Database | PostgreSQL 16 + pgvector (1024-dim embeddings) |
| File Storage | Cloudflare R2 (S3-compatible) |
| Cache & Queue | Redis 7 + Celery 5.4 |
| OCR | Mistral API |
| Embeddings | mistral-embed (1024 dimensions) |
| Primary LLM | Google Gemini 2.0 Flash |
| Fallback LLM | Groq LLaMA 3.3 70B |
| Search | pgvector (semantic, 70%) + PostgreSQL tsvector (full-text, 30%) with RRF |
| Containerization | Docker + docker-compose (6 services) |
| Security | JWT (15-min access + 7-day refresh), MFA (TOTP), brute-force lockout |

---

## Phased Launch Checklist

```
PHASE 1 — Foundation (0–3 Months)
  ✅ Core document management (upload, preview, manage)
  ✅ OCR pipeline
  ✅ Hybrid search
  ✅ AI Q&A (RAG)
  ✅ Document comparison
  ✅ Structured extraction templates
  ✅ Multi-tenancy + JWT auth
  ✅ Docker containerization
  🔲 Billing system (Stripe/Paddle)
  🔲 Free trial onboarding flow
  🔲 In-app guided tour
  🔲 Response streaming for AI answers
  🔲 Proper design system (match DOK website quality)
  🔲 Full mobile responsive UI
  🔲 WCAG accessibility compliance

PHASE 2 — Enterprise Ready (3–6 Months)
  🔲 Audit log + compliance dashboard
  🔲 Document versioning
  🔲 Granular roles & permissions (Viewer/Editor/Admin/Guest)
  🔲 Document approval workflow
  🔲 Email and in-app notifications
  🔲 Public API + developer documentation
  🔲 Webhook support
  🔲 Microsoft 365 / Google Drive integration
  🔲 E-signature integration
  🔲 Sinhala + Tamil + Arabic language support
  🔲 Search result highlighting + filters

PHASE 3 — Differentiation (6–12 Months)
  🔲 Smart document auto-classification
  🔲 Contract intelligence (expiry alerts, risk flags, obligation tracking)
  🔲 Anomaly detection & security alerts
  🔲 On-premise / private cloud deployment package
  🔲 Mobile app (iOS + Android)
  🔲 Batch import from Google Drive / SharePoint / Dropbox
  🔲 Semantic answer caching
  🔲 Advanced analytics dashboard
```

---

## Key Decisions Before Launch

1. **Pricing model** — Per user per month? Per document processed? Per GB stored? Hybrid?
2. **Data residency** — Will you offer Sri Lanka / Asia-Pacific hosted option for regulated clients?
3. **Support tier** — Email only? Live chat? Dedicated account manager for enterprise?
4. **White-labeling** — Will you allow partners (e.g., other BPO companies in the Abans Group ecosystem) to resell IDMS under their own brand?
5. **Compliance certifications** — Pursue ISO 27001 for IDMS specifically (DOK Solutions already holds it for the business — aligning the product is a strong sales enabler)

---

*Document created: July 2026 | Product: IDMS / auraDOCS | Company: DOK Solutions Lanka*
