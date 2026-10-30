import { useCallback, useEffect, useState } from 'react';
import api, { errorMessage } from '../../api';
import { useToast } from '../../ToastContext';
import type { User } from '../../types';
import { CARD } from '../../ui';

// The people come from the family hub (spec 2026-10-30): added, renamed and given access there; a parent there is
// Admin here. Someone the hub no longer lists is hidden here until an admin deletes them
export default function UserManager() {
    const toast = useToast();
    const [users, setUsers] = useState<User[]>([]);
    const [removed, setRemoved] = useState<User[]>([]);

    // Bumping the version reloads the lists after a change
    const [version, setVersion] = useState(0);
    const load = useCallback(() => setVersion((v) => v + 1), []);

    useEffect(() => {
        Promise.all([api.get<User[]>('/api/users'), api.get<User[]>('/api/users/removed')])
            .then(([active, hidden]) => {
                setUsers(active.data);
                setRemoved(hidden.data);
            })
            .catch((e) => toast(errorMessage(e)));
    }, [version, toast]);

    const remove = async (u: User) => {
        if (!window.confirm(`Daten von ${u.name} löschen? Bewerbungen und Ereignisse bleiben erhalten.`)) return;
        try {
            await api.delete(`/api/users/${u.id}`);
            toast('Benutzer gelöscht', 'success');
            load();
        } catch (e) {
            toast(errorMessage(e));
        }
    };

    return (
        <section className={`${CARD} space-y-3`}>
            <h2 className="text-lg font-bold">Benutzer</h2>
            <p className="text-sm text-slate-400">
                Die Familie kommt aus dem Familien-Hub: Personen dort hinzufügen, umbenennen und freischalten. Eltern sind
                hier Admin.
            </p>
            <ul className="divide-y divide-slate-800">
                {users.map((u) => (
                    <li key={u.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-sm">
                        <span className="mr-auto font-semibold">
                            {u.name}
                            {u.is_admin && <span className="ml-2 text-xs text-amber-300">Admin</span>}
                            <span className="ml-2 text-xs font-normal text-slate-500">{u.email ?? 'keine E-Mail'}</span>
                        </span>
                    </li>
                ))}
            </ul>
            {removed.length > 0 && (
                <div className="space-y-2">
                    <h3 className="font-semibold">Im Familien-Hub entfernt</h3>
                    <ul className="divide-y divide-slate-800">
                        {removed.map((u) => (
                            <li key={u.id} className="flex flex-wrap items-center gap-x-3 py-2 text-sm">
                                <span className="mr-auto">{u.name}</span>
                                <button type="button" onClick={() => void remove(u)} className="text-red-300 hover:underline">
                                    Daten löschen
                                </button>
                            </li>
                        ))}
                    </ul>
                </div>
            )}
        </section>
    );
}
