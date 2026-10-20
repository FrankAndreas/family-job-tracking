import { useState } from 'react';
import api, { downloadFile, errorMessage, openFile } from '../api';
import { CATEGORY_LABELS, CATEGORY_ORDER, formatDate, formatSize } from '../labels';
import { useToast } from '../ToastContext';
import type { AppDocument, DocumentCategory } from '../types';
import { BUTTON, BUTTON_DANGER, BUTTON_SECONDARY, INPUT } from '../ui';

const SMALL = 'rounded border border-slate-600 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800 disabled:opacity-40';

interface Props {
    doc: AppDocument;
    first: boolean;
    last: boolean;
    onChanged: () => void;
}

export default function DocumentRow({ doc, first, last, onChanged }: Props) {
    const toast = useToast();
    const [busy, setBusy] = useState(false);
    const [editing, setEditing] = useState(false);
    const [title, setTitle] = useState(doc.title);
    const [category, setCategory] = useState<DocumentCategory>(doc.category);
    const [issuedOn, setIssuedOn] = useState(doc.issued_on ?? '');
    const [note, setNote] = useState(doc.note);

    const run = async (action: () => Promise<unknown>) => {
        setBusy(true);
        try {
            await action();
            onChanged();
        } catch (e) {
            toast(errorMessage(e));
        } finally {
            setBusy(false);
        }
    };

    const patch = (body: Partial<Omit<AppDocument, 'issued_on'>> & { issued_on?: string | null }) =>
        run(() => api.patch(`/api/documents/${doc.id}`, body));
    const move = (direction: 'up' | 'down') => run(() => api.post(`/api/documents/${doc.id}/move`, { direction }));
    const remove = () => {
        if (!window.confirm(`„${doc.title}“ löschen?`)) return;
        run(() => api.delete(`/api/documents/${doc.id}`));
    };
    // Start from the document as it is now, not from an earlier, abandoned edit
    const startEdit = () => {
        setTitle(doc.title);
        setCategory(doc.category);
        setIssuedOn(doc.issued_on ?? '');
        setNote(doc.note);
        setEditing(true);
    };

    const save = () =>
        run(async () => {
            await api.patch(`/api/documents/${doc.id}`, { title, category, issued_on: issuedOn || null, note });
            setEditing(false);
        });

    if (editing) {
        return (
            <li className="space-y-2 rounded-lg border border-slate-700 p-3">
                <div className="grid gap-2 sm:grid-cols-3">
                    <input value={title} onChange={(e) => setTitle(e.target.value)} className={INPUT} />
                    <select
                        value={category}
                        onChange={(e) => setCategory(e.target.value as DocumentCategory)}
                        className={INPUT}
                    >
                        {CATEGORY_ORDER.map((c) => (
                            <option key={c} value={c}>
                                {CATEGORY_LABELS[c]}
                            </option>
                        ))}
                    </select>
                    <input type="date" value={issuedOn} onChange={(e) => setIssuedOn(e.target.value)} className={INPUT} />
                </div>
                <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} className={INPUT} />
                <div className="flex gap-2">
                    <button type="button" className={BUTTON} disabled={busy} onClick={save}>
                        Speichern
                    </button>
                    <button type="button" className={BUTTON_SECONDARY} onClick={() => setEditing(false)}>
                        Abbrechen
                    </button>
                </div>
            </li>
        );
    }

    return (
        <li className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-slate-800 p-3">
            <label className="flex items-center gap-1 text-xs text-slate-400">
                <input
                    type="checkbox"
                    checked={doc.in_dossier}
                    // A file that can't go into the dossier can still be unticked, never ticked
                    disabled={busy || (!doc.dossier_ok && !doc.in_dossier)}
                    onChange={(e) => patch({ in_dossier: e.target.checked })}
                />
                Im Dossier
            </label>
            <div className="min-w-0 flex-1">
                <div className={`truncate font-semibold ${doc.outdated ? 'text-slate-500' : ''}`}>{doc.title}</div>
                <div className="text-xs text-slate-500">
                    {doc.issued_on ? formatDate(doc.issued_on) : 'ohne Datum'} · {formatSize(doc.size)} ·{' '}
                    {doc.created_by_name ?? 'unbekannt'}
                    {!doc.dossier_ok && ' · nicht im Dossier möglich (bitte als PDF hochladen)'}
                </div>
                {doc.note && <div className="whitespace-pre-wrap text-xs text-slate-400">{doc.note}</div>}
            </div>
            <div className="flex flex-wrap gap-1">
                <button type="button" className={SMALL} disabled={busy || first} onClick={() => move('up')} title="Nach oben">
                    ↑
                </button>
                <button type="button" className={SMALL} disabled={busy || last} onClick={() => move('down')} title="Nach unten">
                    ↓
                </button>
                <button
                    type="button"
                    className={SMALL}
                    onClick={() => openFile(`/api/documents/${doc.id}/file`).catch((e) => toast(errorMessage(e)))}
                >
                    Öffnen
                </button>
                <button
                    type="button"
                    className={SMALL}
                    onClick={() =>
                        downloadFile(`/api/documents/${doc.id}/file`, doc.filename).catch((e) => toast(errorMessage(e)))
                    }
                >
                    Herunterladen
                </button>
                <button type="button" className={SMALL} onClick={startEdit}>
                    Bearbeiten
                </button>
                <button type="button" className={SMALL} disabled={busy} onClick={() => patch({ outdated: !doc.outdated })}>
                    {doc.outdated ? 'Aktuell' : 'Veraltet'}
                </button>
                <button type="button" className={`${BUTTON_DANGER} px-2 py-1 text-xs`} disabled={busy} onClick={remove}>
                    Löschen
                </button>
            </div>
        </li>
    );
}
