import { createContext, useCallback, useContext, useState, type ReactNode } from 'react';

type ToastKind = 'error' | 'success';
type ShowToast = (text: string, kind?: ToastKind) => void;

interface Toast {
    id: number;
    text: string;
    kind: ToastKind;
}

const ToastContext = createContext<ShowToast>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
    const [toasts, setToasts] = useState<Toast[]>([]);

    const show = useCallback<ShowToast>((text, kind = 'error') => {
        const id = Date.now() + Math.random();
        setToasts((current) => [...current, { id, text, kind }]);
        setTimeout(() => setToasts((current) => current.filter((t) => t.id !== id)), 5000);
    }, []);

    return (
        <ToastContext.Provider value={show}>
            {children}
            <div className="fixed inset-x-4 bottom-4 z-50 flex flex-col items-center gap-2">
                {toasts.map((t) => (
                    <div
                        key={t.id}
                        role="status"
                        className={`rounded-lg px-4 py-2 text-sm text-white shadow-lg ${
                            t.kind === 'error' ? 'bg-red-700' : 'bg-emerald-700'
                        }`}
                    >
                        {t.text}
                    </div>
                ))}
            </div>
        </ToastContext.Provider>
    );
}

// eslint-disable-next-line react-refresh/only-export-components -- the hook belongs with its provider
export const useToast = () => useContext(ToastContext);
