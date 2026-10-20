# Documents (Unterlagen) and the application dossier

## Goal

The son keeps his application documents in one place in the app: school reports, external
certificates and tests (e.g. Multicheck, Stellwerk), CV, cover letter. From them the app builds one
PDF in a fixed order, the application dossier (Bewerbungsdossier) that many companies ask for.

Success:

- uploading a document (also a photo taken with the phone) takes one form
- documents are grouped by category, newest first; outdated ones stay but are folded away
- one button gives a dossier PDF in the usual order, small enough to send by e-mail
- the files are on the NAS with readable names, covered by the backup and the export

Out of scope: linking documents to applications (the application mail with the app in BCC already
brings its attachments into the timeline), per-user visibility (everyone sees everything), converting
Word or other office files, storing generated dossiers.

## Data

New table `documents` (created by `create_all`; no change to existing tables):

| Column | Type | Notes |
|---|---|---|
| `id` | integer PK | |
| `category` | string(20) | `letter`, `cv`, `report`, `certificate`, `other` |
| `title` | string(200), required | |
| `issued_on` | date, nullable | date on the document |
| `note` | text, default "" | |
| `outdated` | bool, default false | |
| `in_dossier` | bool, default true | |
| `position` | integer | order inside its category, ascending |
| `filename` | string(300) | original upload name, for downloads |
| `path` | string(500) | relative to `config.files_dir()` |
| `content_type` | string(200) | |
| `size` | integer | bytes |
| `created_by` | FK users, nullable, `ON DELETE SET NULL` | |
| `created_at` | datetime (UTC) | |

Category labels (German UI) and dossier order:

| Order | Key | Label | Folder |
|---|---|---|---|
| 1 | `letter` | Motivationsschreiben | `motivationsschreiben` |
| 2 | `cv` | Lebenslauf | `lebenslauf` |
| 3 | `report` | Zeugnis | `zeugnis` |
| 4 | `certificate` | Zertifikat/Test | `zertifikat` |
| 5 | `other` | Andere | `andere` |

**Order inside a category:** `position` ascending. A new upload gets `position = (lowest position
in its category) - 1`, so it comes first ("newest first" by default). Moving up/down swaps
`position` with the neighbour in the same category. A document whose category changes gets the
lowest position of the new category minus 1.

**Marking outdated** also sets `in_dossier = false`; marking it current again does not change
`in_dossier` (the user decides).

## Files

`files/_unterlagen/<folder>/<YYYY-MM-DD>_<folder>_<title-slug>.<ext>`, with the date `issued_on`
(or the upload date) and the extension of the uploaded file, e.g.
`_unterlagen/zeugnis/2026-07-01_zeugnis_Zeugnis-2-Sek-1-Semester.pdf`. Existing names get `_2`,
`_3`, … like other files. Built with the existing helpers in `files.py` (`slugify`, `_unique`,
`_move`). At most 25 MB per file (`MAX_UPLOAD_BYTES`). Allowed are PDF, Word-type files (`doc`, `docx`,
`odt`, `rtf`) and photos (`jpg`, `jpeg`, `png`, `webp`, `heic`, `heif`), by extension; anything else
(HTML, SVG, scripts, no extension) gets 422. The stored content type comes from the extension, not
from the browser. Word-type files start with `in_dossier = false`. A failed database commit deletes
a newly written file, or moves a moved file back.

A category change moves the file into the new folder (`_move`); a title or date change does not
rename it. Deleting a document deletes its file.

## API

All endpoints need a login.

- `GET /api/documents` → all documents, ordered by category order, then `position`; each with
  `id, category, title, issued_on, note, outdated, in_dossier, position, filename, content_type,
  size, created_at, created_by_name, dossier_ok` (`dossier_ok`: PDF or a supported image type, see
  below).
- `POST /api/documents` (multipart: `file`, `category`, `title` optional, `issued_on` optional,
  `note` optional) → 201. Without a title, the file name without extension. 413 over 25 MB, 422 for
  an unknown category or an empty file.
- `PATCH /api/documents/{id}` (JSON: `category`, `title`, `issued_on` (null clears), `note`,
  `outdated`, `in_dossier`) → the document.
- `POST /api/documents/{id}/move` (`direction`: `up` or `down`) → the documents of that category in
  their new order. At the top or bottom: no change.
- `DELETE /api/documents/{id}` → 204.
- `GET /api/documents/{id}/file` → the file, with its content type and original file name;
  `inline` for PDFs and images (they open in the browser), `attachment` for everything else.
- `GET /api/documents/dossier` → preview: `{parts: [{id, title, category, pages}], skipped:
  [{id, title, reason}], pages, size}`.
- `GET /api/documents/dossier.pdf` → the PDF as `Bewerbungsdossier_<YYYY-MM-DD>.pdf`; 404 if no
  document can go into it.

## Dossier

Built in memory on each request, never stored. Inputs: documents with `in_dossier = true`, in the
order above.

- **PDF:** appended unchanged (pypdf). An encrypted PDF is tried with an empty password (many are
  only protected against editing); if it still can't be read it is skipped with the reason
  "passwortgeschützt". A PDF pypdf can't read is skipped with "PDF nicht lesbar".
- **Images** (`image/jpeg`, `image/png`, `image/webp`, `image/heic`, `image/heif`, also recognised by
  extension): orientation from EXIF applied, converted to RGB, scaled to fit an A4 page at 150 dpi
  (1240 × 1754 px, never enlarged), centred on a white A4 page, JPEG quality 80, one page per image
  (Pillow; pillow-heif for HEIC).
- **Anything else** (Word, text, …): skipped with "kein PDF oder Bild – bitte als PDF hochladen".
- **Missing file** on the NAS: skipped with "Datei fehlt".

`dossier_ok` in the list uses the same type check, so the page can mark such documents before the
dossier is built.

New dependencies: `pypdf`, `Pillow`, `pillow-heif` (pinned versions in `backend/requirements.txt`).

## Frontend

- Navigation: tab **Unterlagen** (`/unterlagen`) after Posteingang, no badge.
- **Upload form** at the top: file (`accept` PDFs and images; on phones the camera is offered), category
  (select), title (filled from the file name when empty), date, note, **Hochladen**.
- **Dossier card:** button **Dossier als PDF** and the preview (order, pages, approximate size,
  skipped documents with their reason), loaded when the page opens and after every change.
- **List** per category in dossier order, each with its count: rows with title, date, size, who
  uploaded it, a checkbox **Im Dossier**, buttons ↑/↓, **Öffnen**, **Herunterladen**,
  **Bearbeiten**, **Veraltet** / **Aktuell**, **Löschen** (confirm). Documents that can't go into the
  dossier show "nicht im Dossier möglich (bitte als PDF hochladen)". Outdated documents of a
  category are folded under "Veraltet (n)".
- Files are fetched with the login token (like attachments): "Öffnen" opens a temporary blob URL
  in a new tab, "Herunterladen" saves it.

## Export

- `unterlagen.csv` (readable, semicolon, BOM): Kategorie, Titel, Datum, Datei, Grösse (KB), Im Dossier,
  Veraltet, Hochgeladen von, Hochgeladen am, Pfad.
- `documents.csv`: the raw table.
- The files are in `files/_unterlagen/…` of the export already.

## Testing

Backend (pytest):

- upload: stored path and name, title from the file name, 413 over the limit, 422 for an unknown
  category and an empty file, position (new one first)
- list order (category order, then position)
- patch: fields, clearing the date, category change moves the file, outdated clears `in_dossier`
- move up/down, at the edges
- delete removes the file; download returns the content and name; login required
- dossier: order across and inside categories; a PDF and an image (PNG, a large JPEG is scaled down,
  a rotated EXIF image is upright) give the expected page count and A4 page size; skipped: Word file,
  encrypted PDF, broken PDF, missing file; 404 when nothing fits; preview numbers match the PDF
- export: `unterlagen.csv` and `documents.csv`

Frontend: `npm run lint` and `npm run build`.
