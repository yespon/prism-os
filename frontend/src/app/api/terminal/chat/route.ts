import { terminalGatewayHeaders } from "../gateway-headers";

const gatewayUrl = process.env.GATEWAY_URL ?? 'http://localhost:8001';

export async function POST(req: Request) {
  const body = await req.json();

  try {
    // Sanitize body: replace null/undefined with empty strings for string fields
    const sanitizedBody = {
      ...body,
      terminal_session_id: body.terminal_session_id ?? '',
      asset_id: body.asset_id ?? '',
    };

    const res = await fetch(`${gatewayUrl}/api/v1/terminal/invoke`, {
      method: 'POST',
      headers: terminalGatewayHeaders(req),
      body: JSON.stringify(sanitizedBody),
    });

    if (!res.ok) {
      const errText = await res.text();
      return new Response(`[SYSTEM ERROR] Failed to invoke agent. Status ${res.status}: ${errText}`, { status: res.status });
    }

    // Proxy the SSE stream
    return new Response(res.body, {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no' }
    });
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    return new Response(`[SYSTEM ERROR] ${message}`, { status: 500 });
  }
}
