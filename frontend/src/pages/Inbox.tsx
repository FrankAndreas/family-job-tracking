import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useOutletContext } from 'react-router-dom';
import api, { downloadFile, errorMessage } from '../api';
import { EVENT_LABELS, formatDateTime, formatSize } from '../labels';
import { useToast } from '../ToastContext';
import type { ApplicationSummary, EventType, InboxItem, LayoutContext } from '../types';
import { BUTTON, BUTTON_SECONDARY, CARD, FIELD } from '../ui';

const MAIL_EVENT_TYPES: EventType[] = [
    'mail_received',
    'mail_sent',
    'reply_received',
    'sent',
    'followed_up',
    'interview',
    'offer',
    'rejection',
];

// "hr.migros.ch" -> "Migros", as a starting point for a new application
function guessCompany(fromAddr: string): string {
    const parts = (fromAddr.split('@')[1] ?? '').split('.');
    const name = parts.length >= 2 ? parts[parts.length - 2] : '';
    return name ? name.charAt(0).toUpperCase() + name.slice(1) : '';
}

interface CardProps {
    item: InboxItem;
    applications: ApplicationSummary[];
    onDone: () => void;
}

function InboxCard({ item, applications, onDone }: CardProps) {
    const toast = useToast();
    const navigate = useNavigate();
    const [applicationId, setApplicationId] = useState(item.suggestion ? String(item.suggestion.id) : '');
    const [eventType, setEventType] = useState<EventType | ''>('');
    const [creating, setCreating] = useState(false);
    const [company, setCompany] = useState(() => guessCompany(item.from_addr));
    const [position, setPosition] = useState('');
    const [busy, setBusy] = useState(false);

    const run = async (action: () => Promise<void>) => {
        setBusy(true);
        try {
            await action();
        } catch (e) {
            toast(errorMessage(e));
        } finally {
            setBusy(false);
        }
    };

    const assign = () =>
        run(async () => {
            await api.post(`/api/inbox/${item.id}/assign`, {
                application_id: Number(applicationId),
                event_type: eventType || null,
            });
            toast('Mail zugeordnet', 'success');
            onDone();
        });

    const create = () =>
        run(async () => {
            const response = await api.post<{ application_id: number }>(
                `/api/inbox/${item.id}/create-application`,
                { company, position },
            );
            navigate(`/bewerbungen/${response.data.application_id}`);
        });

    const dismiss = () => {
        if (!window.confirm('Diese Mail verwerfen?')) return;
        run(async () => {
            await api.post(`/api/inbox/${item.id}/dismiss`);
            onDone();
        });
    };

    return (
        <article className={`${CARD} space-y-3`}>
            <header>
                <div className="font-semibold">{item.subject || '(kein Betreff)'}</div>
                <div className="text-sm text-slate-400">
                    {item.from_addr || 'unbekannter Absender'} · {formatDateTime(item.received_at)}
                </div>
                {item.parse_error && (
                    <div className="mt-1 text-sm text-red-300">Konnte nicht gelesen werden: {item.parse_error}</div>
                )}
            </header>
            {item.body_text && (
                <details className="text-sm">
                    <summary className="cursor-pointer text-slate-300">Inhalt anzeigen</summary>
                    <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap font-sans">{item.body_text}</pre>
                </details>
            )}
            {item.attachments.length > 0 && (
                <ul className="text-sm">
                    {item.attachments.map((a) => (
                        <li key={a.id}>
                            <button
                                type="button"
                                className="text-blue-300 hover:underline"
                                onClick={() =>
                                    downloadFile(`/api/attachments/${a.id}`, a.filename).catch((e) =>
                                        toast(errorMessage(e)),
                                    )
                                }
                            >
                                📎 {a.filename}
                            </button>{' '}
                            <span className="text-xs text-slate-500">{formatSize(a.size)}</span>
                        </li>
                    ))}
                </ul>
            )}
            {item.suggestion && (
                <p className="text-sm text-amber-300">
                    Gehört vermutlich zu{' '}
                    <Link to={`/bewerbungen/${item.suggestion.id}`} className="underline">
                        {item.suggestion.company}
                    </Link>
                </p>
            )}
            <div className="flex flex-wrap gap-2">
                <select
                    value={applicationId}
                    onChange={(e) => setApplicationId(e.target.value)}
                    className={`${FIELD} min-w-40 flex-1`}
                >
                    <option value="">Bewerbung wählen…</option>
                    {applications.map((a) => (
                        <option key={a.id} value={a.id}>
                            {a.company}
                            {a.position ? ` – ${a.position}` : ''}
                        </option>
                    ))}
                </select>
                <select
                    value={eventType}
                    onChange={(e) => setEventType(e.target.value as EventType | '')}
                    className={FIELD}
                >
                    <option value="">Typ automatisch</option>
                    {MAIL_EVENT_TYPES.map((t) => (
                        <option key={t} value={t}>
                            {EVENT_LABELS[t]}
                        </option>
                    ))}
                </select>
                <button type="button" disabled={busy || !applicationId} onClick={assign} className={BUTTON}>
                    Zuordnen
                </button>
            </div>
            {creating ? (
                <div className="flex flex-wrap gap-2">
                    <input
                        placeholder="Firma"
                        value={company}
                        onChange={(e) => setCompany(e.target.value)}
                        className={`${FIELD} min-w-32 flex-1`}
                    />
                    <input
                        placeholder="Stelle"
                        value={position}
                        onChange={(e) => setPosition(e.target.value)}
                        className={`${FIELD} min-w-32 flex-1`}
                    />
                    <button type="button" disabled={busy || !company.trim()} onClick={create} className={BUTTON}>
                        Erstellen
                    </button>
                    <button type="button" onClick={() => setCreating(false)} className={BUTTON_SECONDARY}>
                        Abbrechen
                    </button>
                </div>
            ) : (
                <div className="flex flex-wrap gap-2">
                    <button type="button" onClick={() => setCreating(true)} className={BUTTON_SECONDARY}>
                        Neue Bewerbung daraus erstellen
                    </button>
                    <button type="button" disabled={busy} onClick={dismiss} className={BUTTON_SECONDARY}>
                        Verwerfen
                    </button>
                </div>
            )}
        </article>
    );
}

export default function Inbox() {
    const toast = useToast();
    const { setInboxCount } = useOutletContext<LayoutContext>();
    const [items, setItems] = useState<InboxItem[] | null>(null);
    const [applications, setApplications] = useState<ApplicationSummary[]>([]);

    // Bumping the version reloads the inbox, e.g. after a mail was assigned
    const [version, setVersion] = useState(0);
    const load = useCallback(() => setVersion((v) => v + 1), []);

    useEffect(() => {
        Promise.all([api.get<InboxItem[]>('/api/inbox'), api.get<ApplicationSummary[]>('/api/applications')])
            .then(([inbox, apps]) => {
                setItems(inbox.data);
                // Keep the navigation badge in step after assigning or dismissing a mail
                setInboxCount(inbox.data.length);
                setApplications([...apps.data].sort((a, b) => a.company.localeCompare(b.company, 'de')));
            })
            .catch((e) => toast(errorMessage(e)));
    }, [version, toast, setInboxCount]);

    if (items === null) return <p className="text-slate-400">Laden…</p>;

    return (
        <div className="space-y-4">
            <h1 className="text-2xl font-bold">Posteingang</h1>
            <p className="text-sm text-slate-400">
                Mails ohne Bewerbungs-Kennung landen hier. Ordne sie einer Bewerbung zu oder verwirf sie.
            </p>
            {items.length === 0 && <p className="text-slate-400">Keine offenen Mails.</p>}
            {items.map((item) => (
                <InboxCard key={item.id} item={item} applications={applications} onDone={load} />
            ))}
        </div>
    );
}
