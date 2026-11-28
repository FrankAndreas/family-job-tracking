import type { ApplicationFormValues } from './types';

// Shared Tailwind classes, so forms and cards look the same everywhere: the family look (family-hub-theme), as in the
// hub. Contrast (accessibility review 2026-11-08): a field's outline 3:1 or more (line-strong), the primary button's
// white text 6.3:1 on its gradient
export const FIELD =
    'rounded-control border border-line-strong bg-field p-2 text-ink focus:border-accent focus:outline-none';
export const INPUT = `${FIELD} w-full`;
export const BUTTON = 'btn-primary';
export const BUTTON_SECONDARY =
    'rounded-control border border-line px-4 py-2 text-ink hover:bg-hover disabled:opacity-50';
export const BUTTON_DANGER =
    'rounded-control border border-danger/40 px-4 py-2 text-danger hover:bg-danger/15 disabled:opacity-50';
export const CARD = 'glass-card p-4';

export const EMPTY_APPLICATION: ApplicationFormValues = {
    company: '',
    position: '',
    location: '',
    contact_name: '',
    contact_email: '',
    contact_phone: '',
    posting_url: '',
    channel: 'email',
    notes: '',
};
