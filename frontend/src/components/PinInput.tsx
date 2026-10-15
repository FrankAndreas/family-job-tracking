import { useState } from 'react';
import { INPUT } from '../ui';

interface PinInputProps {
    id: string;
    value: string;
    onChange: (pin: string) => void;
    placeholder?: string;
    autoComplete?: 'current-password' | 'new-password';
    autoFocus?: boolean;
}

// Masked PIN field with a show/hide toggle; only accepts digits (4–8)
export default function PinInput({
    id,
    value,
    onChange,
    placeholder = 'PIN',
    autoComplete = 'current-password',
    autoFocus = false,
}: PinInputProps) {
    const [show, setShow] = useState(false);
    return (
        <div className="relative">
            <input
                id={id}
                type={show ? 'text' : 'password'}
                inputMode="numeric"
                autoComplete={autoComplete}
                autoFocus={autoFocus}
                maxLength={8}
                value={value}
                onChange={(e) => {
                    if (/^\d*$/.test(e.target.value)) onChange(e.target.value);
                }}
                placeholder={placeholder}
                className={`${INPUT} pr-12 tracking-widest placeholder:tracking-normal`}
            />
            <button
                type="button"
                onClick={() => setShow(!show)}
                aria-label={show ? 'PIN verbergen' : 'PIN anzeigen'}
                className="absolute inset-y-0 right-0 px-3 text-slate-400 hover:text-white"
            >
                {show ? '🙈' : '👁️'}
            </button>
        </div>
    );
}
