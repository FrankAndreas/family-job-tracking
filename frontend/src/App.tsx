import type { ReactElement } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from './AuthContext';
import Layout from './components/Layout';
import Login from './pages/Login';
import Overview from './pages/Overview';
import { ToastProvider } from './ToastContext';

function RequireAuth({ children }: { children: ReactElement }) {
    const { user, isLoading } = useAuth();
    if (isLoading) return <p className="p-6 text-slate-400">Laden…</p>;
    return user ? children : <Navigate to="/login" replace />;
}

export default function App() {
    return (
        <ToastProvider>
            <AuthProvider>
                <BrowserRouter>
                    <Routes>
                        <Route path="/login" element={<Login />} />
                        <Route
                            element={
                                <RequireAuth>
                                    <Layout />
                                </RequireAuth>
                            }
                        >
                            <Route index element={<Overview />} />
                        </Route>
                        <Route path="*" element={<Navigate to="/" replace />} />
                    </Routes>
                </BrowserRouter>
            </AuthProvider>
        </ToastProvider>
    );
}
