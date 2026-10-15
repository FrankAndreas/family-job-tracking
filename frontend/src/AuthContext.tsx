import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import api from './api';
import type { User } from './types';

interface AuthContextType {
    user: User | null;
    isLoading: boolean;
    login: (name: string, pin: string) => Promise<void>;
    logout: () => void;
    refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
    const [user, setUser] = useState<User | null>(null);
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
        const checkAuth = async () => {
            if (localStorage.getItem('token')) {
                try {
                    setUser((await api.get<User>('/api/me')).data);
                } catch {
                    localStorage.removeItem('token');
                }
            }
            setIsLoading(false);
        };
        checkAuth();
    }, []);

    // Reload the current user after their settings change on the server
    const refreshUser = async () => {
        setUser((await api.get<User>('/api/me')).data);
    };

    const login = async (name: string, pin: string) => {
        const response = await api.post<{ access_token: string }>('/api/token', { name, pin });
        localStorage.setItem('token', response.data.access_token);
        await refreshUser();
    };

    const logout = () => {
        localStorage.removeItem('token');
        setUser(null);
    };

    return (
        <AuthContext.Provider value={{ user, isLoading, login, logout, refreshUser }}>{children}</AuthContext.Provider>
    );
};

// eslint-disable-next-line react-refresh/only-export-components -- the hook belongs with its provider
export const useAuth = () => {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
};
