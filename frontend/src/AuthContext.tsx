import axios from 'axios';
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import api, { errorCode, goToHubLogout } from './api';
import type { User } from './types';

// in: logged in; no_access: logged in at the family hub, but not given this app; hub_unavailable: the hub (or the NAS)
// doesn't answer; away: on the way to the hub's login (the API's 401 sends the browser there)
export type AuthState = 'loading' | 'in' | 'no_access' | 'hub_unavailable' | 'away';

interface AuthContextType {
    user: User | null;
    state: AuthState;
    isLoading: boolean;
    logout: () => Promise<void>;
    refreshUser: () => Promise<void>;
    retry: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

// Who is logged in: the family hub's login (spec 2026-10-30); the backend asks the hub
export const AuthProvider = ({ children }: { children: ReactNode }) => {
    const [user, setUser] = useState<User | null>(null);
    const [state, setState] = useState<AuthState>('loading');
    // Raised by "Nochmals versuchen": asks the backend once more
    const [attempt, setAttempt] = useState(0);

    useEffect(() => {
        const check = async () => {
            try {
                setUser((await api.get<User>('/api/me')).data);
                setState('in');
            } catch (error) {
                const code = errorCode(error);
                const away = axios.isAxiosError(error) && error.response?.status === 401;
                setState(code === 'no_access' ? 'no_access' : away ? 'away' : 'hub_unavailable');
            }
        };
        void check();
    }, [attempt]);

    // Reload the current user after their settings change on the server
    const refreshUser = useCallback(async () => {
        setUser((await api.get<User>('/api/me')).data);
    }, []);

    const logout = useCallback(async () => {
        await goToHubLogout();
    }, []);

    const retry = useCallback(() => {
        setState('loading');
        setAttempt((n) => n + 1);
    }, []);

    return (
        <AuthContext.Provider value={{ user, state, isLoading: state === 'loading', logout, refreshUser, retry }}>
            {children}
        </AuthContext.Provider>
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
