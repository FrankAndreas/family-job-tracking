import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import api, { errorMessage } from '../api';
import ApplicationForm from '../components/ApplicationForm';
import EventForm from '../components/EventForm';
import StatusBadge from '../components/StatusBadge';
import Timeline from '../components/Timeline';
import { CHANNEL_LABELS } from '../labels';
import { useToast } from '../ToastContext';
import type { ApplicationDetail, ApplicationFormValues } from '../types';
import { BUTTON_DANGER, BUTTON_SECONDARY, CARD } from '../ui';

function toFormValues(a: ApplicationDetail): ApplicationFormValues {
    return {
        company: a.company,
        position: a.position,
        location: a.location,
        contact_name: a.contact_name,
        contact_email: a.contact_email,
        contact_phone: a.contact_phone,
        posting_url: a.posting_url,
        channel: a.channel,
        notes: a.notes,
    };
}

export default function ApplicationPage() {
    const { id } = useParams();
    const navigate = useNavigate();
    const toast = useToast();
    const [application, setApplication] = useState<ApplicationDetail | null>(null);
    const [editing, setEditing] = useState(false);

    // Bumping the version reloads the application, e.g. after an event was added
    const [version, setVersion] = useState(0);
    const load = useCallback(() => setVersion((v) => v + 1), []);

    useEffect(() => {
        api.get<ApplicationDetail>(`/api/applications/${id}`)
            .then((response) => setApplication(response.data))
            .catch((e) => toast(errorMessage(e, 'Bewerbung nicht gefunden')));
    }, [id, version, toast]);

    if (!application) return <p className="text-slate-400">Laden…</p>;

    const save = async (values: ApplicationFormValues) => {
        await api.patch(`/api/applications/${application.id}`, values);
        setEditing(false);
        load();
    };

    const toggleArchived = async () => {
        try {
            await api.patch(`/api/applications/${application.id}`, { archived: !application.archived });
            load();
        } catch (e) {
            toast(errorMessage(e));
        }
    };

    const remove = async () => {
        if (!window.confirm(`„${application.company}“ mit allen Ereignissen, Mails und Dateien löschen?`)) return;
        try {
            await api.delete(`/api/applications/${application.id}`);
            navigate('/');
        } catch (e) {
            toast(errorMessage(e));
        }
    };

    const copyAddress = () => {
        const address = application.mail_address;
        // The clipboard API only exists on https (or localhost)
        if (!address || !navigator.clipboard) {
            toast('Kopieren nicht möglich – bitte von Hand markieren');
            return;
        }
        navigator.clipboard.writeText(address).then(
            () => toast('Adresse kopiert', 'success'),
            () => toast('Kopieren nicht möglich – bitte von Hand markieren'),
        );
    };

    const details: [string, string][] = [
        ['Ort', application.location],
        ['Ansprechperson', application.contact_name],
        ['E-Mail', application.contact_email],
        ['Telefon', application.contact_phone],
        ['Kanal', CHANNEL_LABELS[application.channel]],
    ];
    const postingIsLink = /^https?:\/\//i.test(application.posting_url);

    return (
        <div className="space-y-6">
            <div className="flex flex-wrap items-start gap-3">
                <div className="mr-auto">
                    <h1 className="text-2xl font-bold">{application.company}</h1>
                    <p className="text-slate-400">{application.position || 'Stelle nicht angegeben'}</p>
                </div>
                <StatusBadge status={application.status} />
            </div>

            {application.mail_address ? (
                <div className={`${CARD} flex flex-wrap items-center gap-2 text-sm`}>
                    <span className="text-slate-400">Mails an / BCC:</span>
                    <code className="break-all">{application.mail_address}</code>
                    <button type="button" onClick={copyAddress} className="ml-auto text-blue-300 hover:underline">
                        Kopieren
                    </button>
                </div>
            ) : (
                <p className="text-sm text-slate-500">
                    Für eine eigene Mail-Adresse pro Bewerbung die Eingangsadresse in den Einstellungen setzen.
                </p>
            )}

            <section className={CARD}>
                {editing ? (
                    <ApplicationForm
                        initial={toFormValues(application)}
                        submitLabel="Speichern"
                        onSubmit={save}
                        onCancel={() => setEditing(false)}
                    />
                ) : (
                    <>
                        <dl className="grid gap-2 text-sm sm:grid-cols-2">
                            {details
                                .filter(([, value]) => value)
                                .map(([label, value]) => (
                                    <div key={label}>
                                        <dt className="text-slate-500">{label}</dt>
                                        <dd className="break-words">{value}</dd>
                                    </div>
                                ))}
                            {application.posting_url && (
                                <div>
                                    <dt className="text-slate-500">Inserat</dt>
                                    <dd className="break-all">
                                        {postingIsLink ? (
                                            <a
                                                href={application.posting_url}
                                                target="_blank"
                                                rel="noreferrer"
                                                className="text-blue-300 hover:underline"
                                            >
                                                {application.posting_url}
                                            </a>
                                        ) : (
                                            application.posting_url
                                        )}
                                    </dd>
                                </div>
                            )}
                        </dl>
                        {application.notes && <p className="mt-3 whitespace-pre-wrap text-sm">{application.notes}</p>}
                        <div className="mt-4 flex flex-wrap gap-2">
                            <button type="button" onClick={() => setEditing(true)} className={BUTTON_SECONDARY}>
                                Bearbeiten
                            </button>
                            <button type="button" onClick={toggleArchived} className={BUTTON_SECONDARY}>
                                {application.archived ? 'Wiederherstellen' : 'Archivieren'}
                            </button>
                            <button type="button" onClick={remove} className={BUTTON_DANGER}>
                                Löschen
                            </button>
                        </div>
                    </>
                )}
            </section>

            <section className="space-y-4">
                <h2 className="text-xl font-bold">Verlauf</h2>
                <EventForm
                    applicationId={application.id}
                    defaultType={application.events.length ? 'followed_up' : 'sent'}
                    onSaved={load}
                />
                <Timeline events={application.events} onChanged={load} />
            </section>
        </div>
    );
}
