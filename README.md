# Family Job Tracking

A small self-hosted app to keep track of job and apprenticeship applications: every company, and a
timeline of everything that happened (sent, followed up, reply, interview, offer, …), including the
e-mails and their attachments. Built for a family: the applicant and a parent both log in with a PIN
and see everything.

- **Overview**: counts per status, the applications that need a follow-up, search and filters.
- **Timeline per application**: events with notes and files; files are stored on the NAS with
  readable names (`files/migros/2026-10-15_migros_Lebenslauf.pdf`).
- **E-mails into the timeline**: each application has its own address
  (`bewerbungen+a7k2@your-domain`); put it in BCC or forward mails there and they appear in the
  timeline. Mails without such an address land in the inbox for one-click assignment.
- **Daily reminder** by e-mail (via Resend) when a follow-up is due.

The UI is German. Stack: FastAPI + SQLite, React + Vite + Tailwind, nginx, a Cloudflare Email
Worker; runs as two Docker containers next to family-budget-dashboard and family-chore.

## Install
See [README_DOCKER.md](README_DOCKER.md) for the NAS setup, Cloudflare and Resend.

## Development

```bash
python3 -m venv venv
venv/bin/pip install -r backend/requirements.txt -r tests/requirements.txt
venv/bin/pytest                                   # backend tests

mkdir -p data/dev
DATA_DIR=data/dev DATABASE_URL=sqlite:///data/dev/dev.db INITIAL_ADMIN_PIN=1234 SECRET_KEY=dev \
  venv/bin/uvicorn app.main:app --app-dir backend --reload --port 8000

cd frontend && npm install && npm run dev         # http://localhost:5173, proxies /api to :8000
cd cloudflare/email-worker && npm install && npm test
```

The design is in `docs/superpowers/specs/2026-10-15-family-job-tracking-design.md`.

## License

MIT, see [LICENSE](LICENSE).
