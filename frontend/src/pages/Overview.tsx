import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import api, { errorMessage } from '../api';
import ApplicationForm from '../components/ApplicationForm';
import StatusBadge from '../components/StatusBadge';
import { EVENT_LABELS, STATUS_LABELS, formatDate } from '../labels';
import { useToast } from '../ToastContext';
import type { ApplicationDetail, ApplicationFormValues, ApplicationSummary, Dashboard, Status } from '../types';
import { BUTTON, CARD, EMPTY_APPLICATION, FIELD } from '../ui';

const TILES: { status: Status; label: string }[] = [
    { status: 'open', label: 'Offen' },
    { status: 'in_contact', label: 'In Kontakt' },
    { status: 'closed_offer', label: 'Zusagen' },
    { status: 'closed_rejection', label: 'Absagen' },
];

function ApplicationRow({ item }: { item: ApplicationSummary }) {
    return (
        <Link
            to={`/bewerbungen/${item.id}`}
            className="flex items-center gap-3 rounded-lg border border-slate-800 bg-slate-900/60 p-3 hover:border-slate-600"
        >
            <div className="min-w-0 flex-1">
                <div className="truncate font-semibold">
                    {item.company}
                    {item.archived && <span className="ml-2 text-xs font-normal text-slate-500">archiviert</span>}
                </div>
                <div className="truncate text-sm text-slate-400">
                    {item.position || '–'}
                    {item.location && ` · ${item.location}`}
                </div>
            </div>
            <div className="text-right text-xs text-slate-400">
                <StatusBadge status={item.status} />
                <div className="mt-1">
                    {item.last_event_type
                        ? `${EVENT_LABELS[item.last_event_type]}, ${formatDate(item.last_event_at)}`
                        : 'noch nichts erfasst'}
                </div>
            </div>
        </Link>
    );
}

export default function Overview() {
    const navigate = useNavigate();
    const toast = useToast();
    const [dashboard, setDashboard] = useState<Dashboard | null>(null);
    const [items, setItems] = useState<ApplicationSummary[]>([]);
    const [status, setStatus] = useState<Status | ''>('');
    const [query, setQuery] = useState('');
    const [includeArchived, setIncludeArchived] = useState(false);
    const [creating, setCreating] = useState(false);

    useEffect(() => {
        api.get<Dashboard>('/api/dashboard')
            .then((response) => setDashboard(response.data))
            .catch((e) => toast(errorMessage(e)));
    }, [toast]);

    useEffect(() => {
        // Wait until typing in the search field pauses
        const timer = setTimeout(() => {
            api.get<ApplicationSummary[]>('/api/applications', {
                params: { status: status || undefined, q: query || undefined, include_archived: includeArchived },
            })
                .then((response) => setItems(response.data))
                .catch((e) => toast(errorMessage(e)));
        }, 250);
        return () => clearTimeout(timer);
    }, [status, query, includeArchived, toast]);

    const create = async (values: ApplicationFormValues) => {
        const response = await api.post<ApplicationDetail>('/api/applications', values);
        navigate(`/bewerbungen/${response.data.id}`);
    };

    return (
        <div className="space-y-6">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {TILES.map((tile) => (
                    <button
                        key={tile.status}
                        type="button"
                        onClick={() => setStatus(status === tile.status ? '' : tile.status)}
                        className={`${CARD} text-left ${status === tile.status ? 'border-blue-400' : ''}`}
                    >
                        <div className="text-3xl font-bold">{dashboard?.counts[tile.status] ?? '–'}</div>
                        <div className="text-sm text-slate-400">{tile.label}</div>
                    </button>
                ))}
            </div>

            {dashboard && dashboard.due.length > 0 && (
                <section className={`${CARD} border-amber-600/60`}>
                    <h2 className="mb-2 font-bold text-amber-300">Nachfragen fällig</h2>
                    <ul className="space-y-1 text-sm">
                        {dashboard.due.map((d) => (
                            <li key={d.id}>
                                <Link to={`/bewerbungen/${d.id}`} className="hover:underline">
                                    {d.company}
                                    {d.position && ` – ${d.position}`}
                                </Link>
                                <span className="text-slate-400"> · seit {d.days_since_last} Tagen nichts mehr</span>
                            </li>
                        ))}
                    </ul>
                </section>
            )}

            <section className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                    <h2 className="mr-auto text-xl font-bold">Bewerbungen</h2>
                    <button type="button" onClick={() => setCreating(true)} className={BUTTON}>
                        Neue Bewerbung
                    </button>
                </div>
                {creating && (
                    <div className={CARD}>
                        <ApplicationForm
                            initial={EMPTY_APPLICATION}
                            submitLabel="Erstellen"
                            onSubmit={create}
                            onCancel={() => setCreating(false)}
                        />
                    </div>
                )}
                <div className="flex flex-wrap items-center gap-2">
                    <input
                        type="search"
                        placeholder="Suchen…"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        className={`${FIELD} min-w-40 flex-1`}
                    />
                    <select
                        value={status}
                        onChange={(e) => setStatus(e.target.value as Status | '')}
                        className={FIELD}
                    >
                        <option value="">Alle Status</option>
                        {Object.entries(STATUS_LABELS).map(([value, label]) => (
                            <option key={value} value={value}>
                                {label}
                            </option>
                        ))}
                    </select>
                    <label className="flex items-center gap-2 text-sm text-slate-300">
                        <input
                            type="checkbox"
                            checked={includeArchived}
                            onChange={(e) => setIncludeArchived(e.target.checked)}
                        />
                        Archivierte zeigen
                    </label>
                </div>
                <div className="space-y-2">
                    {items.map((item) => (
                        <ApplicationRow key={item.id} item={item} />
                    ))}
                    {items.length === 0 && <p className="text-slate-400">Keine Bewerbungen gefunden.</p>}
                </div>
            </section>
        </div>
    );
}
