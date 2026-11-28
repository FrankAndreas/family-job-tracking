import type { Channel, DocumentCategory, EventType, Status } from './types';

export const STATUS_LABELS: Record<Status, string> = {
    draft: 'Entwurf',
    open: 'Offen',
    in_contact: 'In Kontakt',
    closed_offer: 'Zusage',
    closed_rejection: 'Absage',
    closed_withdrawn: 'Zurückgezogen',
};

// Fill and text together, 4.5:1 or more (accessibility review 2026-11-08): the theme's state colours are light, so
// the text on them is the page's dark colour (themes 2026-11-28)
export const STATUS_COLORS: Record<Status, string> = {
    draft: 'bg-pressed text-ink',
    open: 'bg-accent text-page',
    in_contact: 'bg-warning text-page',
    closed_offer: 'bg-success text-page',
    closed_rejection: 'bg-danger text-page',
    closed_withdrawn: 'bg-pressed text-ink',
};

export const EVENT_LABELS: Record<EventType, string> = {
    sent: 'Bewerbung gesendet',
    followed_up: 'Nachgefragt',
    reply_received: 'Antwort erhalten',
    mail_sent: 'Mail gesendet',
    mail_received: 'Mail erhalten',
    call: 'Telefonat',
    interview: 'Vorstellungsgespräch',
    trial: 'Schnupperlehre/Probetag',
    offer: 'Zusage',
    rejection: 'Absage',
    no_position: 'Keine Lehrstelle angeboten',
    position_filled: 'Bereits vergeben',
    withdrawn: 'Zurückgezogen',
    note: 'Notiz',
};

export const EVENT_TYPES = Object.keys(EVENT_LABELS) as EventType[];

// Events whose note is the reason, and how the status names each kind of rejection
export const REASON_EVENTS: EventType[] = ['rejection', 'no_position', 'position_filled', 'withdrawn'];
export const REJECTION_LABELS: Partial<Record<EventType, string>> = {
    rejection: 'Absage',
    no_position: 'Keine Lehrstelle',
    position_filled: 'Vergeben',
};

export const CHANNEL_LABELS: Record<Channel, string> = {
    email: 'E-Mail',
    portal: 'Portal',
    post: 'Post',
    in_person: 'Persönlich',
    other: 'Andere',
};

export function formatDate(iso: string | null): string {
    return iso ? new Date(iso).toLocaleDateString('de-CH') : '–';
}

export function formatDateTime(iso: string | null): string {
    return iso ? new Date(iso).toLocaleString('de-CH', { dateStyle: 'medium', timeStyle: 'short' }) : '–';
}

export function formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

// Dossier order
export const CATEGORY_ORDER: DocumentCategory[] = ['letter', 'cv', 'report', 'certificate', 'other'];

export const CATEGORY_LABELS: Record<DocumentCategory, string> = {
    letter: 'Motivationsschreiben',
    cv: 'Lebenslauf',
    report: 'Zeugnis',
    certificate: 'Zertifikat/Test',
    other: 'Andere',
};
