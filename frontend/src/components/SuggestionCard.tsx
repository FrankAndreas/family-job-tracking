import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import api, { errorMessage } from '../api';
import { formatDate, formatDateTime } from '../labels';
import { useToast } from '../ToastContext';
import type { Suggestion } from '../types';
import { BUTTON, BUTTON_DANGER, BUTTON_SECONDARY, CARD } from '../ui';

const SOON_MS = 7 * 24 * 60 * 60 * 1000;

function host(url: string): string {
    try {
        return new URL(url).hostname.replace(/^www\./, '');
    } catch {
        return url;
    }
}

function title(s: Suggestion): string {
    return [s.company, s.position].filter(Boolean).join(' – ') || host(s.url);
}

function Deadline({ s, now }: { s: Suggestion; now: number }) {
    if (!s.deadline) return null;
    const soon = !s.deadline_passed && new Date(s.deadline).getTime() - now < SOON_MS;
    const color = s.deadline_passed ? 'text-red-400' : soon ? 'text-amber-400' : 'text-slate-400';
    return (
        <span className={color}>
            {s.deadline_passed ? 'Frist abgelaufen' : 'Frist'} {formatDate(s.deadline)}
        </span>
    );
}

interface Props {
    suggestion: Suggestion;
    now: number; // Date.now() of the page load, for "deadline soon"
    onChanged: () => void;
    onEdit: (s: Suggestion) => void;
}

export default function SuggestionCard({ suggestion: s, now, onChanged, onEdit }: Props) {
    const toast = useToast();
    const navigate = useNavigate();
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

    const apply = () => {
        let company = s.company;
        if (!company) {
            company = window.prompt('Bei welcher Firma ist die Lehrstelle?')?.trim() ?? '';
            if (!company) return;
        }
        run(async () => {
            const response = await api.post<{ application_id: number }>(`/api/suggestions/${s.id}/apply`, { company });
            navigate(`/bewerbungen/${response.data.application_id}`);
        });
    };

    const decline = () => {
        const reason = window.prompt('Nicht interessiert. Grund (optional):');
        if (reason === null) return;
        run(async () => {
            await api.post(`/api/suggestions/${s.id}/decline`, { reason });
            onChanged();
        });
    };

    const reopen = () =>
        run(async () => {
            await api.post(`/api/suggestions/${s.id}/reopen`);
            onChanged();
        });

    const remove = () => {
        if (!window.confirm('Diesen Vorschlag löschen?')) return;
        run(async () => {
            await api.delete(`/api/suggestions/${s.id}`);
            onChanged();
        });
    };

    return (
        <div className={`${CARD} space-y-2`}>
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <a href={s.url} target="_blank" rel="noreferrer" className="font-semibold text-blue-300 hover:underline">
                    {title(s)}
                </a>
                {s.location && <span className="text-sm text-slate-400">{s.location}</span>}
                <span className="text-sm">
                    <Deadline s={s} now={now} />
                </span>
            </div>
            {s.note && <p className="whitespace-pre-wrap text-sm text-slate-300">{s.note}</p>}
            <p className="text-xs text-slate-500">
                Vorgeschlagen von {s.created_by_name ?? 'unbekannt'} am {formatDateTime(s.created_at)}
                {s.source === 'mail' && ' (per Mail)'} · {host(s.url)}
            </p>
            {s.status === 'applied' && (
                <p className="text-sm text-emerald-400">
                    Beworben
                    {s.application ? (
                        <>
                            : <Link to={`/bewerbungen/${s.application.id}`} className="underline">zur Bewerbung</Link>
                        </>
                    ) : (
                        ' (Bewerbung gelöscht)'
                    )}
                </p>
            )}
            {s.status === 'declined' && (
                <p className="text-sm text-slate-400">
                    Nicht interessiert{s.decline_reason && `: ${s.decline_reason}`} ({s.decided_by_name ?? 'unbekannt'})
                </p>
            )}
            <div className="flex flex-wrap gap-2">
                {s.status === 'open' ? (
                    <>
                        <button type="button" className={BUTTON} disabled={busy} onClick={apply}>
                            Bewerben
                        </button>
                        <button type="button" className={BUTTON_SECONDARY} disabled={busy} onClick={decline}>
                            Nicht interessiert
                        </button>
                        <button type="button" className={BUTTON_SECONDARY} disabled={busy} onClick={() => onEdit(s)}>
                            Bearbeiten
                        </button>
                    </>
                ) : (
                    <button type="button" className={BUTTON_SECONDARY} disabled={busy} onClick={reopen}>
                        Wieder öffnen
                    </button>
                )}
                <button type="button" className={BUTTON_DANGER} disabled={busy} onClick={remove}>
                    Löschen
                </button>
            </div>
        </div>
    );
}
