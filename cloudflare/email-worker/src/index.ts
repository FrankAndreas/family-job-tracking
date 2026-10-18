export interface Env {
    APP_URL: string;
    INBOUND_SECRET: string;
    CF_ACCESS_CLIENT_ID: string;
    CF_ACCESS_CLIENT_SECRET: string;
    // Optional: a verified Email Routing destination that gets the mail when the app can't take it
    FALLBACK_ADDRESS?: string;
}

// The parts of Cloudflare's ForwardableEmailMessage the worker uses
export interface InboundMessage {
    readonly from: string;
    readonly to: string;
    readonly raw: ReadableStream<Uint8Array>;
    readonly rawSize: number;
    setReject(reason: string): void;
    forward(rcptTo: string, headers?: Headers): Promise<unknown>;
}

/**
 * The app couldn't take the mail: forward it to the fallback address if there is one,
 * otherwise reject it, so the sender gets a bounce instead of the mail being lost silently.
 */
async function giveUp(message: InboundMessage, env: Env, reason: string): Promise<void> {
    if (env.FALLBACK_ADDRESS) {
        try {
            await message.forward(env.FALLBACK_ADDRESS, new Headers({ 'X-Family-Jobs-Error': reason }));
            return;
        } catch (error) {
            reason = `${reason}; Weiterleitung fehlgeschlagen: ${String(error)}`;
        }
    }
    message.setReject(reason);
}

/** Post the raw mail to the app; if it doesn't accept it, give up on it (see giveUp). */
export async function deliver(message: InboundMessage, env: Env, fetchImpl: typeof fetch = fetch): Promise<void> {
    if (!env.APP_URL) {
        await giveUp(message, env, 'Family Job Tracking: APP_URL ist im Worker nicht gesetzt');
        return;
    }
    const body = await new Response(message.raw).arrayBuffer();
    let response: Response;
    try {
        response = await fetchImpl(`${env.APP_URL.replace(/\/+$/, '')}/api/inbound`, {
            method: 'POST',
            headers: {
                'Content-Type': 'message/rfc822',
                'X-Inbound-Secret': env.INBOUND_SECRET,
                // A BCC'd +tag address appears in no header, only in the envelope
                'X-Envelope-To': message.to,
                'CF-Access-Client-Id': env.CF_ACCESS_CLIENT_ID,
                'CF-Access-Client-Secret': env.CF_ACCESS_CLIENT_SECRET,
            },
            body,
            // Cloudflare Access answers a bad service token with a redirect to its login page
            redirect: 'manual',
        });
    } catch (error) {
        await giveUp(message, env, `Family Job Tracking nicht erreichbar: ${String(error)}`);
        return;
    }
    if (!response.ok) {
        await giveUp(message, env, `Family Job Tracking hat die Mail nicht angenommen (HTTP ${response.status})`);
    }
}

export default {
    async email(message: InboundMessage, env: Env): Promise<void> {
        await deliver(message, env);
    },
};
