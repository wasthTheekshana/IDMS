# Document Comparison (Side-by-Side Diff) — Design Spec

**Date:** 2026-06-21
**Phase:** 3 of 8 (Independent feature phases)
**Status:** Approved

## Summary

Add a document comparison feature that lets users select exactly two documents and view their extracted text side-by-side with inline diff highlighting. Uses the `diff-match-patch` library for client-side diffing — no backend changes required. Integrates into the existing bulk action toolbar in the document list.

No new database models. No new API endpoints. All features layer on existing document infrastructure.

## Scope

### In Scope

- Compare button in bulk action toolbar (visible when exactly 2 documents selected)
- Full-screen comparison modal with side-by-side panels
- Inline diff highlighting (green for additions, red for deletions)
- Fetch both documents' extracted text via existing `GET /api/v1/documents/{id}` endpoint
- Close via X button and Escape key
- Loading state while fetching documents
- Synchronized scrolling between panels

### Out of Scope

- Visual/layout comparison of rendered documents (PDF pages, images)
- Three-way merge or conflict resolution
- Saving or exporting comparison results
- Comparing more than two documents at once
- Backend diff computation

## Dependencies

### New NPM Package

- `diff-match-patch` — Google's diff algorithm library (~50KB). Well-maintained, widely used, handles character-level and word-level diffs efficiently.
- `@types/diff-match-patch` — TypeScript type definitions (dev dependency).

## Frontend

### DocumentCompareModal (New Component)

`web/components/DocumentCompareModal.tsx`

**Props:**

- `documentIds: [string, string]` — exactly two document IDs
- `onClose: () => void`

**Behavior:**

1. On mount, fetch both documents in parallel via `GET /api/v1/documents/{docId}` with auth header
2. Show loading spinner while fetching
3. Compute diff using `diff-match-patch`:
   - Create `diff_match_patch` instance
   - Call `diff_main(textA, textB)` to get diff array
   - Call `diff_cleanupSemantic(diffs)` for human-readable output
4. Render two side-by-side panels, each showing the document's text with diff highlighting:
   - Left panel (Document A): shows deletions highlighted red, unchanged text normal
   - Right panel (Document B): shows additions highlighted green, unchanged text normal
5. Synchronized scrolling: scrolling one panel scrolls the other
6. Close on X click or Escape keypress

**Layout:**

- Fixed position overlay covering entire viewport
- Semi-transparent dark backdrop (`rgba(0,0,0,0.85)`)
- Header bar with both filenames (left: "Document A name", right: "Document B name"), close button (X) top-right
- Content area: two equal-width panels separated by a subtle divider
- Each panel: white background, scrollable, monospace-ish text at readable size
- Diff highlighting colors:
  - Deletions (left panel): `background: rgba(239, 68, 68, 0.15)` with `color: var(--red-700)`
  - Additions (right panel): `background: rgba(34, 197, 94, 0.15)` with `color: var(--green-700)`
  - Unchanged: normal text color

**Error handling:**

- If either document fails to load: show error message with the failing document name
- If neither document has extracted text: show "No extracted text available for comparison"
- If only one document has extracted text: show that document's text normally, the other panel shows "No extracted text"

### DocumentList Change

In the existing bulk action toolbar in `web/components/DocumentList.tsx`:

- Add a "Compare" button between the existing Delete and Download buttons
- Only visible when exactly 2 documents are selected (`selectedIds.size === 2`)
- Button style: `btn-secondary` with a compare/diff icon (two overlapping documents)
- Clicking opens `DocumentCompareModal` with the two selected document IDs
- Add state: `const [showCompare, setShowCompare] = useState(false)`

## Data Flow

```
COMPARE:
  User checks exactly 2 documents in document list
  → "Compare" button appears in bulk toolbar
  → User clicks "Compare"
  → DocumentCompareModal opens with loading spinner
  → Parallel fetch: GET /api/v1/documents/{idA} + GET /api/v1/documents/{idB}
  → Both responses contain extracted_text
  → Client-side diff: diff_match_patch.diff_main(textA, textB)
  → diff_cleanupSemantic(diffs) for readable output
  → Render side-by-side panels with highlighted diffs
```

## Error Handling

| Scenario                       | Behavior                                            |
| ------------------------------ | --------------------------------------------------- |
| Document not found             | Show error in the failing panel                     |
| No extracted text (both)       | Show "No extracted text available" message          |
| No extracted text (one)        | Show available text, other panel shows placeholder  |
| Network error                  | Show error with retry button                        |
| Very large texts (>100KB each) | Diff may be slow — show "Computing diff..." message |

## Testing

### Frontend

- Compare button appears only when exactly 2 documents selected
- Compare button hidden when 0, 1, or 3+ documents selected
- Modal opens/closes correctly (X button, Escape key)
- Diff highlighting renders correctly for additions/deletions
- Loading state displays during fetch
- Error states display correctly
- Synchronized scrolling works between panels
