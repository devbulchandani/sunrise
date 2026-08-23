// Sunrise API proxy — gives the HTTPS dashboard an HTTPS origin that
// forwards to the EC2 backend over HTTP (server-to-server, no mixed content).
const BACKEND = "http://52.23.202.227.sslip.io:8000";

export default {
  async fetch(request) {
    const url = new URL(request.url);
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
    out.set("Access-Control-Allow-Origin", "*");
    out.delete("content-security-policy");
    out.delete("x-frame-options");

    return new Response(response.body, {
      status: response.status,
      headers: out,
    });
  },
};
