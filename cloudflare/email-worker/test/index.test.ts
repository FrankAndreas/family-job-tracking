import { describe, expect, it, vi } from 'vitest';
import { deliver, type Env, type InboundMessage } from '../src/index';

const env: Env = {
    APP_URL: 'https://bewerbungen.example.ch/',
    INBOUND_SECRET: 's3cret',
    CF_ACCESS_CLIENT_ID: 'id.access',
    CF_ACCESS_CLIENT_SECRET: 'access-secret',
};

const RAW = 'Subject: Hallo\r\n\r\nText';

function message(forward = vi.fn(async () => undefined)) {
    const setReject = vi.fn();
    const msg: InboundMessage = {
        from: 'hr@migros.ch',
        to: 'bewerbungen+abcd@example.ch',
        raw: new Response(RAW).body!,
        rawSize: RAW.length,
        setReject,
        forward,
    };
    return { msg, setReject, forward };
}

describe('deliver', () => {
    it('posts the raw mail with the secrets and the envelope recipient', async () => {
        const fetchMock = vi.fn(async () => new Response('{"status":"stored"}', { status: 200 }));
        const { msg, setReject } = message();
        await deliver(msg, env, fetchMock as unknown as typeof fetch);

        expect(fetchMock).toHaveBeenCalledOnce();
        const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
        expect(url).toBe('https://bewerbungen.example.ch/api/inbound');
        const headers = init.headers as Record<string, string>;
        expect(headers['X-Inbound-Secret']).toBe('s3cret');
        expect(headers['X-Envelope-To']).toBe('bewerbungen+abcd@example.ch');
        expect(headers['CF-Access-Client-Id']).toBe('id.access');
        expect(headers['CF-Access-Client-Secret']).toBe('access-secret');
        expect(init.redirect).toBe('manual');
        expect(new TextDecoder().decode(init.body as ArrayBuffer)).toBe(RAW);
        expect(setReject).not.toHaveBeenCalled();
    });

    // 302: Cloudflare Access redirects to its login page when the service token is wrong
    it.each([500, 401, 302])('rejects the mail when the app answers %i', async (status) => {
        const { msg, setReject } = message();
        await deliver(msg, env, (async () => new Response(null, { status })) as unknown as typeof fetch);
        expect(setReject).toHaveBeenCalledOnce();
    });

    it('rejects the mail when the app is unreachable', async () => {
        const { msg, setReject } = message();
        const failing = async () => {
            throw new Error('connection refused');
        };
        await deliver(msg, env, failing as unknown as typeof fetch);
        expect(setReject).toHaveBeenCalledWith(expect.stringContaining('nicht erreichbar'));
    });

    it('rejects the mail without calling out when APP_URL is not set', async () => {
        const fetchMock = vi.fn();
        const { msg, setReject } = message();
        await deliver(msg, { ...env, APP_URL: '' }, fetchMock as unknown as typeof fetch);
        expect(fetchMock).not.toHaveBeenCalled();
        expect(setReject).toHaveBeenCalledWith(expect.stringContaining('APP_URL'));
    });

    describe('with a fallback address', () => {
        const withFallback: Env = { ...env, FALLBACK_ADDRESS: 'papa@example.ch' };
        const down = (async () => {
            throw new Error('connection refused');
        }) as unknown as typeof fetch;

        it.each([
            ['unreachable', down],
            ['answering 502', (async () => new Response(null, { status: 502 })) as unknown as typeof fetch],
        ])('forwards instead of rejecting when the app is %s', async (_case, fetchImpl) => {
            const { msg, setReject, forward } = message();
            await deliver(msg, withFallback, fetchImpl);
            expect(setReject).not.toHaveBeenCalled();
            expect(forward).toHaveBeenCalledOnce();
            const [to, headers] = forward.mock.calls[0] as unknown as [string, Headers];
            expect(to).toBe('papa@example.ch');
            expect(headers.get('X-Family-Jobs-Error')).toContain('Family Job Tracking');
        });

        it('does not forward a mail the app took', async () => {
            const { msg, setReject, forward } = message();
            await deliver(msg, withFallback, (async () => new Response('{}', { status: 200 })) as unknown as typeof fetch);
            expect(forward).not.toHaveBeenCalled();
            expect(setReject).not.toHaveBeenCalled();
        });

        it('rejects the mail when forwarding fails too', async () => {
            const { msg, setReject } = message(
                vi.fn(async () => {
                    throw new Error('destination address not verified');
                }),
            );
            await deliver(msg, withFallback, down);
            expect(setReject).toHaveBeenCalledWith(expect.stringContaining('Weiterleitung fehlgeschlagen'));
        });
    });
});
