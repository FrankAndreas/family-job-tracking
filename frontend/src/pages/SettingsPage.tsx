import { useState } from 'react';
import { downloadFile, errorMessage } from '../api';
import { useAuth } from '../AuthContext';
import AppSettingsForm from '../components/settings/AppSettingsForm';
import IntegrationCards from '../components/settings/IntegrationCards';
import MyAccount from '../components/settings/MyAccount';
import UserManager from '../components/settings/UserManager';
import { useToast } from '../ToastContext';
import { BUTTON_SECONDARY, CARD } from '../ui';

export default function SettingsPage() {
    const { user } = useAuth();
    const toast = useToast();
    // Bumped after saving the app settings, so the integration cards reload (e.g. the inbound address warning)
    const [integrationsVersion, setIntegrationsVersion] = useState(0);
    const [exporting, setExporting] = useState(false);

    const exportData = async () => {
        setExporting(true);
        try {
            await downloadFile('/api/export', 'bewerbungen-export.zip');
        } catch (e) {
            toast(errorMessage(e, 'Export fehlgeschlagen'));
        } finally {
            setExporting(false);
        }
    };

    return (
        <div className="space-y-6">
            <h1 className="text-2xl font-bold">Einstellungen</h1>
            <MyAccount />
            <IntegrationCards key={integrationsVersion} />
            {user?.is_admin && (
                <>
                    <AppSettingsForm onSaved={() => setIntegrationsVersion((v) => v + 1)} />
                    <UserManager />
                </>
            )}
            <section className={`${CARD} space-y-2`}>
                <h2 className="text-lg font-bold">Daten exportieren</h2>
                <p className="text-sm text-slate-400">
                    Alle Bewerbungen, Ereignisse und Mails als CSV, dazu alle Dateien, in einem ZIP.
                </p>
                <button type="button" disabled={exporting} onClick={exportData} className={BUTTON_SECONDARY}>
                    {exporting ? 'Export läuft…' : 'ZIP herunterladen'}
                </button>
            </section>
        </div>
    );
}
