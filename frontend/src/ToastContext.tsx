import { createContext, useCallback, useContext, useState, type ReactNode } from 'react';

type ToastKind = 'error' | 'success';
type ShowToast = (text: string, kind?: ToastKind) => void;

interface Toast {
    id: number;
    text: string;
    kind: ToastKind;
}

const ToastContext = createContext<ShowToast>(() => {});

// How long a success message stays; an error stays until closed, so nobody misses it (accessibility review 2026-11-08)
const SUCCESS_MS = 5000;

export function ToastProvider({ children }: { children: ReactNode }) {
    const [toasts, setToasts] = useState<Toast[]>([]);

    const close = useCallback((id: number) => setToasts((current) => current.filter((t) => t.id !== id)), []);

    const show = useCallback<ShowToast>(
        (text, kind = 'error') => {
            const id = Date.now() + Math.random();
            // The same message once: a failing request repeated doesn't pile up copies
            setToasts((current) =>
                current.some((t) => t.kind === kind && t.text === text) ? current : [...current, { id, text, kind }],
            );
            if (kind === 'success') setTimeout(() => close(id), SUCCESS_MS);
        },
        [close],
    );

    const errors = toasts.filter((t) => t.kind === 'error');
    const successes = toasts.filter((t) => t.kind === 'success');

    // Both regions are always there: screen readers announce what is added to them (a region that appears together
    // with its text is missed by some). Errors as an alert, interrupting; successes politely
    return (
        <ToastContext.Provider value={show}>
            {children}
            <div className="fixed inset-x-4 bottom-4 z-50 flex flex-col items-center gap-2">
                <div role="alert" className="flex flex-col items-center gap-2">
                    {errors.map((t) => (
                        <div
                            key={t.id}
                            className="flex items-start gap-3 rounded-lg bg-red-700 py-2 pl-4 pr-2 text-sm text-white shadow-lg"
                        >
                            <span className="py-1">{t.text}</span>
                            <button
                                type="button"
                                onClick={() => close(t.id)}
                                aria-label="Meldung schliessen"
                                className="min-h-8 min-w-8 rounded hover:bg-red-800"
                            >
                                ✕
                            </button>
                        </div>
                    ))}
                </div>
                <div role="status" className="flex flex-col items-center gap-2">
                    {successes.map((t) => (
                        <div key={t.id} className="rounded-lg bg-emerald-700 px-4 py-2 text-sm text-white shadow-lg">
                            {t.text}
                        </div>
                    ))}
                </div>
            </div>
        </ToastContext.Provider>
    );
}

// eslint-disable-next-line react-refresh/only-export-components -- the hook belongs with its provider
export const useToast = () => useContext(ToastContext);
