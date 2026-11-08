import type { ApplicationFormValues } from './types';

// Shared Tailwind classes, so forms and cards look the same everywhere. Contrast (accessibility review 2026-11-08):
// a field's outline 3:1 or more (slate-500; slate-600 gave 2.4), white on the button 4.5:1 or more, also on hover
export const FIELD =
    'rounded-lg border border-slate-500 bg-slate-800/60 p-2 text-slate-100 focus:border-blue-400 focus:outline-none';
export const INPUT = `${FIELD} w-full`;
export const BUTTON =
    'rounded-lg bg-blue-600 px-4 py-2 font-semibold text-white hover:bg-blue-700 disabled:opacity-50';
export const BUTTON_SECONDARY =
    'rounded-lg border border-slate-600 px-4 py-2 text-slate-200 hover:bg-slate-800 disabled:opacity-50';
export const BUTTON_DANGER =
    'rounded-lg border border-red-700 px-4 py-2 text-red-300 hover:bg-red-900/40 disabled:opacity-50';
export const CARD = 'rounded-xl border border-slate-800 bg-slate-900/60 p-4';

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
