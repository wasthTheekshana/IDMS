# Document Preview (In-App Viewer) — Design Spec

**Date:** 2026-06-21
**Phase:** 2 of 8 (Independent feature phases)
**Status:** Approved

## Summary

Add an in-app document preview modal that renders PDF, JPEG, PNG, TIFF, and DOCX files directly in the browser without downloading. Uses browser-native rendering (iframe for PDFs, img for images) via presigned R2 URLs. TIFF files are converted server-side to PNG via Pillow. DOCX files display extracted text in a styled reader view.

No new database models. All features layer on existing document infrastructure.

## Scope

### In Scope

- Preview button in document detail panel
- Full-screen modal overlay with document viewer
- PDF rendering via browser-native iframe
- JPEG/PNG rendering via img tag
- TIFF to PNG server-side conversion
- DOCX fallback to styled extracted text
- Presigned URL generation endpoint
- Close via X button and Escape key
- Loading state while fetching preview URL

### Out of Scope

- Custom PDF controls (zoom, page nav) — browser handles this
- DOCX native rendering (would require mammoth.js or similar)
- Annotation or markup on previews
- Thumbnail generation
- Caching of preview URLs

## Backend

### New Dependencies

- `Pillow>=10.0.0` — TIFF to PNG conversion

### New API Endpoint

#### `GET /api/v1/documents/{document_id}/preview-url`

**Response:**

```json
{
  "preview_url": "https://r2.example/...",
  "content_type": "application/pdf"
}
```

**Behavior:**

1. Validate document belongs to caller's org (404 if not)
2. For PDF/JPEG/PNG: generate presigned download URL via `storage.presign_download(r2_key)`, return URL + content type
3. For TIFF: return a URL pointing to the TIFF-to-PNG conversion endpoint
4. For DOCX: return `content_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document"` with `preview_url: null` — frontend falls back to extracted text

**Errors:**

- 404: document not found in org

#### `GET /api/v1/documents/{document_id}/preview-tiff`

**Behavior:**

1. Validate document belongs to caller's org
2. Fetch file bytes from R2 via `storage.get_object_bytes(r2_key)`
3. Convert TIFF to PNG using Pillow: `Image.open(BytesIO(data)).convert("RGB").save(buf, "PNG")`
4. Return as `StreamingResponse` with `image/png` content type

**Errors:**

- 404: document not found
- 500: conversion failure

### New Schema

In `api/app/schemas/document.py`:

```python
class PreviewUrlResponse(BaseModel):
    preview_url: str | None
    content_type: str
```

## Frontend

### DocumentPreviewModal (New Component)

`web/components/DocumentPreviewModal.tsx`

**Props:**

- `documentId: string`
- `filename: string`
- `mimeType: string`
- `extractedText?: string | null`
- `onClose: () => void`

**Behavior:**

1. On mount, fetch `GET /api/v1/documents/{documentId}/preview-url`
2. Show loading spinner while fetching
3. Render based on `content_type`:
   - `application/pdf` → `<iframe src={preview_url} />`
   - `image/jpeg`, `image/png` → `<img src={preview_url} />`
   - `image/tiff` → `<img src={tiff_conversion_url} />`
   - DOCX → styled extracted text in a reader layout
4. Close on X click or Escape keypress

**Layout:**

- Fixed position overlay covering entire viewport
- Semi-transparent dark backdrop (`rgba(0,0,0,0.85)`)
- White close button (X) top-right corner
- Filename displayed top-left
- Content area: full width/height minus header bar
- PDF iframe fills the content area entirely
- Images centered with `object-fit: contain`, max-width/max-height 100%
- DOCX text in a centered, max-width readable column

### DocumentList Change

In the existing detail panel section of `web/components/DocumentList.tsx`:

- Add a "Preview" button between the metadata row and extracted text section
- Button style: `btn-primary` with an eye icon
- Only show for documents with status "ready" or "indexed"
- Clicking opens `DocumentPreviewModal` with the document's info

## Data Flow

```
PREVIEW:
  User expands document → clicks "Preview" button
  → DocumentPreviewModal opens with loading spinner
  → GET /api/v1/documents/{id}/preview-url
  → Backend: validate org, generate presigned URL (15 min expiry)
  → Response: { preview_url, content_type }
  → Modal renders iframe (PDF) or img (images) or text (DOCX)

TIFF PREVIEW:
  → preview_url points to /api/v1/documents/{id}/preview-tiff
  → Backend fetches from R2, converts TIFF→PNG via Pillow
  → Streams PNG bytes as response
  → Modal renders <img> with the response

DOCX PREVIEW:
  → preview_url is null, content_type is DOCX
  → Modal renders extracted text in styled reader view
```

## Error Handling

| Scenario              | Behavior                                   |
| --------------------- | ------------------------------------------ |
| Document not found    | 404, modal shows error message             |
| Presigned URL expired | Show "Preview expired" with retry button   |
| TIFF conversion fails | Show error with fallback to extracted text |
| Network error         | Show error toast with retry                |
| Unsupported MIME type | Show extracted text as fallback            |

## Testing

### Backend

- Unit: preview-url endpoint returns presigned URL for PDF/JPEG/PNG
- Unit: preview-url returns null URL for DOCX
- Unit: preview-tiff converts and streams PNG
- Integration: org isolation — user A cannot preview user B's document

### Frontend

- Preview button appears only for ready/indexed documents
- Modal opens/closes correctly (X button, Escape key)
- PDF renders in iframe
- Image renders in img tag
- DOCX shows extracted text
- Loading state displays during fetch
