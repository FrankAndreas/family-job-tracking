import { useCallback, useEffect, useState, type FormEvent } from 'react';
import api, { errorMessage } from '../../api';
import { useAuth } from '../../AuthContext';
import { useToast } from '../../ToastContext';
import type { User } from '../../types';
import { BUTTON, CARD, FIELD } from '../../ui';
import PinInput from '../PinInput';

export default function UserManager() {
    const { user: me } = useAuth();
    const toast = useToast();
    const [users, setUsers] = useState<User[]>([]);
    const [name, setName] = useState('');
    const [pin, setPin] = useState('');
    const [isAdmin, setIsAdmin] = useState(false);

    // Bumping the version reloads the list after a change
    const [version, setVersion] = useState(0);
    const load = useCallback(() => setVersion((v) => v + 1), []);

    useEffect(() => {
        api.get<User[]>('/api/users')
            .then((response) => setUsers(response.data))
            .catch((e) => toast(errorMessage(e)));
    }, [version, toast]);

    const run = async (action: () => Promise<unknown>, success?: string) => {
        try {
            await action();
            if (success) toast(success, 'success');
            load();
        } catch (e) {
            toast(errorMessage(e));
        }
    };

    const add = (e: FormEvent) => {
        e.preventDefault();
        run(async () => {
            await api.post('/api/users', { name, pin, is_admin: isAdmin });
            setName('');
            setPin('');
            setIsAdmin(false);
        }, 'Benutzer angelegt');
    };
    const rename = (u: User) => {
        const newName = window.prompt('Neuer Name:', u.name);
        if (newName && newName !== u.name) run(() => api.patch(`/api/users/${u.id}`, { name: newName }));
    };
    const resetPin = (u: User) => {
        const newPin = window.prompt(`Neuer PIN für ${u.name} (4–8 Ziffern):`);
        if (newPin) run(() => api.post(`/api/users/${u.id}/pin`, { pin: newPin }), 'PIN gesetzt');
    };
    const toggleAdmin = (u: User) => run(() => api.patch(`/api/users/${u.id}`, { is_admin: !u.is_admin }));
    const remove = (u: User) => {
        if (window.confirm(`${u.name} löschen? Bewerbungen und Ereignisse bleiben erhalten.`)) {
            run(() => api.delete(`/api/users/${u.id}`), 'Benutzer gelöscht');
        }
    };

    return (
        <section className={`${CARD} space-y-3`}>
            <h2 className="text-lg font-bold">Benutzer</h2>
            <ul className="divide-y divide-slate-800">
                {users.map((u) => (
                    <li key={u.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-sm">
                        <span className="mr-auto font-semibold">
                            {u.name}
                            {u.is_admin && <span className="ml-2 text-xs text-amber-300">Admin</span>}
                            <span className="ml-2 text-xs font-normal text-slate-500">{u.email ?? 'keine E-Mail'}</span>
                        </span>
                        <button type="button" onClick={() => rename(u)} className="text-slate-300 hover:underline">
                            Umbenennen
                        </button>
                        <button type="button" onClick={() => resetPin(u)} className="text-slate-300 hover:underline">
                            PIN setzen
                        </button>
                        <button type="button" onClick={() => toggleAdmin(u)} className="text-slate-300 hover:underline">
                            {u.is_admin ? 'Admin entziehen' : 'Zum Admin machen'}
                        </button>
                        {u.id !== me?.id && (
                            <button type="button" onClick={() => remove(u)} className="text-red-300 hover:underline">
                                Löschen
                            </button>
                        )}
                    </li>
                ))}
            </ul>
            <form onSubmit={add} className="flex flex-wrap items-center gap-2">
                <input
                    placeholder="Name"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className={`${FIELD} min-w-32 flex-1`}
                />
                <div className="w-44">
                    <PinInput id="new-user-pin" value={pin} onChange={setPin} placeholder="PIN" autoComplete="new-password" />
                </div>
                <label className="flex items-center gap-1 text-sm">
                    <input type="checkbox" checked={isAdmin} onChange={(e) => setIsAdmin(e.target.checked)} />
                    Admin
                </label>
                <button type="submit" disabled={!name.trim() || pin.length < 4} className={BUTTON}>
                    Hinzufügen
                </button>
            </form>
        </section>
    );
}
