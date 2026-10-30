import type { ReactElement } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from './AuthContext';
import Layout from './components/Layout';
import ApplicationPage from './pages/ApplicationPage';
import Documents from './pages/Documents';
import Inbox from './pages/Inbox';
import NoAccess from './pages/NoAccess';
import Overview from './pages/Overview';
import SettingsPage from './pages/SettingsPage';
import Suggestions from './pages/Suggestions';
import { ToastProvider } from './ToastContext';

// Not logged in: the API's 401 has already sent the browser to the family hub's login
function RequireAuth({ children }: { children: ReactElement }) {
    const { state } = useAuth();
    if (state === 'no_access') return <NoAccess />;
    if (state === 'hub_unavailable') return <NoAccess hubDown />;
    if (state !== 'in') return <p className="p-6 text-slate-400">Laden…</p>;
    return children;
}

export default function App() {
    return (
        <ToastProvider>
            <AuthProvider>
                <BrowserRouter>
                    <Routes>
                        <Route
                            element={
                                <RequireAuth>
                                    <Layout />
                                </RequireAuth>
                            }
                        >
                            <Route index element={<Overview />} />
                            <Route path="bewerbungen/:id" element={<ApplicationPage />} />
                            <Route path="vorschlaege" element={<Suggestions />} />
                            <Route path="posteingang" element={<Inbox />} />
                            <Route path="unterlagen" element={<Documents />} />
                            <Route path="einstellungen" element={<SettingsPage />} />
                        </Route>
                        <Route path="*" element={<Navigate to="/" replace />} />
                    </Routes>
                </BrowserRouter>
            </AuthProvider>
        </ToastProvider>
    );
}
