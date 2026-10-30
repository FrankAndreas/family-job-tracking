import { useState, type FormEvent } from 'react';
import api, { errorMessage } from '../../api';
import { useAuth } from '../../AuthContext';
import { useToast } from '../../ToastContext';
import { BUTTON, CARD, INPUT } from '../../ui';

export default function MyAccount() {
    const { user, refreshUser } = useAuth();
    const toast = useToast();
    const [email, setEmail] = useState(user?.email ?? '');
    const [wantsReminders, setWantsReminders] = useState(user?.wants_reminders ?? false);

    const saveProfile = async (e: FormEvent) => {
        e.preventDefault();
        try {
            // An address from the family hub is changed there; only the reminder choice is saved here
            await api.patch('/api/me', user?.email_from_hub ? { wants_reminders: wantsReminders } : { email, wants_reminders: wantsReminders });
            await refreshUser();
            toast('Gespeichert', 'success');
        } catch (err) {
            toast(errorMessage(err));
        }
    };

    return (
        <section className={`${CARD} space-y-4`}>
            <h2 className="text-lg font-bold">Mein Konto ({user?.name})</h2>
            <form onSubmit={saveProfile} className="space-y-3">
                <label className="block text-sm">
                    <span className="mb-1 block text-slate-400">
                        E-Mail-Adresse (für Erinnerungen; Mails von dieser Adresse gelten als „gesendet“)
                    </span>
                    <input
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        readOnly={user?.email_from_hub}
                        className={INPUT}
                    />
                    {user?.email_from_hub && (
                        <span className="mt-1 block text-xs text-slate-500">
                            Kommt aus dem Familien-Hub: dort unter Einstellungen → Personen ändern.
                        </span>
                    )}
                </label>
                <label className="flex items-center gap-2 text-sm">
                    <input
                        type="checkbox"
                        checked={wantsReminders}
                        onChange={(e) => setWantsReminders(e.target.checked)}
                    />
                    Tägliche Erinnerung per E-Mail erhalten
                </label>
                <button type="submit" className={BUTTON}>
                    Speichern
                </button>
            </form>
            <p className="text-sm text-slate-400">Name, PIN und das Abmelden auf allen Geräten sind im Familien-Hub.</p>
        </section>
    );
}
