export type Status = 'draft' | 'open' | 'in_contact' | 'closed_offer' | 'closed_rejection' | 'closed_withdrawn';
export type EventType =
    | 'sent' | 'followed_up' | 'reply_received' | 'mail_sent' | 'mail_received' | 'call'
    | 'interview' | 'trial' | 'offer' | 'rejection' | 'no_position' | 'position_filled' | 'withdrawn' | 'note';
export type Channel = 'email' | 'portal' | 'post' | 'in_person' | 'other';

export interface User {
    id: number;
    name: string;
    is_admin: boolean;
    email: string | null;
    wants_reminders: boolean;
}

export interface Attachment {
    id: number;
    filename: string;
    content_type: string;
    size: number;
    path: string;
}

export interface EmailItem {
    id: number;
    message_id: string;
    from_addr: string;
    to_addrs: string;
    subject: string;
    body_text: string;
    received_at: string;
    application_id: number | null;
    parse_error: string | null;
    attachments: Attachment[];
}

export interface TimelineEvent {
    id: number;
    occurred_at: string;
    type: EventType;
    note: string;
    created_by_name: string | null;
    email: EmailItem | null;
    attachments: Attachment[];
}

export interface ApplicationSummary {
    id: number;
    company: string;
    position: string;
    location: string;
    status: Status;
    // The event that closed it (e.g. 'position_filled' for closed_rejection) and its note as the reason
    closed_by: EventType | null;
    closed_note: string | null;
    archived: boolean;
    due: boolean;
    last_event_type: EventType | null;
    last_event_at: string | null;
    days_since_last: number | null;
    mail_tag: string;
}

export interface ApplicationFormValues {
    company: string;
    position: string;
    location: string;
    contact_name: string;
    contact_email: string;
    contact_phone: string;
    posting_url: string;
    channel: Channel;
    notes: string;
}

export interface ApplicationDetail extends ApplicationSummary, ApplicationFormValues {
    created_at: string;
    created_by_name: string | null;
    mail_address: string | null;
    events: TimelineEvent[];
}

export interface Dashboard {
    counts: Record<Status, number>;
    due: ApplicationSummary[];
    inbox_count: number;
    suggestion_count: number;
}

export interface InboxItem extends EmailItem {
    suggestion: { id: number; company: string; position: string } | null;
}

export interface AppSettings {
    followup_days: number;
    reminder_time: string;
    inbound_address: string;
}

export type IntegrationState = 'not_configured' | 'waiting' | 'ok' | 'error';

export interface Integration {
    state: IntegrationState;
    details: Record<string, string | number | string[] | null>;
    warnings: string[];
}

export interface Integrations {
    inbound: Integration;
    reminders: Integration;
}

// Passed by Layout to its pages through the router outlet
export interface LayoutContext {
    // Pages that know the inbox count better than the last navigation update the badge with it
    setInboxCount: (count: number) => void;
    setSuggestionCount: (count: number) => void;
}

export type SuggestionStatus = 'open' | 'applied' | 'declined';

export interface SuggestionFormValues {
    url: string;
    company: string;
    position: string;
    location: string;
    deadline: string; // YYYY-MM-DD or '' for none
    note: string;
}

export interface Suggestion extends Omit<SuggestionFormValues, 'deadline'> {
    id: number;
    deadline: string | null;
    status: SuggestionStatus;
    decline_reason: string;
    source: 'app' | 'mail';
    created_at: string;
    created_by_name: string | null;
    decided_at: string | null;
    decided_by_name: string | null;
    application: { id: number; company: string; position: string } | null;
    deadline_passed: boolean;
}

export interface SuggestionDuplicate {
    kind: 'suggestion' | 'application';
    id: number;
    label: string;
    date: string;
    status?: SuggestionStatus;
}

export interface SuggestionCheck {
    duplicates: SuggestionDuplicate[];
    title: string | null;
}

export type DocumentCategory = 'letter' | 'cv' | 'report' | 'certificate' | 'other';

export interface AppDocument {
    id: number;
    category: DocumentCategory;
    title: string;
    issued_on: string | null;
    note: string;
    outdated: boolean;
    in_dossier: boolean;
    position: number;
    filename: string;
    content_type: string;
    size: number;
    created_at: string;
    created_by_name: string | null;
    dossier_ok: boolean;
}

export interface DossierPreview {
    parts: { id: number; title: string; category: DocumentCategory; pages: number }[];
    skipped: { id: number; title: string; reason: string }[];
    pages: number;
    size: number;
}
