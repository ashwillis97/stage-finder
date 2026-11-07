// Counts outbound ticket-link clicks per venue. No cookies, no IP or user data stored.
const ALLOWED = ["https://findashow.co.uk", "https://www.findashow.co.uk"];
const BOT = /bot|crawl|spider|slurp|preview|headless|python|curl|wget/i;

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const origin = req.headers.get("Origin") || "";
    const cors = ALLOWED.includes(origin) ? { "Access-Control-Allow-Origin": origin, "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "Content-Type" } : {};
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
    if (req.method !== "POST" || url.pathname !== "/c") return new Response("Find a Show click counter", { status: 200 });
    if (!ALLOWED.includes(origin) || BOT.test(req.headers.get("User-Agent") || "")) return new Response(null, { status: 204, headers: cors });
    let d;
    try { d = JSON.parse((await req.text()).slice(0, 1000)); } catch (e) { return new Response(null, { status: 400, headers: cors }); }
    const clip = (x, n) => String(x == null ? "" : x).slice(0, n);
    const v = clip(d.v, 90), s = clip(d.s, 150), k = d.k === "tm" ? "tm" : "venue", p = clip(d.p, 100);
    if (!v) return new Response(null, { status: 400, headers: cors });
    env.CLICKS.writeDataPoint({ indexes: [v], blobs: [s, k, p], doubles: [1] });
    return new Response(null, { status: 204, headers: cors });
  },
};
