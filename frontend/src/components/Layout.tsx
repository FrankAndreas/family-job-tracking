import { useEffect, useRef, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import api from '../api';
import { useAuth } from '../AuthContext';
import type { Dashboard, Integrations, LayoutContext } from '../types';

const linkClass = ({ isActive }: { isActive: boolean }) =>
    `rounded-lg px-3 py-2 text-sm ${isActive ? 'bg-slate-700 text-white' : 'text-slate-300 hover:text-white'}`;

export default function Layout() {
    const { user, logout } = useAuth();
    const location = useLocation();
    const [inboxCount, setInboxCount] = useState(0);
    const [suggestionCount, setSuggestionCount] = useState(0);
    const [integrationError, setIntegrationError] = useState(false);

    // Refresh the badges whenever the page changes
    useEffect(() => {
        let cancelled = false;
        Promise.all([api.get<Dashboard>('/api/dashboard'), api.get<Integrations>('/api/integrations')])
            .then(([dashboard, integrations]) => {
                if (cancelled) return;
                setInboxCount(dashboard.data.inbox_count);
                setSuggestionCount(dashboard.data.suggestion_count);
                setIntegrationError(
                    integrations.data.inbound.state === 'error' || integrations.data.reminders.state === 'error',
                );
            })
            .catch(() => {});
        return () => {
            cancelled = true;
        };
    }, [location.pathname]);

    // Moving to another page puts the focus on its heading: a screen reader reads where one is now, and Tab goes on
    // from there. Not on the first page shown. A page still loading gets it once its heading is there
    const main = useRef<HTMLElement>(null);
    const shown = useRef(location.pathname);
    useEffect(() => {
        if (shown.current === location.pathname || !main.current) return;
        shown.current = location.pathname;
        const area = main.current;
        const focusHeading = () => {
            const heading = area.querySelector('h1');
            if (!heading) return false;
            heading.tabIndex = -1;
            heading.focus();
            return true;
        };
        if (focusHeading()) return;
        const waiting = new MutationObserver(() => {
            if (focusHeading()) waiting.disconnect();
        });
        waiting.observe(area, { childList: true, subtree: true });
        return () => waiting.disconnect();
    }, [location.pathname]);

    return (
        <div className="min-h-screen">
            <header className="sticky top-0 z-10 border-b border-slate-800 bg-slate-900/90 backdrop-blur">
                <div className="mx-auto flex max-w-4xl flex-wrap items-center gap-2 px-4 py-3">
                    <span className="mr-auto font-bold">Bewerbungen</span>
                    {/* Wraps on a phone: five links are wider than its screen */}
                    <nav className="flex flex-wrap gap-1">
                        <NavLink to="/" end className={linkClass}>
                            Übersicht
                        </NavLink>
                        <NavLink to="/vorschlaege" className={linkClass}>
                            Vorschläge
                            {suggestionCount > 0 && (
                                <span className="ml-1 rounded-full bg-blue-600 px-2 text-xs text-white">
                                    {suggestionCount}
                                </span>
                            )}
                        </NavLink>
                        <NavLink to="/posteingang" className={linkClass}>
                            Posteingang
                            {inboxCount > 0 && (
                                <span className="ml-1 rounded-full bg-blue-600 px-2 text-xs text-white">{inboxCount}</span>
                            )}
                        </NavLink>
                        <NavLink to="/unterlagen" className={linkClass}>
                            Unterlagen
                        </NavLink>
                        <NavLink to="/einstellungen" className={linkClass}>
                            Einstellungen
                            {integrationError && (
                                <>
                                    <span
                                        aria-hidden="true"
                                        className="ml-1 inline-block h-2 w-2 rounded-full bg-red-500"
                                        title="Eine Integration meldet einen Fehler"
                                    />
                                    <span className="sr-only"> (eine Integration meldet einen Fehler)</span>
                                </>
                            )}
                        </NavLink>
                    </nav>
                    <button type="button" onClick={() => void logout()} className="text-sm text-slate-400 hover:text-white">
                        {user?.name} abmelden
                    </button>
                </div>
            </header>
            <main ref={main} className="mx-auto max-w-4xl px-4 py-6">
                <Outlet context={{ setInboxCount, setSuggestionCount } satisfies LayoutContext} />
            </main>
        </div>
    );
}
