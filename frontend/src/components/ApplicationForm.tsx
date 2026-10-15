import { useState, type FormEvent } from 'react';
import { errorMessage } from '../api';
import { CHANNEL_LABELS } from '../labels';
import { useToast } from '../ToastContext';
import type { ApplicationFormValues, Channel } from '../types';
import { BUTTON, BUTTON_SECONDARY, INPUT } from '../ui';

type TextField = Exclude<keyof ApplicationFormValues, 'channel' | 'notes'>;

const FIELDS: [TextField, string, string][] = [
    ['company', 'Firma *', 'text'],
    ['position', 'Stelle', 'text'],
    ['location', 'Ort', 'text'],
    ['contact_name', 'Ansprechperson', 'text'],
    ['contact_email', 'E-Mail der Ansprechperson', 'email'],
    ['contact_phone', 'Telefon', 'tel'],
    ['posting_url', 'Link zum Inserat', 'url'],
];

interface Props {
    initial: ApplicationFormValues;
    submitLabel: string;
    onSubmit: (values: ApplicationFormValues) => Promise<void>;
    onCancel: () => void;
}

export default function ApplicationForm({ initial, submitLabel, onSubmit, onCancel }: Props) {
    const toast = useToast();
    const [values, setValues] = useState(initial);
    const [busy, setBusy] = useState(false);

    const set = (key: keyof ApplicationFormValues, value: string) => setValues({ ...values, [key]: value });

    const submit = async (e: FormEvent) => {
        e.preventDefault();
        setBusy(true);
        try {
            await onSubmit(values);
        } catch (err) {
            toast(errorMessage(err, 'Speichern fehlgeschlagen'));
        } finally {
            setBusy(false);
        }
    };

    return (
        <form onSubmit={submit} className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2">
                {FIELDS.map(([key, label, type]) => (
                    <label key={key} className="block text-sm">
                        <span className="mb-1 block text-slate-400">{label}</span>
                        <input
                            type={type}
                            required={key === 'company'}
                            value={values[key]}
                            onChange={(e) => set(key, e.target.value)}
                            className={INPUT}
                        />
                    </label>
                ))}
                <label className="block text-sm">
                    <span className="mb-1 block text-slate-400">Kanal</span>
                    <select
                        value={values.channel}
                        onChange={(e) => set('channel', e.target.value as Channel)}
                        className={INPUT}
                    >
                        {Object.entries(CHANNEL_LABELS).map(([value, label]) => (
                            <option key={value} value={value}>
                                {label}
                            </option>
                        ))}
                    </select>
                </label>
            </div>
            <label className="block text-sm">
                <span className="mb-1 block text-slate-400">Notizen</span>
                <textarea rows={3} value={values.notes} onChange={(e) => set('notes', e.target.value)} className={INPUT} />
            </label>
            <div className="flex gap-2">
                <button type="submit" disabled={busy} className={BUTTON}>
                    {submitLabel}
                </button>
                <button type="button" onClick={onCancel} className={BUTTON_SECONDARY}>
                    Abbrechen
                </button>
            </div>
        </form>
    );
}
