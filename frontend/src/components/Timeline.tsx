import { useState } from 'react';
import api, { downloadFile, errorMessage } from '../api';
import { EVENT_LABELS, EVENT_TYPES, REASON_EVENTS, formatDateTime, formatSize } from '../labels';
import { useToast } from '../ToastContext';
import type { Attachment, EventType, TimelineEvent } from '../types';
import { INPUT } from '../ui';

function AttachmentList({ attachments, onDelete }: { attachments: Attachment[]; onDelete: (a: Attachment) => void }) {
    const toast = useToast();
    if (attachments.length === 0) return null;
    return (
        <ul className="mt-2 space-y-1 text-sm">
            {attachments.map((a) => (
                <li key={a.id} className="flex items-center gap-2">
                    <button
                        type="button"
                        className="truncate text-blue-300 hover:underline"
                        onClick={() =>
                            downloadFile(`/api/attachments/${a.id}`, a.filename).catch((e) =>
                                toast(errorMessage(e, 'Download fehlgeschlagen')),
                            )
                        }
                    >
                        📎 {a.filename}
                    </button>
                    <span className="text-xs text-slate-500">{formatSize(a.size)}</span>
                    <button
                        type="button"
                        onClick={() => onDelete(a)}
                        aria-label={`${a.filename} löschen`}
                        className="text-xs text-slate-500 hover:text-red-400"
                    >
                        ✕
                    </button>
                </li>
            ))}
        </ul>
    );
}

function TimelineItem({ event, onChanged }: { event: TimelineEvent; onChanged: () => void }) {
    const toast = useToast();
    const [busy, setBusy] = useState(false);
    const email = event.email;

    const run = async (action: () => Promise<unknown>) => {
        setBusy(true);
        try {
            await action();
            onChanged();
        } catch (e) {
            toast(errorMessage(e, 'Speichern fehlgeschlagen'));
        } finally {
            setBusy(false);
        }
    };
    const deleteEvent = () => {
        const question = email
            ? 'Dieses Ereignis löschen? Die Mail kommt zurück in den Posteingang.'
            : 'Dieses Ereignis löschen?';
        if (window.confirm(question)) run(() => api.delete(`/api/events/${event.id}`));
    };
    const [editing, setEditing] = useState(false);
    const [type, setType] = useState<EventType>(event.type);
    const [note, setNote] = useState(event.note);
    const startEdit = () => {
        setType(event.type);
        setNote(event.note);
        setEditing(true);
    };
    const save = () =>
        run(async () => {
            await api.patch(`/api/events/${event.id}`, { type, note });
            setEditing(false);
        });
    const deleteAttachment = (a: Attachment) => {
        if (window.confirm(`${a.filename} löschen?`)) run(() => api.delete(`/api/attachments/${a.id}`));
    };

    return (
        <li className="relative border-l-2 border-slate-700 pb-5 pl-4">
            <span className="absolute -left-[7px] top-1.5 h-3 w-3 rounded-full bg-blue-500" />
            <div className="flex flex-wrap items-baseline gap-x-2">
                <span className="font-semibold">{EVENT_LABELS[event.type]}</span>
                <span className="text-sm text-slate-400">{formatDateTime(event.occurred_at)}</span>
                <span className="text-xs text-slate-500">
                    {event.created_by_name ? `von ${event.created_by_name}` : email ? 'per E-Mail' : ''}
                </span>
                <button
                    type="button"
                    disabled={busy}
                    onClick={startEdit}
                    className="ml-auto text-xs text-slate-500 hover:text-blue-300"
                >
                    bearbeiten
                </button>
                <button
                    type="button"
                    disabled={busy}
                    onClick={deleteEvent}
                    className="text-xs text-slate-500 hover:text-red-400"
                >
                    löschen
                </button>
            </div>
            {editing ? (
                <div className="mt-2 space-y-2">
                    <select value={type} onChange={(e) => setType(e.target.value as EventType)} className={INPUT}>
                        {EVENT_TYPES.map((t) => (
                            <option key={t} value={t}>
                                {EVENT_LABELS[t]}
                            </option>
                        ))}
                    </select>
                    <textarea
                        rows={2}
                        value={note}
                        onChange={(e) => setNote(e.target.value)}
                        placeholder={REASON_EVENTS.includes(type) ? 'Grund' : 'Notiz'}
                        className={INPUT}
                    />
                    <div className="flex gap-3 text-sm">
                        <button type="button" disabled={busy} onClick={save} className="text-blue-300 hover:underline">
                            Speichern
                        </button>
                        <button type="button" onClick={() => setEditing(false)} className="text-slate-400 hover:underline">
                            Abbrechen
                        </button>
                    </div>
                </div>
            ) : (
                event.note && <p className="mt-1 whitespace-pre-wrap text-sm">{event.note}</p>
            )}
            <AttachmentList attachments={event.attachments} onDelete={deleteAttachment} />
            {email && (
                <details className="mt-2 rounded-lg bg-slate-800/50 p-2 text-sm">
                    <summary className="cursor-pointer text-slate-300">Mail anzeigen</summary>
                    <div className="mt-2 space-y-1 text-xs text-slate-400">
                        <div>Von: {email.from_addr || '–'}</div>
                        <div>An: {email.to_addrs || '–'}</div>
                    </div>
                    <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap font-sans text-sm">{email.body_text}</pre>
                    <AttachmentList attachments={email.attachments} onDelete={deleteAttachment} />
                    <button
                        type="button"
                        className="mt-2 text-xs text-blue-300 hover:underline"
                        onClick={() =>
                            downloadFile(`/api/emails/${email.id}/raw`, `mail-${email.id}.eml`).catch((e) =>
                                toast(errorMessage(e, 'Download fehlgeschlagen')),
                            )
                        }
                    >
                        Originalmail (.eml) herunterladen
                    </button>
                </details>
            )}
        </li>
    );
}

export default function Timeline({ events, onChanged }: { events: TimelineEvent[]; onChanged: () => void }) {
    if (events.length === 0) return <p className="text-slate-400">Noch keine Ereignisse.</p>;
    return (
        <ol className="ml-2">
            {events.map((event) => (
                <TimelineItem key={event.id} event={event} onChanged={onChanged} />
            ))}
        </ol>
    );
}
