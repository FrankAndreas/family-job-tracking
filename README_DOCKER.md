# Running Family Job Tracking on a Synology NAS

The app runs as two containers from images on GitHub Container Registry (GHCR):

- **backend** (`ghcr.io/frankandreas/family-job-tracking/backend`): the API; the database and all
  attachments live in `./data`
- **frontend** (`ghcr.io/frankandreas/family-job-tracking/frontend`): nginx serving the app on port
  8080 inside the container, forwarding `/api` to the backend

It is set up like family-budget-dashboard and family-chore, so all three run side by side
(family-chore on 8080, family-budget on 8081, this app on **8082**). A second, fully separate
instance, e.g. for a parent's own applications, can run next to it on 8083 (see the section at the end).

Two integrations are optional and can be added later; the app runs fine without them:

- **Incoming e-mails** through Cloudflare Email Routing and a small Email Worker
- **Daily reminders** through Resend

## Installation

1. **Choose the user the app runs as.** Reuse the DSM user of the other family apps (e.g.
   `familyapps`), or create one in **Control Panel → User & Group** with no application permissions.
   Look up its IDs over SSH:
   ```bash
   id familyapps    # e.g. uid=1031(familyapps) gid=100(users)
   ```
2. **Prepare the folder.** Create `/volume1/docker/family-jobs` and upload `docker-compose.yml` into
   it **renamed to `compose.yaml`**. Then create the data folder, owned by the app's user:
   ```bash
   cd /volume1/docker/family-jobs
   sudo mkdir -p data
   sudo chown -R 1031:100 data    # the IDs from step 1
   ```
3. **Create `.env`** (all settings are explained in `.env.example`):
   ```bash
   printf 'PUID=1031\nPGID=100\nPORT=8082\nTZ=Europe/Zurich\nSECRET_KEY=%s\nAPP_URL=https://bewerbungen.example.ch\n' \
     "$(openssl rand -hex 32)" | sudo tee .env
   sudo chmod 600 .env
   ```
4. **Start** it:
   ```bash
   sudo docker-compose pull
   sudo docker-compose up -d
   ```
5. **Open** `http://<NAS_IP>:8082`.

### First login
On an empty database the backend creates the user **Admin** with a random 4-digit PIN, printed once in
its log:
```bash
sudo docker logs jobs-backend 2>&1 | grep "INITIAL PIN"
```
Log in, then in **Einstellungen**:
- change the PIN
- rename Admin
- add the other user (e.g. your son) under **Benutzer**

Everyone sees and edits all applications. To choose the first PIN yourself, set
`INITIAL_ADMIN_PIN=1234` in `.env` before the first start.

### Where the data is
Everything worth keeping is in `data/`:
- `jobs.db`: the database
- `files/<firma>/`: attachments and the original e-mails (`.eml`), named
  `<date>_<firma>_<original name>`
- `files/_posteingang/`: files of e-mails that are not assigned yet
- `files/_unterlagen/<kategorie>/`: the documents of the page **Unterlagen** (reports, certificates,
  CV, cover letter), named `<date>_<kategorie>_<title>`

Include `data/` in your Hyper Backup task. **Einstellungen → Daten exportieren** downloads everything
as a ZIP: `uebersicht.csv` (one row per application with status and dates), `zeitleiste.csv` (all
events with German labels), the raw tables as CSV and the `files/` folder. The CSVs use semicolons and a
UTF-8 BOM, so Excel opens them directly. The export is an archive, not a restore format: back up
`data/` for that.

## Reaching the app from outside (Cloudflare Tunnel and Access)

The NAS is already connected to Cloudflare Zero Trust with a tunnel. Cloudflare renames dashboard
menus from time to time; older names are given in brackets.

1. **Route the hostname to the app.** In **Zero Trust → Networks → Connectors → Cloudflare Tunnels**
   (Networks → Tunnels), open your tunnel, choose **Edit**, then **Published application routes**
   (Public Hostname) → **Add**:
   - subdomain `bewerbungen`, your domain, path empty
   - service type `HTTP`, URL `<NAS_IP>:8082`

   Port 8082 is the frontend container; its nginx passes `/api` on to the backend. Use the NAS's LAN
   IP if `cloudflared` runs as a container in a bridge network (`localhost` would be the `cloudflared`
   container itself); `localhost:8082` only works if it runs on the host network. Cloudflare creates
   the DNS record. A **502 Bad Gateway** means `cloudflared` can't reach the port.
2. **Access application for people.** In **Access controls → Applications → Create new
   application** (Access → Applications → Add) choose **Public DNS** (Self-hosted):
   - subdomain `bewerbungen`, your domain, path empty
   - a policy with action **Allow** that includes your family's e-mail addresses

   The PIN login of the app comes on top of that.
3. Set `APP_URL=https://bewerbungen.<domain>` in `.env` and restart (`sudo docker-compose up -d`).

## Incoming e-mails (Cloudflare Email Worker)

Each application has its own address `bewerbungen+<tag>@<domain>`. A mail sent, CC'd, BCC'd or
forwarded to it lands in that application's timeline, including attachments. A mail to plain
`bewerbungen@<domain>` lands in the timeline too if its sender's domain fits exactly one active
application (its contact address or earlier mails, not for gmail.com and the like, not for your own
addresses). Everything else lands in the **Posteingang**, with a suggestion where one fits.

Links mailed to `bewerbungen+vorschlag@<domain>` from a user's saved address become suggestions on
the page **Vorschläge** (one per link, at most 10 per mail). This needs no extra Email Routing rule.
From any other sender, or without a link, the mail lands in the Posteingang.

`bewerbungen` is only the mailbox name in front of the `@`; mail is received on your main domain.
Check first that the domain doesn't already receive mail elsewhere:

```bash
dig +short MX <domain>
```

No output or only `route*.mx.cloudflare.net` is fine. If another provider is listed (Google,
Microsoft, Infomaniak, …), enabling Email Routing would take mail away from those mailboxes: use an
e-mail subdomain instead (**Email Routing → Settings → Subdomains**, e.g. `jobs.<domain>`) and
replace `<domain>` below with it. Otherwise do **not** add a subdomain there.

1. **Secret for the app.** Add it to `.env`, then restart:
   ```bash
   echo "INBOUND_SECRET=$(openssl rand -hex 32)" | sudo tee -a .env
   sudo docker-compose up -d
   ```
2. **Service token for the worker.** In **Zero Trust → Access controls → Service credentials →
   Service Tokens → Create Service Token** (Access → Service Auth), name it `family-jobs-inbound`,
   choose **Non-expiring** and note the Client ID and Client Secret. The secret is shown only once.
3. **Policy for the token.** In **Access controls → Policies → Add a policy**:
   - name `family-jobs-inbound-token`
   - action **Service Auth** (not Allow)
   - include rule: selector **Service Token**, value `family-jobs-inbound`
4. **Access application for the worker.** In **Access controls → Applications → Create new
   application → Public DNS**:
   - name `family-jobs-inbound`
   - subdomain `bewerbungen`, your domain, path `api/inbound` (no leading slash, no `*`)
   - under the policies, **Select existing policies** → `family-jobs-inbound-token`
   - leave the login methods as they are; optionally turn on **401 Response for Service Auth
     policies**, so a wrong token gives a 401 instead of a redirect

   You now have two applications on the same hostname. The one with the path is more specific and
   takes precedence for `/api/inbound`; everything else stays behind the one from above. Only the
   worker gets through to `/api/inbound`, and the app checks `INBOUND_SECRET` on top of that.
   Check both layers:
   ```bash
   # without token: 302 or 401 from Cloudflare
   curl -s -o /dev/null -w "%{http_code}\n" -X POST https://bewerbungen.<domain>/api/inbound
   # with token: 401 from the app, because INBOUND_SECRET is missing
   curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "CF-Access-Client-Id: <id>" \
     -H "CF-Access-Client-Secret: <secret>" https://bewerbungen.<domain>/api/inbound
   ```
   A 302 on the second call means the policy doesn't apply: check its action and token.
5. **Deploy the worker** from a checkout of this repository. Deploy first, so the worker exists,
   then set its secrets. Put the values in environment variables first, so they stay out of the
   shell history:
   ```bash
   cd cloudflare/email-worker
   npm ci
   npx wrangler login
   npx wrangler deploy
   # APP_URL=https://bewerbungen.<domain>, INBOUND_SECRET from step 1,
   # CF_ACCESS_CLIENT_ID and CF_ACCESS_CLIENT_SECRET from step 2
   for name in APP_URL INBOUND_SECRET CF_ACCESS_CLIENT_ID CF_ACCESS_CLIENT_SECRET; do
     printf %s "${!name}" | npx wrangler secret put "$name"
   done
   npx wrangler secret list    # shows the names, not the values
   ```
   `printf %s` keeps a trailing newline out of the secret. The app URL is a secret too, so
   `wrangler.toml` holds no personal data. Until all four are set, the worker rejects mails.
6. **Route the address to the worker.** This is in the regular dashboard
   (**dash.cloudflare.com**), not in Zero Trust: open your domain, then **Email → Email Routing**:
   - enable it if it isn't, and let Cloudflare add the MX, SPF and DKIM records. They show as
     "Locked". Resend is unaffected, as it sends from its own subdomain.
   - in **Settings**, enable **Subaddressing**, so `bewerbungen+tag@` reaches the same rule
   - under **Routing rules → Custom addresses → Create address**, enter `bewerbungen`, set the action
     to **Send to a Worker** and choose `family-jobs-inbound`. The address shown must be
     `bewerbungen@<domain>`. If the worker isn't in the list, it isn't deployed yet.
7. **Fallback address (recommended).** While the app is unreachable (an update, a NAS restart, a
   tunnel outage), the worker can't deliver. Without a fallback it rejects the mail and the sender,
   e.g. a company's HR, gets a bounce. With one, the worker forwards the mail there instead, with a
   header `X-Family-Jobs-Error` saying why, and sends a short note next to it ("Bewerbungen: Mail
   weitergeleitet, App nicht erreichbar") with the reason, sender and subject. Forward the mail to
   `bewerbungen@<domain>` once the app runs again. The note uses the worker's `send_email` binding
   `NOTIFY`; if Cloudflare refuses to send it, the mail is forwarded all the same.
   - In **Email Routing → Destination addresses → Add destination address**, add an address
     outside this domain (e.g. your own mailbox) and confirm the verification mail.
   - Set it on the worker:
     ```bash
     printf %s "$FALLBACK_ADDRESS" | npx wrangler secret put FALLBACK_ADDRESS
     ```
   - Test it: stop the app (`sudo docker stop jobs-backend`), send a mail to `bewerbungen@<domain>`,
     check that it arrives at the fallback address, then start the app again
     (`sudo docker start jobs-backend`).

   If forwarding fails too (e.g. the address isn't verified), the worker rejects the mail.
8. **In the app**, open **Einstellungen → App-Einstellungen** (admins only):
   - set the **Eingangsadresse** to `bewerbungen@<domain>`. This is an app setting, not a `.env`
     variable.
   - check that the card **Eingehende Mails** says "Wartet"
   - send a test mail to `bewerbungen@<domain>`

   The card turns "OK" and the mail appears in the Posteingang. Then send one with an attachment to
   an application's `+tag` address: it lands in that application's timeline.

If the app is unreachable or refuses the mail, the worker rejects it, so the sender gets a bounce and
nothing is lost silently. Mails the app cannot read are kept as `.eml` in the Posteingang. Delivering
the same mail twice is detected by its Message-ID.

**Mails from you count as sent:** save your own address under **Einstellungen → Mein Konto** (the card
**Eingehende Mails** warns about users without one). Your first mail to an application, i.e. the
application itself with its address in BCC, becomes "Bewerbung gesendet", so the status turns "Offen"
and the follow-up reminder starts; later ones become "Mail gesendet". A company's reply that you
forward (subject starting with `WG:`, `Fw:` or `Fwd:`) becomes "Antwort erhalten", filed under the
sender named in the forwarded text, so it also finds its application by that sender's domain.

**Catching replies that go to a private mailbox.** Companies usually answer the address the
application was sent from, not the `+tag` address. Let that mailbox forward them automatically: in
Gmail, for example, add `bewerbungen@<domain>` under **Settings → Forwarding and POP/IMAP → Add a
forwarding address** (Gmail sends a confirmation code there; it shows up in the Posteingang), then
create a filter such as `from:(@migros.ch OR @coop.ch)` with **Forward it to** that address.
Automatic forwarding keeps the company as the sender, so the app assigns the mail by its domain.
A mail forwarded by hand comes from you instead and lands in the Posteingang.

## Daily reminders (Resend)

1. In Resend, verify the domain (or a subdomain) you want to send from. If Papra already sends through
   Resend with this domain, it is verified already.
2. Create an API key with **Sending access** for that domain.
3. Add it to `.env` and restart:
   ```bash
   printf 'RESEND_API_KEY=re_...\nMAIL_FROM=Bewerbungen <bewerbungen@example.ch>\n' | sudo tee -a .env
   sudo docker-compose up -d
   ```
4. In **Einstellungen**, do the following:
   - every user who wants reminders saves their e-mail address and ticks **Tägliche Erinnerung**
   - an admin sets **Nachfragen nach (Tagen)** (default 10) and **Erinnerung um** (default 07:00)
   - press **Test-Erinnerung senden** on the **Erinnerungen** card

Once a day, after the set time, one e-mail goes to everyone who opted in. It lists the applications
with no news for longer than the follow-up period, and the number of unassigned inbox mails. Nothing
is sent on days without anything due. If sending fails, the card turns red with the error and the
app retries every 15 minutes.

## Automatic updates

`scripts/nas-update.sh` checks for new images and installs them, the same way as in the other family
apps:
- it pulls the images
- if there is a new one, it backs up the database to `db-backups/`, keeps the old images as
  `:previous` and restarts the app
- it waits until the backend is healthy, logging to `logs/update.log`

1. Copy `scripts/nas-update.sh` into `/volume1/docker/family-jobs` and make it executable (or let
   `scripts/deploy-nas.sh` upload it):
   ```bash
   sudo chmod +x /volume1/docker/family-jobs/nas-update.sh
   sudo /volume1/docker/family-jobs/nas-update.sh     # should end with "Up to date" or "Update complete"
   ```
2. In **Control Panel → Task Scheduler → Create → Scheduled Task → User-defined script**:
   - user **root**
   - daily, a few minutes apart from the other apps' updates (e.g. 04:00)
   - command `bash /volume1/docker/family-jobs/nas-update.sh`

If the images are private, log in to the registry once as root:
`sudo docker login ghcr.io -u <github-user>` with a token that has `read:packages`.

To deploy right away from your computer:
```bash
cp .deploy.env.example .deploy.env   # once; then set NAS_HOST and NAS_DIR
scripts/deploy-nas.sh
```

## A second, separate instance

To track applications that only one person may see, e.g. a parent's own job search, run the app a
second time. The two instances share nothing: separate folder, database, files, users, URL and
inbound address, so nobody in one instance can see the other's data. The images and the code are
the same. The examples use the suffix `papa`; pick your own.

| | First instance | Second instance |
|---|---|---|
| NAS folder | `/volume1/docker/family-jobs` | `/volume1/docker/family-jobs-papa` |
| `.env`: `PORT` / `CONTAINER_PREFIX` | `8082` / `jobs` | `8083` / `jobs-papa` |
| Containers | `jobs-backend`, `jobs-frontend` | `jobs-papa-backend`, `jobs-papa-frontend` |
| Hostname | `bewerbungen.<domain>` | `bewerbungen-papa.<domain>` |
| Inbound address | `bewerbungen@<domain>` | `bewerbungen-papa@<domain>` |
| Email Worker | `family-jobs-inbound` | `family-jobs-inbound-papa` |

1. **Install it** as in [Installation](#installation), with the second folder. Use a new
   `SECRET_KEY` and `INBOUND_SECRET`, and add to its `.env`:
   ```
   PORT=8083
   CONTAINER_PREFIX=jobs-papa
   APP_URL=https://bewerbungen-papa.<domain>
   ```
   `RESEND_API_KEY` and `MAIL_FROM` can be the same as in the first instance. In the Container
   Manager, give the project its own name (e.g. `family-jobs-papa`). The first login uses its own
   initial PIN: `sudo docker logs jobs-papa-backend 2>&1 | grep "INITIAL PIN"`.
2. **Tunnel route:** add a second published application route `bewerbungen-papa` → `HTTP`,
   `<NAS_IP>:8083`.
3. **Access application for people:** a new application for `bewerbungen-papa.<domain>` whose
   policy allows **only your own** e-mail address. Don't add the hostname to the family application,
   or everyone in the family gets past Cloudflare Access (the PIN would still be needed).
4. **Access for the worker:** open the existing application `family-jobs-inbound` and add a second
   public hostname: `bewerbungen-papa`, your domain, path `api/inbound`. The same service token
   and policy then cover both instances.
5. **Deploy the worker a second time** under its own name. `--name` overrides the name in
   `wrangler.toml`, for the deployment and for each secret:
   ```bash
   cd cloudflare/email-worker
   npx wrangler deploy --name family-jobs-inbound-papa
   # APP_URL=https://bewerbungen-papa.<domain>, INBOUND_SECRET of the second instance,
   # CF_ACCESS_CLIENT_ID and CF_ACCESS_CLIENT_SECRET as for the first worker
   for name in APP_URL INBOUND_SECRET CF_ACCESS_CLIENT_ID CF_ACCESS_CLIENT_SECRET FALLBACK_ADDRESS; do
     printf %s "${!name}" | npx wrangler secret put "$name" --name family-jobs-inbound-papa
   done
   ```
   Drop `FALLBACK_ADDRESS` from the list if you don't use one. Later updates of the worker code
   need both deployments: `npx wrangler deploy` and
   `npx wrangler deploy --name family-jobs-inbound-papa`.
6. **Email Routing:** create the custom address `bewerbungen-papa` → **Send to a Worker** →
   `family-jobs-inbound-papa`. Subaddressing is already on, so `bewerbungen-papa+<tag>@` works too.
7. **In the second app:** set the **Eingangsadresse** to `bewerbungen-papa@<domain>` and send a test
   mail.
8. **Updates and backups:** copy `nas-update.sh` into the second folder too and schedule it as a
   second task (it reads `CONTAINER_PREFIX` from that folder's `.env`). Add the second `data/`
   folder to Hyper Backup.

## Troubleshooting

| Symptom | Check |
|---|---|
| Card "Eingehende Mails" is red | the error shown on the card; the mail is still in the Posteingang as `.eml` |
| Mails bounce with "nicht angenommen (HTTP 302)" | the Access service token or the `api/inbound` Access application |
| Mails bounce with "HTTP 401" | `INBOUND_SECRET` differs between `.env` and the worker secret |
| Mails bounce with "APP_URL ist im Worker nicht gesetzt" | the worker secret `APP_URL` (`npx wrangler secret list`) |
| Mails bounce with "nicht erreichbar" | `APP_URL` in the worker and the tunnel's published application route |
| Mails arrive at the fallback address | the header `X-Family-Jobs-Error` of the forwarded mail says why |
| Card "Erinnerungen" is red | the Resend error shown on the card (unverified domain, wrong key) |
| Reminder e-mails have no links | `APP_URL` in `.env` |
| Everyone is logged out after an update | `SECRET_KEY` is empty in `.env` |
