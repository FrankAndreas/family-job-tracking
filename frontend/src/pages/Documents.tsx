import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import api, { downloadFile, errorMessage } from '../api';
import DocumentRow from '../components/DocumentRow';
import { CATEGORY_LABELS, CATEGORY_ORDER, formatSize } from '../labels';
import { useToast } from '../ToastContext';
import type { AppDocument, DocumentCategory, DossierPreview } from '../types';
import { BUTTON, CARD, INPUT } from '../ui';

function stem(filename: string): string {
    const dot = filename.lastIndexOf('.');
    return dot > 0 ? filename.slice(0, dot) : filename;
}

export default function Documents() {
    const toast = useToast();
    const [docs, setDocs] = useState<AppDocument[] | null>(null);
    const [preview, setPreview] = useState<DossierPreview | null>(null);
    const [file, setFile] = useState<File | null>(null);
    const [category, setCategory] = useState<DocumentCategory>('report');
    const [title, setTitle] = useState('');
    const [issuedOn, setIssuedOn] = useState('');
    const [note, setNote] = useState('');
    const [uploading, setUploading] = useState(false);
    const [building, setBuilding] = useState(false);
    const [openOutdated, setOpenOutdated] = useState<Record<string, boolean>>({});
    const fileInput = useRef<HTMLInputElement>(null);

    const [version, setVersion] = useState(0);
    const load = useCallback(() => setVersion((v) => v + 1), []);

    useEffect(() => {
        Promise.all([api.get<AppDocument[]>('/api/documents'), api.get<DossierPreview>('/api/documents/dossier')])
            .then(([list, dossier]) => {
                setDocs(list.data);
                setPreview(dossier.data);
            })
            .catch((e) => toast(errorMessage(e)));
    }, [version, toast]);

    const submit = async (event: FormEvent) => {
        event.preventDefault();
        if (!file) return;
        setUploading(true);
        const form = new FormData();
        form.append('file', file);
        form.append('category', category);
        form.append('title', title);
        form.append('issued_on', issuedOn);
        form.append('note', note);
        try {
            await api.post('/api/documents', form);
            toast('Unterlage hochgeladen', 'success');
            setFile(null);
            setTitle('');
            setIssuedOn('');
            setNote('');
            if (fileInput.current) fileInput.current.value = '';
            load();
        } catch (e) {
            toast(errorMessage(e));
        } finally {
            setUploading(false);
        }
    };

    const download = async () => {
        setBuilding(true);
        try {
            const today = new Date().toISOString().slice(0, 10);
            await downloadFile('/api/documents/dossier.pdf', `Bewerbungsdossier_${today}.pdf`);
        } catch (e) {
            toast(errorMessage(e, 'Dossier konnte nicht erstellt werden'));
        } finally {
            setBuilding(false);
        }
    };

    if (docs === null) return <p className="text-slate-400">Laden…</p>;

    return (
        <div className="space-y-4">
            <h1 className="text-2xl font-bold">Unterlagen</h1>

            <form onSubmit={submit} className={`${CARD} space-y-3`}>
                <h2 className="font-semibold">Unterlage hochladen</h2>
                <input
                    ref={fileInput}
                    type="file"
                    accept="application/pdf,image/*,.heic,.heif"
                    required
                    onChange={(e) => {
                        const chosen = e.target.files?.[0] ?? null;
                        setFile(chosen);
                        if (chosen && !title) setTitle(stem(chosen.name));
                    }}
                    className="block w-full text-sm text-slate-300"
                />
                <div className="grid gap-3 sm:grid-cols-3">
                    <label className="block text-sm">
                        <span className="mb-1 block text-slate-400">Kategorie</span>
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
                    </label>
                    <label className="block text-sm">
                        <span className="mb-1 block text-slate-400">Titel</span>
                        <input value={title} onChange={(e) => setTitle(e.target.value)} className={INPUT} />
                    </label>
                    <label className="block text-sm">
                        <span className="mb-1 block text-slate-400">Datum</span>
                        <input type="date" value={issuedOn} onChange={(e) => setIssuedOn(e.target.value)} className={INPUT} />
                    </label>
                </div>
                <label className="block text-sm">
                    <span className="mb-1 block text-slate-400">Notiz</span>
                    <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} className={INPUT} />
                </label>
                <button type="submit" className={BUTTON} disabled={uploading || !file}>
                    {uploading ? 'Lädt hoch…' : 'Hochladen'}
                </button>
            </form>

            <section className={`${CARD} space-y-2`}>
                <div className="flex flex-wrap items-center gap-3">
                    <h2 className="mr-auto font-semibold">Bewerbungsdossier</h2>
                    <button type="button" className={BUTTON} disabled={building || !preview?.pages} onClick={download}>
                        {building ? 'Wird erstellt…' : 'Dossier als PDF'}
                    </button>
                </div>
                {preview && preview.pages > 0 ? (
                    <>
                        <ol className="list-decimal pl-5 text-sm text-slate-300">
                            {preview.parts.map((p) => (
                                <li key={p.id}>
                                    {p.title} <span className="text-slate-500">({p.pages} S.)</span>
                                </li>
                            ))}
                        </ol>
                        <p className="text-xs text-slate-500">
                            {preview.pages} Seiten · etwa {formatSize(preview.size)}
                        </p>
                    </>
                ) : (
                    <p className="text-sm text-slate-400">Noch keine Unterlage im Dossier.</p>
                )}
                {preview && preview.skipped.length > 0 && (
                    <ul className="text-xs text-amber-300">
                        {preview.skipped.map((s) => (
                            <li key={s.id}>
                                Nicht im Dossier: {s.title} ({s.reason})
                            </li>
                        ))}
                    </ul>
                )}
            </section>

            {CATEGORY_ORDER.map((c) => {
                const inCategory = docs.filter((d) => d.category === c);
                if (inCategory.length === 0) return null;
                const current = inCategory.filter((d) => !d.outdated);
                const outdated = inCategory.filter((d) => d.outdated);
                return (
                    <section key={c} className="space-y-2">
                        <h2 className="text-lg font-semibold">
                            {CATEGORY_LABELS[c]} <span className="text-sm text-slate-500">({inCategory.length})</span>
                        </h2>
                        <ul className="space-y-2">
                            {current.map((d) => (
                                <DocumentRow
                                    key={d.id}
                                    doc={d}
                                    first={inCategory[0].id === d.id}
                                    last={inCategory[inCategory.length - 1].id === d.id}
                                    onChanged={load}
                                />
                            ))}
                        </ul>
                        {outdated.length > 0 && (
                            <div className="space-y-2">
                                <button
                                    type="button"
                                    className="text-sm text-slate-400 hover:text-white"
                                    onClick={() => setOpenOutdated((o) => ({ ...o, [c]: !o[c] }))}
                                >
                                    {openOutdated[c] ? '▾' : '▸'} Veraltet ({outdated.length})
                                </button>
                                {openOutdated[c] && (
                                    <ul className="space-y-2">
                                        {outdated.map((d) => (
                                            <DocumentRow
                                                key={d.id}
                                                doc={d}
                                                first={inCategory[0].id === d.id}
                                                last={inCategory[inCategory.length - 1].id === d.id}
                                                onChanged={load}
                                            />
                                        ))}
                                    </ul>
                                )}
                            </div>
                        )}
                    </section>
                );
            })}
        </div>
    );
}
