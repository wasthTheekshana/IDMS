# Bulk Upload + Bulk Actions + Excel Export — Design Spec

**Date:** 2026-06-20
**Phase:** 1 of 8 (Independent feature phases)
**Status:** Approved

## Summary

Add bulk upload (multiple files with parallel progress), bulk actions (delete, download ZIP, export Excel) with selection UI, and Excel export (metadata + extracted text) to the existing IDMS.

No new database models. All features layer on existing document infrastructure.

## Scope

### In Scope

- Multi-file upload with per-file progress (max 3 concurrent)
- Document selection model (checkboxes, select all, shift+click range)
- Bulk delete with confirmation modal (transactional)
- Bulk download as ZIP (max 20 files / 500MB)
- Excel export with metadata + extracted text (openpyxl)
- Error handling for partial failures and limits

### Out of Scope

- Drag-to-reorder documents
- Move to folder (deferred to Smart Folders phase)
- Chunk/embedding export (not requested)
- Background job for very large exports (keep synchronous for now)

## Backend

### New Dependencies

- `openpyxl` — Excel file generation
- Python stdlib `zipfile` + `io` — ZIP streaming

### New API Endpoints

All endpoints in `api/app/api/v1/documents.py`. All require JWT auth and enforce org-scoping via existing RLS.

#### `POST /api/v1/documents/bulk/delete`

**Request:**

```json
{ "document_ids": ["uuid1", "uuid2", ...] }
```

**Behavior:**

1. Validate all IDs belong to the caller's org (404 if any don't)
2. In a single transaction:
   - Delete `DocumentChunk` rows for all documents
   - Delete R2 objects via boto3 `delete_objects` (batch)
   - Delete `Document` rows
3. Return `{ "deleted": 3 }`

**Errors:**

- 400: empty list or > 50 IDs
- 404: any document not found in org

#### `POST /api/v1/documents/bulk/download`

**Request:**

```json
{ "document_ids": ["uuid1", "uuid2", ...] }
```

**Behavior:**

1. Validate all IDs belong to org
2. Check total size ≤ 500MB, count ≤ 20
3. Fetch each file from R2 using existing presigned URL or direct get
4. Stream a ZIP file as `StreamingResponse` with `Content-Disposition: attachment; filename="documents-{timestamp}.zip"`

**Errors:**

- 400: empty list or > 20 files
- 413: total size exceeds 500MB

#### `POST /api/v1/documents/bulk/export`

**Request:**

```json
{ "document_ids": ["uuid1", "uuid2", ...] }
```

**Behavior:**

1. Validate all IDs belong to org
2. Query documents with fields: filename, mime_type, size_bytes, page_count, status, created_at, extracted_text
3. Build `.xlsx` with openpyxl:
   - Sheet name: "Documents"
   - Columns: Filename | Type | Size (KB) | Pages | Status | Uploaded At | Extracted Text
   - Auto-width columns, header row bold
   - Extracted text truncated to 32,000 chars per cell (Excel limit)
4. Stream as `StreamingResponse` with `Content-Disposition: attachment; filename="documents-export-{timestamp}.xlsx"`

**Errors:**

- 400: empty list or > 100 IDs
- 404: any document not found in org

### New Schemas

In `api/app/schemas/document.py`:

```python
class BulkDocumentRequest(BaseModel):
    document_ids: list[UUID]

class BulkDeleteResponse(BaseModel):
    deleted: int

class BulkDownloadMeta(BaseModel):
    total_files: int
    total_size_bytes: int
```

## Frontend

### UploadZone Changes

Extend existing `web/components/UploadZone.tsx`:

- Accept `multiple` attribute on file input and drop handler
- Track array of upload items, each with: `id, file, status, progress, error`
- Status enum: `pending | requesting | uploading | processing | done | error`
- Concurrency limiter: process max 3 uploads simultaneously from the queue
- UI per file: filename, progress bar, status icon (spinner/check/x), cancel button
- Summary bar at top: "3 of 7 uploaded" with overall progress
- "Cancel all" button clears pending queue (in-flight uploads complete)
- Each upload uses existing flow: `POST /upload/init` → `PUT` to R2 presigned URL → `POST /upload/confirm`

### DocumentList Changes

Extend existing `web/components/DocumentList.tsx`:

- Add checkbox column (leftmost)
- Header checkbox: select all / deselect all (tri-state: none, some, all)
- Shift+click: select range between last-clicked and current
- Selection state: `Set<string>` of document IDs
- When ≥1 selected, show floating action toolbar:
  - Toolbar fixed at bottom of document list area
  - Contains: selection count badge, Delete button (red), Download ZIP button, Export Excel button
  - Buttons show loading spinners during operations

### ConfirmDeleteModal (New Component)

`web/components/ConfirmDeleteModal.tsx`:

- Receives: list of document names + onConfirm + onCancel
- Shows: "Delete {n} documents?" header
- Lists up to 10 document names; if more, shows "+{n} more"
- Red "Delete permanently" button (disabled during loading)
- "Cancel" button
- Loading state with spinner on confirm button
- Closes on successful deletion, shows error toast on failure

### API Client

Add to existing fetch wrapper:

```typescript
bulkDelete(ids: string[]): Promise<{ deleted: number }>
bulkDownload(ids: string[]): Promise<Blob>  // triggers browser download
bulkExport(ids: string[]): Promise<Blob>    // triggers browser download
```

For download/export: use `fetch` with blob response, create object URL, trigger `<a>` click download.

### State Management

Selection state lives in `DocumentList` component:

- `selectedIds: Set<string>` — currently selected document IDs
- `lastClickedId: string | null` — for shift+click range selection
- Clear selection after successful bulk action
- Clear selection when switching tabs

## Data Flow

```
BULK UPLOAD:
  User drops N files
  → UploadZone queues N items (status: pending)
  → Concurrency limiter picks 3 → each: init → R2 PUT → confirm
  → As each completes, next pending starts
  → Each confirmed doc enters OCR → Embed pipeline via Celery
  → SSE updates status per document in DocumentList

BULK DELETE:
  User selects docs → clicks Delete → ConfirmDeleteModal opens
  → User clicks "Delete permanently"
  → POST /bulk/delete { document_ids }
  → Backend transaction: delete chunks + R2 objects + records
  → 200 → Frontend removes from list + clears selection + success toast

BULK DOWNLOAD:
  User selects docs → clicks Download ZIP
  → POST /bulk/download { document_ids }
  → Backend streams ZIP → browser auto-downloads
  → Button returns to normal state

EXCEL EXPORT:
  User selects docs → clicks Export Excel
  → POST /bulk/export { document_ids }
  → Backend builds xlsx with openpyxl → streams response
  → Browser auto-downloads .xlsx
```

## Error Handling

| Scenario                         | Behavior                                                                 |
| -------------------------------- | ------------------------------------------------------------------------ |
| Single file upload fails         | Mark file as `error` with message, continue others                       |
| All uploads fail                 | Show error state, allow retry                                            |
| Bulk delete partial failure      | Transaction rolls back entirely, return 500                              |
| R2 object delete fails           | Log error, continue with DB deletion (orphaned R2 objects cleaned later) |
| Download exceeds size limit      | Return 413 before starting ZIP                                           |
| Export with invalid IDs          | Return 404 for any missing doc                                           |
| Network error during bulk action | Show error toast, selection preserved for retry                          |
| Excel cell content too long      | Truncate extracted text to 32,000 chars                                  |

## Testing

### Backend

- Unit: bulk delete, download, export endpoints with mocked R2
- Integration: full flow with test documents in DB
- Edge cases: empty list, single item, max limits, cross-org rejection
- Security: verify org isolation (user A cannot bulk-delete user B's docs)

### Frontend

- Upload: multi-file drop, concurrency limit, cancel, error recovery
- Selection: checkbox, select all, shift+click range, clear on action
- Actions: delete modal flow, download trigger, export trigger
- Loading states and error toasts

## Limits

| Limit                   | Value            | Reason                           |
| ----------------------- | ---------------- | -------------------------------- |
| Max concurrent uploads  | 3                | Avoid browser connection limit   |
| Max bulk delete         | 50 docs          | Prevent accidental mass deletion |
| Max bulk download       | 20 files / 500MB | Memory and timeout constraints   |
| Max bulk export         | 100 docs         | Excel file size management       |
| Extracted text per cell | 32,000 chars     | Excel cell limit                 |
