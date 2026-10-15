import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import api from '../api';
import { useAuth } from '../AuthContext';
import type { Dashboard, Integrations } from '../types';

const linkClass = ({ isActive }: { isActive: boolean }) =>
    `rounded-lg px-3 py-2 text-sm ${isActive ? 'bg-slate-700 text-white' : 'text-slate-300 hover:text-white'}`;

export default function Layout() {
    const { user, logout } = useAuth();
    const location = useLocation();
    const [inboxCount, setInboxCount] = useState(0);
    const [integrationError, setIntegrationError] = useState(false);

    // Refresh the badges whenever the page changes
    useEffect(() => {
        let cancelled = false;
        Promise.all([api.get<Dashboard>('/api/dashboard'), api.get<Integrations>('/api/integrations')])
            .then(([dashboard, integrations]) => {
                if (cancelled) return;
                setInboxCount(dashboard.data.inbox_count);
                setIntegrationError(
                    integrations.data.inbound.state === 'error' || integrations.data.reminders.state === 'error',
                );
            })
            .catch(() => {});
        return () => {
            cancelled = true;
        };
    }, [location.pathname]);

    return (
        <div className="min-h-screen">
            <header className="sticky top-0 z-10 border-b border-slate-800 bg-slate-900/90 backdrop-blur">
                <div className="mx-auto flex max-w-4xl flex-wrap items-center gap-2 px-4 py-3">
                    <span className="mr-auto font-bold">Bewerbungen</span>
                    <nav className="flex gap-1">
                        <NavLink to="/" end className={linkClass}>
                            Übersicht
                        </NavLink>
                        <NavLink to="/posteingang" className={linkClass}>
                            Posteingang
                            {inboxCount > 0 && (
                                <span className="ml-1 rounded-full bg-blue-600 px-2 text-xs text-white">{inboxCount}</span>
                            )}
                        </NavLink>
                        <NavLink to="/einstellungen" className={linkClass}>
                            Einstellungen
                            {integrationError && (
                                <span
                                    className="ml-1 inline-block h-2 w-2 rounded-full bg-red-500"
                                    title="Eine Integration meldet einen Fehler"
                                />
                            )}
                        </NavLink>
                    </nav>
                    <button type="button" onClick={logout} className="text-sm text-slate-400 hover:text-white">
                        {user?.name} abmelden
                    </button>
                </div>
            </header>
            <main className="mx-auto max-w-4xl px-4 py-6">
                <Outlet />
            </main>
        </div>
    );
}
