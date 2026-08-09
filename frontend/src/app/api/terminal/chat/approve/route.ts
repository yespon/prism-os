const gatewayUrl = process.env.GATEWAY_URL ?? 'http://localhost:8001';

export async function POST(req: Request) {
  const body = await req.json();
  const cookieHeader = req.headers.get('cookie') ?? '';

  try {
    const res = await fetch(`${gatewayUrl}/api/v1/terminal/approve`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(cookieHeader ? { Cookie: cookieHeader } : {}),
      },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const errText = await res.text();
      return new Response(`[SYSTEM ERROR] Failed to approve. Status ${res.status}: ${errText}`, { status: res.status });
    }

    return new Response(res.body, {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' }
    });
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    return new Response(`[SYSTEM ERROR] ${message}`, { status: 500 });
  }
}
