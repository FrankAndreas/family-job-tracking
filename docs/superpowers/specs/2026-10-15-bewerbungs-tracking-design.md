# Bewerbungs-Tracking — Design

Date: 2026-10-15
Status: Draft for review

## Purpose

A small self-hosted web app to track job / apprenticeship applications ("Bewerbungen") for a
family: the son applies, the parent follows along. For each application it records the company
and a timeline of every communication (sent, followed up, reply received, followed up again,
interview, offer, rejection, …), including e-mails and their attachments.

Success means:

- Both users see at a glance which applications need a follow-up because nothing has happened
  for a while.
- E-mails about an application land in its timeline automatically when they are sent to (or
  BCC'd to) the application's own address, without copying text by hand.
- Both users get one daily reminder e-mail when something is due.

It runs on a Synology NAS like the peer projects `family-budget-dashboard` and `family-chore`,
reusing their stack, deployment and PIN login.

## Scope

In scope:

- Users with PIN login; every user sees and edits everything.
- Applications with master data, a timeline of events, and file attachments.
- Inbound e-mail via Cloudflare Email Routing + Email Worker, auto-assigned by `+tag`, otherwise
  collected in an inbox for manual assignment.
- Daily reminder digest via Resend.
- Data export as ZIP.

Out of scope (YAGNI): sending e-mails to companies from the app, push/browser notifications,
calendar integration, per-user privacy, multiple languages (UI is German only).

## Architecture

Two containers from GHCR, same layout as `family-budget-dashboard`:

| Component | Tech | Notes |
|---|---|---|
| `bewerbungen-backend` | Python, FastAPI, SQLAlchemy, SQLite | DB at `./data/bewerbungen.db`, files under `./data/files/`; runs as `PUID:PGID` |
| `bewerbungen-frontend` | React, Vite, TypeScript, Tailwind, nginx | serves the SPA on port 8080, proxies `/api` to the backend; published on `PORT` (default 8082) |
| `cloudflare/email-worker/` | Cloudflare Worker (TypeScript, wrangler) | deployed to Cloudflare, not to the NAS |

`./data` is a bind mount on the NAS (e.g. `/volume1/docker/bewerbungen/data`), so the database and
all attachments survive updates and are visible in File Station.

The NAS is reachable through the existing Cloudflare Tunnel at e.g. `bewerbungen.<domain>`,
protected by Cloudflare Access. The path `/api/inbound` gets an Access policy that admits the
Worker's service token.

Repository layout:

```
backend/            FastAPI app, Dockerfile, requirements.txt
frontend/           React app, Dockerfile, nginx.conf
cloudflare/email-worker/   Worker source, wrangler.toml, tests
tests/              backend pytest suite (+ tests/fixtures/*.eml)
scripts/            deploy-nas.sh, nas-update.sh
docker-compose.yml, .env.example, README.md, README_DOCKER.md
.github/workflows/  pr-checks.yml, ci-cd.yml
```

## Data model

`users`
- `id`, `name` (unique), `pin_hash`, `is_admin`, `email` (nullable), `wants_reminders` (bool),
  `failed_logins`, `locked_until`, `created_at`

`applications`
- `id`, `company`, `position`, `location`, `contact_name`, `contact_email`, `contact_phone`,
  `posting_url`, `channel` (`email` | `portal` | `post` | `in_person` | `other`), `notes`,
  `mail_tag` (unique, 4 random lowercase alphanumerics, e.g. `a7k2`), `archived` (bool),
  `created_at`, `created_by` (user id)

`events`
- `id`, `application_id`, `occurred_at`, `type`, `note`, `created_by` (user id, null when created
  from an e-mail), `email_id` (nullable), `created_at`
- `type` is one of: `sent` (Bewerbung gesendet), `followed_up` (Nachgefragt), `reply_received`
  (Antwort erhalten), `mail_sent` (Mail gesendet), `mail_received` (Mail erhalten), `call`
  (Telefonat), `interview` (Vorstellungsgespräch), `trial` (Schnupperlehre/Probetag), `offer`
  (Zusage), `rejection` (Absage), `withdrawn` (Zurückgezogen), `note` (Notiz)

`emails`
- `id`, `message_id` (unique; for deduplication), `from_addr`, `to_addrs`, `subject`,
  `body_text`, `received_at`, `raw_path` (stored `.eml`), `application_id` (nullable; null =
  inbox), `parse_error` (nullable text), `dismissed` (bool)

`attachments`
- `id`, `event_id` (nullable), `email_id` (nullable), `filename` (original), `path` (relative to
  `data/files`), `content_type`, `size`, `created_at`. Exactly one of `event_id` / `email_id` is
  set.

`settings` (single row)
- `followup_days` (default 10), `reminder_time` (default `07:00`, Europe/Zurich),
  `inbound_address` (e.g. `bewerbungen@<domain>`, used to display `+tag` addresses),
  `last_reminder_date`, `last_reminder_attempt_at`, `last_reminder_sent_at`,
  `last_reminder_error` (nullable), `last_inbound_at`, `last_inbound_error` (nullable)

### Derived status

The status of an application is computed from its events, never stored:

- `closed_offer` / `closed_rejection` / `closed_withdrawn` if the latest of `offer`, `rejection`,
  `withdrawn` exists (the latest closing event wins).
- otherwise `in_contact` if any `reply_received`, `mail_received`, `call`, `interview` or `trial`
  event exists.
- otherwise `open` if a `sent` event exists.
- otherwise `draft`.

### Follow-up due

An application is *due* when it is not archived, its status is `open` or `in_contact`, and its
newest event is more than `followup_days` days old.

## File storage

Attachments (uploaded with an event or extracted from an e-mail) and raw `.eml` files are stored
with readable names:

```
data/files/<company-slug>/<YYYY-MM-DD>_<company-slug>_<original-name>.<ext>
data/files/<company-slug>/<YYYY-MM-DD>_<company-slug>_<original-name>_2.<ext>   # counter on collision
data/files/_posteingang/<YYYY-MM-DD>_<sender-domain>_<original-name>.<ext>      # unassigned e-mails
```

- The slug is lower-case, `ä→ae`, `ö→oe`, `ü→ue`, `ß→ss`, other non-alphanumerics → `-`, collapsed
  and trimmed, at most 40 characters. The original name is sanitised the same way except case
  is kept. The date is the event's or e-mail's date.
- Raw e-mails are stored as `<date>_<slug>_mail-<subject-slug>.eml`.
- When an inbox e-mail is assigned, its files are moved into the company folder (renamed with the
  company slug) and `path` is updated.
- Renaming a company does not move existing files; `path` in the database stays authoritative.
- Files are served only through an authenticated download endpoint, never as static files.

## Authentication

Same as `family-budget-dashboard`:

- Login by choosing a user and entering a 4–8 digit PIN; bcrypt hash; JWT (HS256, `SECRET_KEY`)
  stored in the browser, valid for 30 days.
- On an empty database the backend creates the admin user `Admin` with `INITIAL_ADMIN_PIN` or a
  random 4-digit PIN printed once to the log as `INITIAL PIN`.
- Admins create, rename and delete users and reset PINs. Every user can change their own PIN,
  e-mail address and reminder opt-in.
- After 5 wrong PINs a user is locked for 15 minutes (`locked_until`); a correct login resets the
  counter.

## Backend API

All under `/api`, JSON, JWT bearer auth unless noted.

- `GET /api/users/public` (no auth): names for the login screen. `POST /api/token`: login.
- `GET/PATCH /api/me`, `POST /api/me/pin`.
- `GET/POST /api/users`, `PATCH/DELETE /api/users/{id}`, `POST /api/users/{id}/pin` (admin).
- `GET /api/applications?status=&q=&archived=` (list with derived status, last event, due flag),
  `POST`, `GET/PATCH/DELETE /api/applications/{id}`.
- `GET /api/dashboard`: counts per status and the due list.
- `POST /api/applications/{id}/events` (multipart: fields + files), `PATCH/DELETE /api/events/{id}`.
- `GET /api/attachments/{id}`: download. `DELETE /api/attachments/{id}`.
- `GET /api/inbox`: unassigned, not dismissed e-mails with a suggested application.
  `POST /api/inbox/{email_id}/assign` (`application_id`, optional event type),
  `POST /api/inbox/{email_id}/create-application` (`company`, `position`),
  `POST /api/inbox/{email_id}/dismiss`.
- `GET /api/emails/{id}`: full e-mail incl. body. `GET /api/emails/{id}/raw`: the `.eml`.
- `GET/PATCH /api/settings` (patch: admin).
- `GET /api/integrations`: status of the optional integrations (see "Integration status").
- `GET /api/export`: ZIP with CSVs of all tables and the `files/` tree.
- `POST /api/inbound` (no JWT; `X-Inbound-Secret` header): raw MIME body.
- `GET /health` (no auth).

## Inbound e-mail

Cloudflare setup (documented in `README_DOCKER.md`):

1. Email Routing enabled on the domain, subaddressing enabled, a custom address
   `bewerbungen@<domain>` routed to the Worker `bewerbungen-inbound`.
2. The Worker reads `message.raw`, and POSTs it to `APP_URL/api/inbound` with headers
   `CF-Access-Client-Id`, `CF-Access-Client-Secret` and `X-Inbound-Secret` (all Worker secrets).
3. If the response is not 2xx, the Worker calls `message.setReject(...)`, so the sender gets a
   bounce instead of the mail being lost silently.

Backend processing of `POST /api/inbound`:

1. Reject with 401 unless `X-Inbound-Secret` matches `INBOUND_SECRET`; reject bodies over 25 MB
   with 413. If `INBOUND_SECRET` is unset, the endpoint returns 503.
2. Parse with Python's `email` package (`policy.default`). Take the `Message-ID`; if it already
   exists, return 200 without changes (duplicate delivery).
3. Find the tag: the first recipient in `To`/`Cc`/`Delivered-To`/`X-Original-To` of the form
   `<local>+<tag>@<domain>` whose tag matches an application's `mail_tag` (case-insensitive).
4. Store the raw `.eml`, the text body (plain part, else HTML converted to text) and all
   attachments using the file naming rules above.
5. With a matching tag: link the e-mail to the application and create an event at the e-mail's
   `Date`: `mail_sent` if the sender address belongs to a user (`users.email`), else
   `mail_received`. The event note is the subject. Without a tag: the e-mail goes to the inbox.
6. If parsing fails, store the raw `.eml` anyway in `_posteingang`, create an inbox entry with
   `parse_error` set and subject "(konnte nicht gelesen werden)", and return 200.

Inbox suggestion: the application whose `contact_email` domain, or whose earlier e-mails' sender
domain, equals the e-mail's sender domain (ignoring common free-mail domains such as gmail.com,
gmx.ch, bluewin.ch, outlook.com, hotmail.com, icloud.com, yahoo.com). If several match, the most
recently active one.

## Reminder e-mails

- Optional. The app starts and works fully without it: when `RESEND_API_KEY` or `MAIL_FROM` is
  missing, the reminder task is not started and the integration shows as "nicht konfiguriert".
- A background task in the backend wakes every hour. If the local time (Europe/Zurich) is past
  `reminder_time` and `last_reminder_date` is not today, it builds the digest:
  - due applications (company, position, days since last event, link `APP_URL/bewerbungen/{id}`)
  - number of unassigned inbox e-mails, with a link to the inbox
- If the digest is empty, it sets `last_reminder_date` to today and sends nothing.
- Otherwise it sends one e-mail (German, simple HTML + text) via the Resend HTTP API to every user
  with `wants_reminders` and an `email`. Only after all sends succeed is `last_reminder_date`
  set; on failure it logs the error, stores it in `last_reminder_error` and retries on the next
  hourly run. Every attempt sets `last_reminder_attempt_at`; a success sets
  `last_reminder_sent_at` and clears the error.
- The Settings page has a "Test-Erinnerung senden" button for the current user.

## Integration status

Both integrations are optional; the app never refuses to start because one is missing or broken.
Startup logs one line per integration ("configured" / "not configured").

`GET /api/integrations` returns, per integration, a state and details:

| Integration | States | Details shown |
|---|---|---|
| Eingehende Mails (Cloudflare Worker) | `not_configured` (no `INBOUND_SECRET`), `waiting` (configured, nothing received yet), `ok`, `error` (last delivery failed to parse) | inbound address, time of last received e-mail, last error |
| Erinnerungen (Resend) | `not_configured` (no `RESEND_API_KEY`/`MAIL_FROM`), `ok`, `error` (last send failed) | sender, recipients (users with reminders on), next planned run, last attempt, last successful send, last error |

`last_inbound_at` is set on every accepted `POST /api/inbound`; `last_inbound_error` is set when
parsing fails and cleared by the next successful one. `APP_URL` missing is shown as a warning on
the reminder integration (links in the e-mail would be missing).

## Frontend

German UI, mobile-first, React Router.

1. **Login**: user tiles, PIN pad.
2. **Übersicht** (`/`): status counts as tiles; "Nachfragen fällig" list; list of active
   applications (company, position, status badge, last event and date), with status filter,
   search and "Archivierte zeigen" toggle; button "Neue Bewerbung".
3. **Bewerbung** (`/bewerbungen/:id`): editable master data; the application's address
   `bewerbungen+<tag>@<domain>` with copy button; archive/delete; timeline newest first;
   "+ Ereignis" form (type, date/time defaulting to now, note, files); e-mail events expand to
   show the body and attachments.
4. **Posteingang** (`/posteingang`): unassigned e-mails with count badge in the navigation;
   per e-mail: suggested application, "Bewerbung wählen", "Neue Bewerbung daraus erstellen",
   "Verwerfen".
5. **Einstellungen** (`/einstellungen`): own PIN, e-mail and reminder opt-in; admin: users,
   follow-up days, reminder time, inbound address; export ZIP; section **Integrationen** with a
   card per integration (green ok / grey nicht konfiguriert / orange wartet / red Fehler, plus
   the details above) and the "Test-Erinnerung senden" button on the Resend card. A red
   integration also shows a small warning dot on the Einstellungen navigation item.

## Configuration (`.env`)

| Variable | Purpose |
|---|---|
| `PUID`, `PGID` | user the backend runs as |
| `PORT` | NAS port of the frontend (default 8082) |
| `SECRET_KEY` | signs JWTs; random if empty (logins lost on restart) |
| `INITIAL_ADMIN_PIN` | PIN for `Admin` on an empty database |
| `INBOUND_SECRET` | shared secret with the Worker |
| `APP_URL` | public URL, for links in reminders |
| `RESEND_API_KEY`, `MAIL_FROM` | reminder e-mails; off if empty |
| `TZ` | default `Europe/Zurich` |

## Error handling

- API errors return JSON `{"detail": "..."}` with proper status codes; the frontend shows them as
  a toast in German.
- Unreadable inbound e-mails are kept (see above); nothing is dropped.
- Failed reminder sends are logged and retried hourly.
- Deleting an application deletes its events, e-mails and files (with a confirmation dialog in the
  UI); archiving is the normal way to hide finished applications.

## Testing

- Backend (pytest, in-memory/tmp SQLite, tmp `data/files`):
  - auth: login, wrong PIN, lockout and unlock, admin-only endpoints
  - CRUD for applications, events, attachments; file naming, slugging, collision counter
  - derived status and follow-up due logic
  - inbound: tagged mail, untagged mail, mail sent by a user, attachments, duplicate
    `Message-ID`, broken MIME, wrong secret, oversize body (fixtures in `tests/fixtures/*.eml`)
  - inbox: suggestion, assign (files moved), create application, dismiss
  - reminders: digest content, empty digest, opt-out, failure and retry (Resend mocked)
  - integration status: not configured, waiting, ok, error for both integrations; app starts
    without `RESEND_API_KEY` and `INBOUND_SECRET`
  - export ZIP contents
- Frontend: `tsc`, ESLint and `vite build` in CI.
- Worker: Vitest test with a mocked `fetch` for success and reject paths.

## CI/CD and deployment

Copied from `family-budget-dashboard` and adapted:

- `pr-checks.yml`: backend tests, frontend lint/type-check/build, worker tests.
- `ci-cd.yml`: on `main`, build and push `ghcr.io/frankandreas/bewerbungs-tracking/backend` and
  `.../frontend` (`latest` + commit SHA).
- `docker-compose.yml` (installed on the NAS as `compose.yaml`), `.env.example`,
  `scripts/nas-update.sh` (nightly pull + restart), `scripts/deploy-nas.sh`.
- `README_DOCKER.md`: NAS install, first login, Cloudflare Tunnel hostname and Access policies
  (including the service token for `/api/inbound`), Email Routing and Worker deploy with
  `wrangler`, Resend domain and API key, backup (`data/` folder).
