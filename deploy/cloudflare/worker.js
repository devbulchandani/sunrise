// Sunrise API proxy — gives the HTTPS dashboard an HTTPS origin that
// forwards to the EC2 backend over HTTP (server-to-server, no mixed content).
const BACKEND = "http://52.7.157.152.sslip.io:8000";
const ALLOWED_ORIGINS = new Set([
  "https://sunrise-dashboard.pages.dev",
  "http://localhost:5173",
  "http://127.0.0.1:5173",
]);
const ALLOWED_METHODS = "GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS";
const ALLOWED_HEADERS = "Authorization, Content-Type, X-Admin-Token";

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const origin = request.headers.get("Origin");
    const allowedOrigin = origin && ALLOWED_ORIGINS.has(origin) ? origin : null;

    if (request.method === "OPTIONS") {
      if (!allowedOrigin) return new Response(null, { status: 403 });
      return new Response(null, {
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": allowedOrigin,
          "Access-Control-Allow-Methods": ALLOWED_METHODS,
          "Access-Control-Allow-Headers": ALLOWED_HEADERS,
          "Access-Control-Max-Age": "600",
          Vary: "Origin",
        },
      });
    }

    const upstream = BACKEND + url.pathname + url.search;

    const init = {
      method: request.method,
      headers: new Headers(request.headers),
      redirect: "follow",
    };
    // strip hop-by-hop / browser-only headers
    init.headers.delete("host");
    init.headers.delete("origin");
    init.headers.delete("referer");

    if (!["GET", "HEAD"].includes(request.method)) {
      init.body = await request.arrayBuffer();
    }

    const response = await fetch(upstream, init);
    const out = new Headers(response.headers);
    out.delete("Access-Control-Allow-Origin");
    out.delete("Access-Control-Allow-Credentials");
    out.append("Vary", "Origin");
    if (allowedOrigin) out.set("Access-Control-Allow-Origin", allowedOrigin);
    out.delete("content-security-policy");
    out.delete("x-frame-options");

    return new Response(response.body, {
      status: response.status,
      headers: out,
    });
  },
};
