import { useEffect } from 'react';

const APP = 'Bewerbungen';

// The tab's title names the page ("Unterlagen · Bewerbungen"), so a screen reader and the list of tabs tell the pages
// apart; the overview is just "Bewerbungen" (accessibility review 2026-11-08)
export function usePageTitle(page: string | null) {
    useEffect(() => {
        document.title = page ? `${page} · ${APP}` : APP;
    }, [page]);
}
