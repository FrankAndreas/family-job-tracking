import { useState, type FormEvent } from 'react';
import api, { errorMessage } from '../../api';
import { useAuth } from '../../AuthContext';
import { useToast } from '../../ToastContext';
import { BUTTON, CARD, INPUT } from '../../ui';
import PinInput from '../PinInput';

export default function MyAccount() {
    const { user, refreshUser } = useAuth();
    const toast = useToast();
    const [email, setEmail] = useState(user?.email ?? '');
    const [wantsReminders, setWantsReminders] = useState(user?.wants_reminders ?? false);
    const [currentPin, setCurrentPin] = useState('');
    const [newPin, setNewPin] = useState('');

    const saveProfile = async (e: FormEvent) => {
        e.preventDefault();
        try {
            await api.patch('/api/me', { email, wants_reminders: wantsReminders });
            await refreshUser();
            toast('Gespeichert', 'success');
        } catch (err) {
            toast(errorMessage(err));
        }
    };

    const changePin = async (e: FormEvent) => {
        e.preventDefault();
        try {
            await api.post('/api/me/pin', { current_pin: currentPin, new_pin: newPin });
            setCurrentPin('');
            setNewPin('');
            toast('PIN geändert', 'success');
        } catch (err) {
            toast(errorMessage(err, 'PIN konnte nicht geändert werden'));
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
                    <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className={INPUT} />
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
            <form onSubmit={changePin} className="space-y-3">
                <h3 className="font-semibold">PIN ändern</h3>
                <div className="grid gap-3 sm:grid-cols-2">
                    <PinInput id="current-pin" value={currentPin} onChange={setCurrentPin} placeholder="Aktueller PIN" />
                    <PinInput
                        id="new-pin"
                        value={newPin}
                        onChange={setNewPin}
                        placeholder="Neuer PIN (4–8 Ziffern)"
                        autoComplete="new-password"
                    />
                </div>
                <button type="submit" disabled={currentPin.length < 4 || newPin.length < 4} className={BUTTON}>
                    PIN ändern
                </button>
            </form>
        </section>
    );
}
