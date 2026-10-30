import { useAuth } from '../AuthContext';
import { BUTTON, CARD } from '../ui';

// Logged in at the family hub, but this app isn't ticked for the person; or the hub (or the NAS) doesn't answer
export default function NoAccess({ hubDown = false }: { hubDown?: boolean }) {
    const { logout, retry } = useAuth();
    return (
        <div className="mx-auto max-w-md p-6">
            <div className={`${CARD} space-y-4`}>
                <h1 className="text-xl font-bold">{hubDown ? 'Anmelden geht gerade nicht' : 'Kein Zugang'}</h1>
                <p className="text-slate-300">
                    {hubDown
                        ? 'Der Familien-Hub oder diese App antwortet gerade nicht (vielleicht startet das NAS neu).'
                        : 'Bitte einen Elternteil, dir im Familien-Hub Zugang zur Bewerbungs-App zu geben.'}
                </p>
                {hubDown ? (
                    <button type="button" className={BUTTON} onClick={retry}>Nochmals versuchen</button>
                ) : (
                    <button type="button" className={BUTTON} onClick={() => void logout()}>Als jemand anderes anmelden</button>
                )}
            </div>
        </div>
    );
}
