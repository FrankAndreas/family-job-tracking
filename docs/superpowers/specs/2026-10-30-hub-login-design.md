# Job tracking: log in through the family hub, home only

Date: 2026-10-30. Rollout step 5 of the family hub (FrankAndreas/family-hub), after the budget app, the meal planner
and the chores app, and the same way. The user chose **home only** (until now the app was reached through the
Cloudflare Tunnel behind Cloudflare Access plus a PIN). Points marked **(my call)** were settled by Claude.

## Behaviour

- **Login:** the hub's `hub_session` cookie at `https://jobs.local.<domain>`, or Bearer for tests and scripts.
  - The hub's `/api/session?app=jobs` says whose login it is and whether they may use the app.
  - A change made with the cookie needs `X-Requested-With: jobs`.
  - A request with `Cf-Connecting-Ip` is no login: the tunnel carries only the e-mail worker's `/api/inbound`, with
    its own service token and `INBOUND_SECRET`.
- **People come from the hub:**
  - A parent there is **admin** here **(my call)**; the name follows the hub.
  - E-mail and reminders stay here: everyone sets their own, and admins can set them for others.
  - Rows from before the hub are linked by name, once, at the first sync. A hub parent matches an admin row and
    anyone else a non-admin row.
- **Removed in the hub:**
  - The person is hidden: no reminders, and their mails don't create suggestions.
  - An admin deletes their data; their applications and events stay.
  - `DELETE /users/{id}` only works for hidden people (409 `still_in_hub`).
- **Gone:**
  - the token login, PINs, the login page, adding, renaming and admin toggles;
  - `SECRET_KEY`, `INITIAL_ADMIN_PIN`, bcrypt and PyJWT.
- **"Abmelden"** goes to `<HUB_PUBLIC_URL>/logout?next=<app>`. A 401 sends the browser to the hub. "Kein Zugang" and
  "Anmelden geht gerade nicht" each get their own page.
- **Schema:** the app has no migrations. `upgrade.py` adds `users.hub_id` (unique index) and `is_active` on start and
  drops `pin_hash`, `failed_logins` and `locked_until`; each step checks first.
- **`APP_URL`** (the links in reminders) becomes the home address. The worker's own `APP_URL` stays the tunnel
  hostname.
- **A second instance** gets its own hub key (e.g. `jobs-papa`), with only its owner ticked.
