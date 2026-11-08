import type { Page, Route } from '@playwright/test';
import type {
    AppDocument,
    AppSettings,
    ApplicationDetail,
    ApplicationSummary,
    Dashboard,
    DossierPreview,
    InboxItem,
    Integrations,
    Suggestion,
    User,
} from '../../frontend/src/types';

// What the API answers in the browser tests, typed with the frontend's own types (npm run type-check), so a changed
// answer shows here. Invented people and companies only: the repository is public

export const LENA: User = { id: 1, name: 'Lena', is_admin: true, email: 'lena@example.org', wants_reminders: true, email_from_hub: true };

const SUMMARY: ApplicationSummary = {
    id: 1,
    company: 'Muster Elektro AG',
    position: 'Elektroinstallateurin EFZ',
    location: 'Bern',
    status: 'in_contact',
    closed_by: null,
    closed_note: null,
    archived: false,
    due: true,
    last_event_type: 'sent',
    last_event_at: '2026-10-20T09:00:00Z',
    days_since_last: 19,
    mail_tag: 'muster-1',
};

const APPLICATIONS: ApplicationSummary[] = [
    SUMMARY,
    { ...SUMMARY, id: 2, company: 'Beispiel Holzbau GmbH', position: 'Zimmerin EFZ', status: 'closed_offer', due: false, mail_tag: 'beispiel-2' },
    {
        ...SUMMARY,
        id: 3,
        company: 'Probe Logistik',
        position: 'Logistikerin EFZ',
        status: 'closed_rejection',
        closed_by: 'position_filled',
        closed_note: 'Schon vergeben',
        archived: true,
        due: false,
        mail_tag: 'probe-3',
    },
];

const ATTACHMENT = { id: 5, filename: 'antwort.pdf', content_type: 'application/pdf', size: 48_000, path: 'x' };

const DETAIL: ApplicationDetail = {
    ...SUMMARY,
    contact_name: 'Frau Beispiel',
    contact_email: 'lehre@muster.example',
    contact_phone: '031 000 00 00',
    posting_url: 'https://muster.example/lehre',
    channel: 'email',
    notes: 'Schnuppern im Frühling',
    created_at: '2026-10-01T09:00:00Z',
    created_by_name: 'Lena',
    mail_address: 'bewerbungen+muster-1@example.org',
    events: [
        { id: 11, occurred_at: '2026-10-20T09:00:00Z', type: 'sent', note: '', created_by_name: 'Lena', email: null, attachments: [ATTACHMENT] },
        { id: 12, occurred_at: '2026-10-25T14:00:00Z', type: 'call', note: 'Rückruf nächste Woche', created_by_name: 'Lena', email: null, attachments: [] },
    ],
};

const DASHBOARD: Dashboard = {
    counts: { draft: 0, open: 1, in_contact: 1, closed_offer: 1, closed_rejection: 1, closed_withdrawn: 0 },
    due: [SUMMARY],
    inbox_count: 1,
    suggestion_count: 1,
};

// One integration with an error: the navigation's red dot
const INTEGRATIONS: Integrations = {
    inbound: { state: 'ok', details: { address: 'bewerbungen@example.org', last_mail: '2026-11-07T08:00:00Z' }, warnings: [] },
    reminders: { state: 'error', details: { last_error: 'Resend antwortet nicht' }, warnings: ['Erinnerungen gehen gerade nicht raus'] },
};

const INBOX: InboxItem[] = [
    {
        id: 21,
        message_id: '<1@example.org>',
        from_addr: 'lehre@werkstatt.example',
        to_addrs: 'bewerbungen@example.org',
        subject: 'Einladung zum Schnuppern',
        body_text: 'Guten Tag, wir laden dich gerne ein.',
        received_at: '2026-11-06T10:00:00Z',
        application_id: null,
        parse_error: null,
        attachments: [ATTACHMENT],
        suggestion: { id: 1, company: 'Muster Elektro AG', position: 'Elektroinstallateurin EFZ' },
    },
];

const SUGGESTIONS: Suggestion[] = [
    {
        id: 31,
        url: 'https://lehrstellen.example/123',
        company: 'Werkstatt Beispiel',
        position: 'Polymechanikerin EFZ',
        location: 'Thun',
        deadline: '2026-12-01',
        note: 'Klingt gut',
        status: 'open',
        decline_reason: '',
        source: 'app',
        created_at: '2026-11-01T18:00:00Z',
        created_by_name: 'Papa',
        decided_at: null,
        decided_by_name: null,
        application: null,
        deadline_passed: false,
    },
    {
        id: 32,
        url: 'https://lehrstellen.example/456',
        company: 'Probe Bau AG',
        position: 'Maurerin EFZ',
        location: '',
        deadline: null,
        note: '',
        status: 'declined',
        decline_reason: 'Zu weit weg',
        source: 'mail',
        created_at: '2026-10-15T18:00:00Z',
        created_by_name: null,
        decided_at: '2026-10-16T18:00:00Z',
        decided_by_name: 'Lena',
        application: null,
        deadline_passed: false,
    },
];

const DOCUMENT: AppDocument = {
    id: 41,
    category: 'cv',
    title: 'Lebenslauf',
    issued_on: '2026-09-01',
    note: '',
    outdated: false,
    in_dossier: true,
    position: 0,
    filename: 'lebenslauf.pdf',
    content_type: 'application/pdf',
    size: 120_000,
    created_at: '2026-09-01T10:00:00Z',
    created_by_name: 'Lena',
    dossier_ok: true,
};

const DOCUMENTS: AppDocument[] = [
    DOCUMENT,
    { ...DOCUMENT, id: 42, category: 'report', title: 'Zeugnis 1. Semester', outdated: true, in_dossier: false, position: 1 },
    { ...DOCUMENT, id: 43, category: 'certificate', title: 'Multicheck', filename: 'multicheck.jpg', content_type: 'image/jpeg', dossier_ok: false, in_dossier: false, position: 2 },
];

const DOSSIER: DossierPreview = { parts: [{ id: 41, title: 'Lebenslauf', category: 'cv', pages: 2 }], skipped: [], pages: 2, size: 120_000 };

const SETTINGS: AppSettings = { followup_days: 14, reminder_time: '18:00', inbound_address: 'bewerbungen@example.org' };

const ANSWERS: Record<string, unknown> = {
    '/api/me': LENA,
    '/api/hub': { login_url: 'https://home.local.example.org', logout_url: 'https://home.local.example.org/logout' },
    '/api/dashboard': DASHBOARD,
    '/api/integrations': INTEGRATIONS,
    '/api/applications': APPLICATIONS,
    '/api/applications/1': DETAIL,
    '/api/inbox': INBOX,
    '/api/suggestions': SUGGESTIONS,
    '/api/documents': DOCUMENTS,
    '/api/documents/dossier': DOSSIER,
    '/api/settings': SETTINGS,
    '/api/users': [LENA, { ...LENA, id: 2, name: 'Papa', email: null }],
    '/api/users/removed': [],
};

// Answers the page's API requests: GET from the list above (`overrides` first), every change with 200. A request the
// list doesn't know fails the test, so a page asking for something new is noticed
export async function mockApi(page: Page, overrides: Record<string, (route: Route) => Promise<void>> = {}) {
    const unknown: string[] = [];
    await page.route('**/api/**', async (route) => {
        const request = route.request();
        const { pathname } = new URL(request.url());
        const special = overrides[`${request.method()} ${pathname}`];
        if (special) return special(route);
        if (request.method() !== 'GET') return route.fulfill({ json: {} });
        if (pathname in ANSWERS) return route.fulfill({ json: ANSWERS[pathname] });
        unknown.push(pathname);
        return route.fulfill({ status: 404, json: { detail: 'Not Found' } });
    });
    return unknown;
}
