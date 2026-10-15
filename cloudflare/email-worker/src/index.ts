export interface Env {
    APP_URL: string;
    INBOUND_SECRET: string;
    CF_ACCESS_CLIENT_ID: string;
    CF_ACCESS_CLIENT_SECRET: string;
}

// The parts of Cloudflare's ForwardableEmailMessage the worker uses
export interface InboundMessage {
    readonly from: string;
    readonly to: string;
    readonly raw: ReadableStream<Uint8Array>;
    readonly rawSize: number;
    setReject(reason: string): void;
}

/**
 * Post the raw mail to the app. If the app doesn't accept it, reject the mail,
 * so the sender gets a bounce instead of the mail being lost silently.
 */
export async function deliver(message: InboundMessage, env: Env, fetchImpl: typeof fetch = fetch): Promise<void> {
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
        message.setReject(`Family Job Tracking nicht erreichbar: ${String(error)}`);
        return;
    }
    if (!response.ok) {
        message.setReject(`Family Job Tracking hat die Mail nicht angenommen (HTTP ${response.status})`);
    }
}

export default {
    async email(message: InboundMessage, env: Env): Promise<void> {
        await deliver(message, env);
    },
};
