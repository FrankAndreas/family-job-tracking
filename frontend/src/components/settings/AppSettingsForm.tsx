import { useEffect, useState, type FormEvent } from 'react';
import api, { errorMessage } from '../../api';
import { useToast } from '../../ToastContext';
import type { AppSettings } from '../../types';
import { BUTTON, CARD, INPUT } from '../../ui';

export default function AppSettingsForm({ onSaved }: { onSaved: () => void }) {
    const toast = useToast();
    const [settings, setSettings] = useState<AppSettings | null>(null);

    useEffect(() => {
        api.get<AppSettings>('/api/settings')
            .then((response) => setSettings(response.data))
            .catch((e) => toast(errorMessage(e)));
    }, [toast]);

    if (!settings) return null;

    const save = async (e: FormEvent) => {
        e.preventDefault();
        try {
            setSettings((await api.patch<AppSettings>('/api/settings', settings)).data);
            toast('Gespeichert', 'success');
            onSaved();
        } catch (err) {
            toast(errorMessage(err));
        }
    };

    return (
        <section className={`${CARD} space-y-3`}>
            <h2 className="text-lg font-bold">App-Einstellungen</h2>
            <form onSubmit={save} className="grid gap-3 sm:grid-cols-3">
                <label className="block text-sm">
                    <span className="mb-1 block text-slate-400">Nachfragen nach (Tagen)</span>
                    <input
                        type="number"
                        min={1}
                        max={365}
                        required
                        value={settings.followup_days}
                        onChange={(e) => setSettings({ ...settings, followup_days: Number(e.target.value) })}
                        className={INPUT}
                    />
                </label>
                <label className="block text-sm">
                    <span className="mb-1 block text-slate-400">Erinnerung um</span>
                    <input
                        type="time"
                        required
                        value={settings.reminder_time}
                        onChange={(e) => setSettings({ ...settings, reminder_time: e.target.value })}
                        className={INPUT}
                    />
                </label>
                <label className="block text-sm">
                    <span className="mb-1 block text-slate-400">Eingangsadresse</span>
                    <input
                        type="email"
                        placeholder="bewerbungen@deine-domain.ch"
                        value={settings.inbound_address}
                        onChange={(e) => setSettings({ ...settings, inbound_address: e.target.value })}
                        className={INPUT}
                    />
                </label>
                <div className="sm:col-span-3">
                    <button type="submit" className={BUTTON}>
                        Speichern
                    </button>
                </div>
            </form>
        </section>
    );
}
