# Suggestions (Vorschläge) for open apprenticeships

## Goal

Anyone in the family can post a link to an open apprenticeship (Lehrstelle) as a suggestion. The
son sees the open suggestions and decides: apply (the suggestion becomes an application) or not
interested. No idea gets lost in a chat, and turning a suggestion into an application takes one
click.

Success:

- a link can be posted from the app (with the page title filled in) or by e-mail
- open suggestions are visible at a glance, with a count in the navigation
- "Bewerben" creates an application with company, position, location, link and note
- the daily reminder mentions new suggestions and those whose deadline is near

Out of scope: per-user visibility (everyone sees everything, as for applications), importing from
job portals, fetching pages for suggestions that arrive by e-mail.

## Data

New table `suggestions` (created by `create_all`; no change to existing tables):

| Column | Type | Notes |
|---|---|---|
| `id` | integer PK | |
| `url` | string(1000), required | as entered |
| `url_key` | string(1000), indexed | normalised URL for duplicate checks (see below) |
| `company` | string(200), default "" | |
| `position` | string(200), default "" | |
| `location` | string(200), default "" | |
| `deadline` | date, nullable | application deadline (Bewerbungsfrist) |
| `note` | text, default "" | |
| `status` | string(20) | `open`, `applied`, `declined` |
| `decline_reason` | text, default "" | |
| `application_id` | FK applications, nullable, `ON DELETE SET NULL` | set when applied |
| `source` | string(10) | `app` or `mail` |
| `created_by` | FK users, nullable, `ON DELETE SET NULL` | |
| `created_at` | datetime (UTC) | |
| `decided_by` | FK users, nullable, `ON DELETE SET NULL` | |
| `decided_at` | datetime (UTC), nullable | |

**URL normalisation** (`url_key`): lower-case scheme and host, drop a leading `www.`, drop the
fragment, drop query parameters starting with `utm_` and `fbclid`/`gclid`, sort the remaining query
parameters, drop a trailing `/` of the path. Duplicates are checked against `url_key` of other
suggestions and against the normalised `posting_url` of applications.

## API

All endpoints need a login.

- `GET /api/suggestions` → all suggestions, newest first, each with `created_by_name`,
  `decided_by_name`, `application` (`{id, company, position}` or null) and `deadline_passed`.
- `POST /api/suggestions` (`url`, `company`, `position`, `location`, `deadline`, `note`) → 201.
  `url` must be `http(s)`; otherwise 422. Duplicates are allowed (the form warns first).
- `PATCH /api/suggestions/{id}` → edit the fields of `POST`.
- `DELETE /api/suggestions/{id}` → 204.
- `POST /api/suggestions/{id}/apply` (`company`, `position`, `location`, all optional overrides) →
  201 `{application_id}`. Creates the application (`company`, `position`, `location`,
  `posting_url` = `url`, `notes` = `note`, a new mail tag), sets the suggestion to `applied`. 409
  if it is not `open`; 422 if the resulting company is empty.
- `POST /api/suggestions/{id}/decline` (`reason`, optional) → `declined`. 409 if not `open`.
- `POST /api/suggestions/{id}/reopen` → back to `open`, clears decision fields and
  `application_id` (the application stays). 409 if `open`.
- `POST /api/suggestions/check` (`url`) → `{duplicates: [...], title: str | null}`: earlier
  suggestions and applications with the same `url_key` (id, kind, label, date), and the page title.
- `GET /api/dashboard` gains `suggestion_count` (open suggestions) for the navigation badge.

## Page title (`check`)

The backend fetches the URL to suggest a position:

- only `http` and `https`, ports 80 and 443
- before connecting, resolve the host; refuse if any address is private, loopback, link-local,
  multicast, reserved or unspecified (IPv4 and IPv6). The connection goes to the checked address.
- at most 3 redirects, each target checked the same way
- 5 s timeout, at most 1 MB read, only `text/html`
- title: `og:title`, else `<title>`, whitespace collapsed, at most 200 characters, HTML entities
  decoded
- any failure gives `title: null`; the duplicate check still answers

Standard library only (`urllib`, `http.client`, `ipaddress`, `html.parser`); no new dependency.

## By e-mail

Address: `bewerbungen+vorschlag@<domain>`. The existing worker and Email Routing rule already
deliver it; `vorschlag` can never be an application's tag (tags use an alphabet without `o`).

In `inbound.process`, before the tag lookup: if a recipient's tag is `vorschlag`

- and the sender is a user's address: every `http(s)` URL in the text body becomes a suggestion
  (`source = mail`, `created_by` = that user), in order, at most 10, skipping duplicates (existing
  `url_key`s and repeats within the mail). With exactly one new link, the mail's subject (without
  `Fwd:`/`WG:`/`Fw:` prefixes) becomes the `position`. The mail itself is not stored. Response
  status `suggestions` with the created ids.
- otherwise (unknown sender, or no link): the mail is processed as an untagged mail, so it lands in
  the Posteingang and nothing is lost.

No page is fetched for e-mailed links.

## Frontend

- Navigation: new tab **Vorschläge** (`/vorschlaege`) between Übersicht and Posteingang, with a badge
  of `suggestion_count`, kept in step by the page like the Posteingang badge.
- Form at the top: **Link** first. After a link is entered (on blur or paste), call `check`: show
  duplicates as a warning ("Schon vorgeschlagen am …" / "Bewerbung bei … existiert") and fill
  **Stelle** with the title if it is still empty. Then Firma, Ort, Bewerbungsfrist, Notiz,
  **Vorschlagen**. A hint shows the mail address `bewerbungen+vorschlag@…` when the inbound
  address is set.
- **Offen**: cards sorted by deadline (soonest first), suggestions without a deadline after them,
  newest first. Each card: position/company (or the link's host if both are empty), location,
  deadline (red "Frist abgelaufen" when passed, amber when within 7 days), note, who suggested it and
  when, the link (opens in a new tab). Buttons: **Bewerben** (asks for the company if empty, then
  opens the new application), **Nicht interessiert** (optional reason), **Bearbeiten**, **Löschen**
  (confirm).
- **Erledigt** (collapsed, with count): applied ones link to their application; declined ones show
  the reason and who decided; button **Wieder öffnen**.

## Reminder

`build_digest` gains two lists of open suggestions:

- **new**: created after `settings.last_reminder_sent_at` (all open ones if it was never sent)
- **deadline soon**: deadline from today up to 7 days ahead (local date), not in **new**

The digest is empty only if there are no due follow-ups, no inbox mails and both lists are empty.
The mail gets a section "Vorschläge" listing them (with deadline, link to `/vorschlaege`). Subject
priority: due follow-ups, then deadlines soon ("Bewerbungen: Frist läuft ab"), then new suggestions
("Bewerbungen: n neue Vorschläge"), then inbox mails.

## Export

- `vorschlaege.csv` (readable, semicolon, BOM): Status (Offen/Beworben/Nicht interessiert), Firma,
  Stelle, Ort, Frist, Link, Notiz, Vorgeschlagen von, Vorgeschlagen am, Entschieden von,
  Entschieden am, Grund.
- `suggestions.csv`: the raw table, like the other tables.

## Testing

Backend (pytest):

- URL normalisation and duplicate detection (suggestions and applications)
- CRUD, apply (creates the application with the fields; 409/422 cases), decline, reopen
- `check`: refuses non-http schemes and private/loopback addresses (DNS resolution mocked), follows
  a redirect only to a public address, extracts `og:title`/`<title>` (HTTP layer mocked), returns
  `title: null` on errors
- mail: a user's mail with links creates suggestions (limit, duplicates, subject as position); an
  unknown sender's mail and a mail without links land in the inbox
- reminder: new and deadline-soon suggestions, digest emptiness, subject priority
- export: `vorschlaege.csv` and `suggestions.csv`
- dashboard `suggestion_count`

Frontend: `npm run lint` and `npm run build`.
