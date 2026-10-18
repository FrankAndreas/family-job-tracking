import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { useOutletContext } from 'react-router-dom';
import api, { errorMessage } from '../api';
import SuggestionCard from '../components/SuggestionCard';
import { formatDate } from '../labels';
import { useToast } from '../ToastContext';
import type { AppSettings, LayoutContext, Suggestion, SuggestionCheck, SuggestionFormValues } from '../types';
import { BUTTON, BUTTON_SECONDARY, CARD, INPUT } from '../ui';

const EMPTY: SuggestionFormValues = { url: '', company: '', position: '', location: '', deadline: '', note: '' };

// "www.yousty.ch/..." -> "https://www.yousty.ch/...": people paste links without the scheme
function withScheme(url: string): string {
    const trimmed = url.trim();
    return !trimmed || /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
}

// Open ones by deadline (soonest first), those without one after them, newest first
function byDeadline(a: Suggestion, b: Suggestion): number {
    if (a.deadline && b.deadline) return a.deadline.localeCompare(b.deadline);
    if (a.deadline) return -1;
    if (b.deadline) return 1;
    return b.created_at.localeCompare(a.created_at);
}

function mailAddress(inbound: string): string | null {
    const [local, domain] = inbound.split('@');
    return local && domain ? `${local}+vorschlag@${domain}` : null;
}

export default function Suggestions() {
    const toast = useToast();
    const { setSuggestionCount } = useOutletContext<LayoutContext>();
    const [items, setItems] = useState<Suggestion[] | null>(null);
    const [address, setAddress] = useState<string | null>(null);
    const [values, setValues] = useState<SuggestionFormValues>(EMPTY);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [check, setCheck] = useState<SuggestionCheck | null>(null);
    const [checkedUrl, setCheckedUrl] = useState('');
    // The link the running check is for; an answer for any other link (edited, saved, reset) is dropped
    const pendingUrl = useRef('');
    const [saving, setSaving] = useState(false);
    const [showDone, setShowDone] = useState(false);
    const [now] = useState(() => Date.now());

    const [version, setVersion] = useState(0);
    const load = useCallback(() => setVersion((v) => v + 1), []);

    useEffect(() => {
        api.get<Suggestion[]>('/api/suggestions')
            .then((response) => {
                setItems(response.data);
                setSuggestionCount(response.data.filter((s) => s.status === 'open').length);
            })
            .catch((e) => toast(errorMessage(e)));
    }, [version, toast, setSuggestionCount]);

    useEffect(() => {
        api.get<AppSettings>('/api/settings')
            .then((response) => setAddress(mailAddress(response.data.inbound_address)))
            .catch(() => {});
    }, []);

    const set = (key: keyof SuggestionFormValues) => (value: string) => setValues((v) => ({ ...v, [key]: value }));

    const checkUrl = async (raw: string) => {
        const url = withScheme(raw);
        if (!url || url === checkedUrl || editingId !== null) return;
        setCheckedUrl(url);
        setValues((v) => ({ ...v, url }));
        pendingUrl.current = url;
        try {
            const response = await api.post<SuggestionCheck>('/api/suggestions/check', { url });
            if (pendingUrl.current !== url) return;
            setCheck(response.data);
            const title = response.data.title;
            if (title) setValues((v) => (v.position || v.url !== url ? v : { ...v, position: title }));
        } catch {
            if (pendingUrl.current === url) setCheck(null);
        }
    };

    const changeUrl = (value: string) => {
        pendingUrl.current = '';
        setCheck(null);
        set('url')(value);
    };

    const reset = () => {
        pendingUrl.current = '';
        setValues(EMPTY);
        setEditingId(null);
        setCheck(null);
        setCheckedUrl('');
    };

    const submit = async (event: FormEvent) => {
        event.preventDefault();
        setSaving(true);
        const body = { ...values, url: withScheme(values.url), deadline: values.deadline || null };
        try {
            if (editingId === null) {
                await api.post('/api/suggestions', body);
                toast('Vorschlag gespeichert', 'success');
            } else {
                await api.patch(`/api/suggestions/${editingId}`, body);
                toast('Vorschlag geändert', 'success');
            }
            reset();
            load();
        } catch (e) {
            toast(errorMessage(e));
        } finally {
            setSaving(false);
        }
    };

    const edit = (s: Suggestion) => {
        setEditingId(s.id);
        setCheck(null);
        setValues({
            url: s.url,
            company: s.company,
            position: s.position,
            location: s.location,
            deadline: s.deadline ?? '',
            note: s.note,
        });
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    if (items === null) return <p className="text-slate-400">Laden…</p>;
    const open = items.filter((s) => s.status === 'open').sort(byDeadline);
    const done = items.filter((s) => s.status !== 'open');

    return (
        <div className="space-y-4">
            <h1 className="text-2xl font-bold">Vorschläge</h1>
            <form onSubmit={submit} className={`${CARD} space-y-3`}>
                <h2 className="font-semibold">{editingId === null ? 'Lehrstelle vorschlagen' : 'Vorschlag bearbeiten'}</h2>
                <label className="block text-sm">
                    <span className="mb-1 block text-slate-400">Link zur Lehrstelle</span>
                    <input
                        type="text"
                        inputMode="url"
                        required
                        value={values.url}
                        onChange={(e) => changeUrl(e.target.value)}
                        onBlur={(e) => checkUrl(e.target.value)}
                        onPaste={(e) => {
                            const input = e.currentTarget;
                            // The pasted text is in the field only after the event
                            setTimeout(() => checkUrl(input.value));
                        }}
                        placeholder="https://www.yousty.ch/…"
                        className={INPUT}
                    />
                </label>
                {check && check.duplicates.length > 0 && (
                    <ul className="rounded-lg border border-amber-700 bg-amber-900/30 p-2 text-sm text-amber-200">
                        {check.duplicates.map((d) => (
                            <li key={`${d.kind}-${d.id}`}>
                                {d.kind === 'suggestion'
                                    ? `Schon vorgeschlagen am ${formatDate(d.date)}: ${d.label}`
                                    : `Bewerbung existiert: ${d.label}`}
                            </li>
                        ))}
                    </ul>
                )}
                <div className="grid gap-3 sm:grid-cols-2">
                    <label className="block text-sm">
                        <span className="mb-1 block text-slate-400">Stelle</span>
                        <input value={values.position} onChange={(e) => set('position')(e.target.value)} className={INPUT} />
                    </label>
                    <label className="block text-sm">
                        <span className="mb-1 block text-slate-400">Firma</span>
                        <input value={values.company} onChange={(e) => set('company')(e.target.value)} className={INPUT} />
                    </label>
                    <label className="block text-sm">
                        <span className="mb-1 block text-slate-400">Ort</span>
                        <input value={values.location} onChange={(e) => set('location')(e.target.value)} className={INPUT} />
                    </label>
                    <label className="block text-sm">
                        <span className="mb-1 block text-slate-400">Bewerbungsfrist</span>
                        <input
                            type="date"
                            value={values.deadline}
                            onChange={(e) => set('deadline')(e.target.value)}
                            className={INPUT}
                        />
                    </label>
                </div>
                <label className="block text-sm">
                    <span className="mb-1 block text-slate-400">Notiz</span>
                    <textarea value={values.note} onChange={(e) => set('note')(e.target.value)} rows={2} className={INPUT} />
                </label>
                <div className="flex flex-wrap gap-2">
                    <button type="submit" className={BUTTON} disabled={saving}>
                        {editingId === null ? 'Vorschlagen' : 'Speichern'}
                    </button>
                    {editingId !== null && (
                        <button type="button" className={BUTTON_SECONDARY} onClick={reset}>
                            Abbrechen
                        </button>
                    )}
                </div>
                {address && (
                    <p className="text-xs text-slate-500">
                        Auch per Mail: Link an <span className="text-slate-300">{address}</span> schicken (von deiner
                        gespeicherten Adresse aus).
                    </p>
                )}
            </form>

            <h2 className="text-lg font-semibold">Offen ({open.length})</h2>
            {open.length === 0 && <p className="text-slate-400">Keine offenen Vorschläge.</p>}
            {open.map((s) => (
                <SuggestionCard key={s.id} suggestion={s} now={now} onChanged={load} onEdit={edit} />
            ))}

            {done.length > 0 && (
                <div className="space-y-3">
                    <button type="button" className="text-sm text-slate-400 hover:text-white" onClick={() => setShowDone((v) => !v)}>
                        {showDone ? '▾' : '▸'} Erledigt ({done.length})
                    </button>
                    {showDone &&
                        done.map((s) => <SuggestionCard key={s.id} suggestion={s} now={now} onChanged={load} onEdit={edit} />)}
                </div>
            )}
        </div>
    );
}
