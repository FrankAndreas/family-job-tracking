import { Fragment, useEffect, useState, type ReactNode } from 'react';
import api, { errorMessage } from '../../api';
import { formatDateTime } from '../../labels';
import { useToast } from '../../ToastContext';
import type { Integration, IntegrationState, Integrations } from '../../types';
import { BUTTON_SECONDARY, CARD } from '../../ui';

const STATE_STYLES: Record<IntegrationState, { label: string; className: string }> = {
    ok: { label: 'OK', className: 'bg-emerald-600' },
    waiting: { label: 'Wartet', className: 'bg-amber-600' },
    error: { label: 'Fehler', className: 'bg-red-600' },
    not_configured: { label: 'Nicht konfiguriert', className: 'bg-slate-600' },
};

const DETAIL_LABELS: Record<string, string> = {
    address: 'Eingangsadresse',
    last_received_at: 'Letzte Mail',
    last_error: 'Letzter Fehler',
    mail_from: 'Absender',
    recipients: 'Empfänger',
    next_run: 'Nächster Versand',
    last_attempt_at: 'Letzter Versuch',
    last_sent_at: 'Zuletzt versendet',
};

function formatValue(value: string | number | string[] | null): string {
    if (value === null || value === '') return '–';
    if (Array.isArray(value)) return value.length ? value.join(', ') : '–';
    if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T.*Z$/.test(value)) return formatDateTime(value);
    return String(value);
}

interface CardProps {
    title: string;
    integration: Integration;
    help: string;
    children?: ReactNode;
}

function IntegrationCard({ title, integration, help, children }: CardProps) {
    const style = STATE_STYLES[integration.state];
    return (
        <div className={`${CARD} space-y-2`}>
            <div className="flex items-center gap-2">
                <h3 className="mr-auto font-semibold">{title}</h3>
                <span className={`rounded-full px-2 py-0.5 text-xs font-semibold text-white ${style.className}`}>
                    {style.label}
                </span>
            </div>
            {integration.state === 'not_configured' ? (
                <p className="text-sm text-slate-400">{help}</p>
            ) : (
                <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
                    {Object.entries(integration.details).map(([key, value]) => (
                        <Fragment key={key}>
                            <dt className="text-slate-500">{DETAIL_LABELS[key] ?? key}</dt>
                            <dd className={`break-words ${key === 'last_error' && value ? 'text-red-300' : ''}`}>
                                {formatValue(value)}
                            </dd>
                        </Fragment>
                    ))}
                </dl>
            )}
            {integration.warnings.map((warning) => (
                <p key={warning} className="text-sm text-amber-300">
                    ⚠ {warning}
                </p>
            ))}
            {children}
        </div>
    );
}

export default function IntegrationCards() {
    const toast = useToast();
    const [data, setData] = useState<Integrations | null>(null);
    const [sending, setSending] = useState(false);

    // Bumping the version reloads the status, e.g. after a test reminder
    const [version, setVersion] = useState(0);

    useEffect(() => {
        api.get<Integrations>('/api/integrations')
            .then((response) => setData(response.data))
            .catch((e) => toast(errorMessage(e)));
    }, [version, toast]);

    const sendTest = async () => {
        setSending(true);
        try {
            await api.post('/api/integrations/reminders/test');
            toast('Test-Erinnerung gesendet', 'success');
        } catch (e) {
            toast(errorMessage(e, 'Versand fehlgeschlagen'));
        } finally {
            setSending(false);
            setVersion((v) => v + 1);
        }
    };

    if (!data) return null;

    return (
        <section className="space-y-3">
            <h2 className="text-lg font-bold">Integrationen</h2>
            <div className="grid gap-3 sm:grid-cols-2">
                <IntegrationCard
                    title="Eingehende Mails (Cloudflare)"
                    integration={data.inbound}
                    help="INBOUND_SECRET in .env und als Worker-Secret setzen (siehe README_DOCKER.md)."
                />
                <IntegrationCard
                    title="Erinnerungen (Resend)"
                    integration={data.reminders}
                    help="RESEND_API_KEY und MAIL_FROM in .env setzen (siehe README_DOCKER.md)."
                >
                    {data.reminders.state !== 'not_configured' && (
                        <button type="button" disabled={sending} onClick={sendTest} className={BUTTON_SECONDARY}>
                            Test-Erinnerung senden
                        </button>
                    )}
                </IntegrationCard>
            </div>
        </section>
    );
}
