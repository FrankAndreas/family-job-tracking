import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import api, { errorMessage } from '../api';
import { useAuth } from '../AuthContext';
import PinInput from '../components/PinInput';
import { useToast } from '../ToastContext';
import { BUTTON, CARD } from '../ui';

interface PublicUser {
    id: number;
    name: string;
}

export default function Login() {
    const { login } = useAuth();
    const navigate = useNavigate();
    const toast = useToast();
    const [users, setUsers] = useState<PublicUser[]>([]);
    const [name, setName] = useState('');
    const [pin, setPin] = useState('');
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        api.get<PublicUser[]>('/api/users/public')
            .then((response) => setUsers(response.data))
            .catch(() => toast('Benutzer konnten nicht geladen werden'));
    }, [toast]);

    const submit = async (e: FormEvent) => {
        e.preventDefault();
        setBusy(true);
        try {
            await login(name, pin);
            navigate('/');
        } catch (err) {
            toast(errorMessage(err, 'Anmeldung fehlgeschlagen'));
            setPin('');
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className="flex min-h-screen items-center justify-center p-4">
            <form onSubmit={submit} className={`${CARD} w-full max-w-sm space-y-4`}>
                <h1 className="text-center text-2xl font-bold">Bewerbungen</h1>
                <div className="grid grid-cols-2 gap-2">
                    {users.map((u) => (
                        <button
                            key={u.id}
                            type="button"
                            onClick={() => {
                                setName(u.name);
                                setPin('');
                            }}
                            className={`rounded-lg border p-3 font-semibold ${
                                name === u.name ? 'border-blue-400 bg-blue-600/30' : 'border-slate-700 hover:bg-slate-800'
                            }`}
                        >
                            {u.name}
                        </button>
                    ))}
                </div>
                {name && (
                    <>
                        <label htmlFor="pin" className="block text-sm text-slate-400">
                            PIN für {name}
                        </label>
                        <PinInput id="pin" value={pin} onChange={setPin} autoFocus />
                        <button type="submit" disabled={busy || pin.length < 4} className={`${BUTTON} w-full`}>
                            Anmelden
                        </button>
                    </>
                )}
            </form>
        </div>
    );
}
