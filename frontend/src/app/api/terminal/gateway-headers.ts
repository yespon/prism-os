/** Preserve the caller's session and tenant through the terminal BFF. */
export function terminalGatewayHeaders(request: Request): Headers {
  const headers = new Headers({ "Content-Type": "application/json" });
  for (const name of ["cookie", "authorization", "x-tenant-id"]) {
    const value = request.headers.get(name);
    if (value !== null) headers.set(name, value);
  }
  return headers;
}
