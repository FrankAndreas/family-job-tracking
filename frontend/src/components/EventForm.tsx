import { useRef, useState, type FormEvent } from 'react';
import api, { errorMessage } from '../api';
import { EVENT_LABELS, EVENT_TYPES } from '../labels';
import { useToast } from '../ToastContext';
import type { EventType } from '../types';
import { BUTTON, BUTTON_SECONDARY, INPUT } from '../ui';

// The current local time in the format of <input type="datetime-local">
function nowForInput(): string {
    const d = new Date();
    d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
    return d.toISOString().slice(0, 16);
}

interface Props {
    applicationId: number;
    defaultType: EventType;
    onSaved: () => void;
}

export default function EventForm({ applicationId, defaultType, onSaved }: Props) {
    const toast = useToast();
    const fileInput = useRef<HTMLInputElement>(null);
    const [open, setOpen] = useState(false);
    const [type, setType] = useState<EventType>(defaultType);
    const [when, setWhen] = useState(nowForInput);
    const [note, setNote] = useState('');
    const [files, setFiles] = useState<File[]>([]);
    const [busy, setBusy] = useState(false);

    const start = () => {
        setType(defaultType);
        setWhen(nowForInput());
        setNote('');
        setFiles([]);
        setOpen(true);
    };

    const submit = async (e: FormEvent) => {
        e.preventDefault();
        setBusy(true);
        const form = new FormData();
        form.append('type', type);
        form.append('occurred_at', new Date(when).toISOString());
        form.append('note', note);
        files.forEach((file) => form.append('files', file));
        try {
            await api.post(`/api/applications/${applicationId}/events`, form);
            setOpen(false);
            onSaved();
        } catch (err) {
            toast(errorMessage(err, 'Speichern fehlgeschlagen'));
        } finally {
            setBusy(false);
        }
    };

    if (!open) {
        return (
            <button type="button" onClick={start} className={BUTTON}>
                + Ereignis
            </button>
        );
    }

    return (
        <form onSubmit={submit} className="space-y-3 rounded-xl border border-slate-700 p-4">
            <div className="grid gap-3 sm:grid-cols-2">
                <label className="block text-sm">
                    <span className="mb-1 block text-slate-400">Was ist passiert?</span>
                    <select value={type} onChange={(e) => setType(e.target.value as EventType)} className={INPUT}>
                        {EVENT_TYPES.map((t) => (
                            <option key={t} value={t}>
                                {EVENT_LABELS[t]}
                            </option>
                        ))}
                    </select>
                </label>
                <label className="block text-sm">
                    <span className="mb-1 block text-slate-400">Wann?</span>
                    <input
                        type="datetime-local"
                        required
                        value={when}
                        onChange={(e) => setWhen(e.target.value)}
                        className={INPUT}
                    />
                </label>
            </div>
            <label className="block text-sm">
                <span className="mb-1 block text-slate-400">Notiz</span>
                <textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} className={INPUT} />
            </label>
            <div className="text-sm">
                <input
                    ref={fileInput}
                    type="file"
                    multiple
                    className="hidden"
                    onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
                />
                <button type="button" onClick={() => fileInput.current?.click()} className={BUTTON_SECONDARY}>
                    Dateien wählen
                </button>
                {files.length > 0 && <span className="ml-2 text-slate-400">{files.map((f) => f.name).join(', ')}</span>}
            </div>
            <div className="flex gap-2">
                <button type="submit" disabled={busy} className={BUTTON}>
                    Speichern
                </button>
                <button type="button" onClick={() => setOpen(false)} className={BUTTON_SECONDARY}>
                    Abbrechen
                </button>
            </div>
        </form>
    );
}
