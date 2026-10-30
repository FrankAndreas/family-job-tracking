import axios from 'axios';

// Same origin: Vite (dev) or nginx (Docker) forwards /api to the backend, and the login is the family hub's cookie
// (spec 2026-10-30), which the browser sends by itself. The backend takes changes made with the cookie only with this
// header: another site can make a browser send the cookie, but not the header
const api = axios.create({ withCredentials: true, headers: { 'X-Requested-With': 'jobs' } });

// The login ended (logged out in the hub, a new PIN): log in at the family hub, which sends the browser back here
api.interceptors.response.use(
    (response) => response,
    (error) => {
        if (axios.isAxiosError(error) && error.response?.status === 401 && !error.config?.url?.endsWith('/api/hub')) {
            void goToHub();
        }
        return Promise.reject(error);
    },
);

// Where the family hub is (HUB_PUBLIC_URL), and where "Abmelden" goes (at home the hub, outside Cloudflare Access)
async function hubLinks(): Promise<{ login_url: string; logout_url: string }> {
    return (await api.get<{ login_url: string; logout_url: string }>('/api/hub')).data;
}

async function hubUrl(): Promise<string> {
    return (await hubLinks()).login_url;
}

// To the hub's login; with next=, the hub sends the browser back here afterwards
export async function goToHub(next: string | null = window.location.href): Promise<void> {
    const login = await hubUrl();
    window.location.href = next ? `${login}/?next=${encodeURIComponent(next)}` : login;
}

// "Abmelden": the hub ends the login, for this app and every other family app, then shows its login (back here after)
export async function goToHubLogout(): Promise<void> {
    const { logout_url } = await hubLinks();
    // Outside, Cloudflare's logout (an address on this site) ends the e-mail-code login; at home the hub's page does,
    // and leads back here after the next login
    window.location.href = logout_url.startsWith('/')
        ? logout_url
        : `${logout_url}?next=${encodeURIComponent(window.location.origin)}`;
}

// The code of an error the app acts on (no_access, hub_unavailable)
export function errorCode(error: unknown): string | undefined {
    const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
    return typeof detail === 'string' ? detail : undefined;
}

// What the backend's codes (since the family hub) mean, in words
const CODES: Record<string, string> = {
    not_logged_in: 'Du bist nicht mehr angemeldet.',
    no_access: 'Du hast keinen Zugang zu dieser App. Ein Elternteil kann ihn im Familien-Hub geben.',
    hub_unavailable: 'Der Familien-Hub ist gerade nicht erreichbar. Versuche es gleich nochmals.',
    csrf: 'Diese Änderung kam nicht von der App selbst. Lade die Seite neu.',
    admins_only: 'Das dürfen nur Admins (Eltern im Familien-Hub).',
    from_hub: 'Name und Admin kommen aus dem Familien-Hub: dort ändern.',
    still_in_hub: 'Entferne zuerst den Zugang der Person im Familien-Hub.',
};

// Turn an API error into a message for the user (FastAPI sends `detail` as text or a list of validation errors)
export function errorMessage(error: unknown, fallback = 'Etwas ist schiefgelaufen'): string {
    if (!axios.isAxiosError(error)) return fallback;
    const detail = error.response?.data?.detail;
    if (typeof detail === 'string') return CODES[detail] ?? detail;
    if (Array.isArray(detail) && detail.length > 0) return detail.map((d: { msg: string }) => d.msg).join('; ');
    return fallback;
}

// Files need the login token, so fetch them with axios and hand the browser a temporary link
export async function downloadFile(url: string, filename: string): Promise<void> {
    const response = await api.get<Blob>(url, { responseType: 'blob' });
    const href = URL.createObjectURL(response.data);
    const link = document.createElement('a');
    link.href = href;
    link.download = filename;
    link.click();
    setTimeout(() => URL.revokeObjectURL(href), 1000);
}

// Open a file that needs the login token in a new tab; the tab is opened first, so popup blockers allow it
export async function openFile(url: string): Promise<void> {
    const tab = window.open('', '_blank');
    try {
        const response = await api.get<Blob>(url, { responseType: 'blob' });
        const href = URL.createObjectURL(response.data);
        if (tab) tab.location.href = href;
        else window.location.href = href;
        setTimeout(() => URL.revokeObjectURL(href), 60_000);
    } catch (error) {
        tab?.close();
        throw error;
    }
}

export default api;
