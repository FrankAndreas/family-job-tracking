import axios from 'axios';

// Same origin: Vite (dev) or nginx (Docker) forwards /api to the backend
const api = axios.create();

api.interceptors.request.use((config) => {
    const token = localStorage.getItem('token');
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

// Expired or invalid token: drop it and go back to the login page
api.interceptors.response.use(
    (response) => response,
    (error) => {
        const isLogin = error.config?.url === '/api/token';
        if (error.response?.status === 401 && !isLogin && localStorage.getItem('token')) {
            localStorage.removeItem('token');
            window.location.href = '/login';
        }
        return Promise.reject(error);
    },
);

// Turn an API error into a message for the user (FastAPI sends `detail` as text or a list of validation errors)
export function errorMessage(error: unknown, fallback = 'Etwas ist schiefgelaufen'): string {
    if (!axios.isAxiosError(error)) return fallback;
    const detail = error.response?.data?.detail;
    if (typeof detail === 'string') return detail;
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
