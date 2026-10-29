import {isSecretProbe} from './request-security.js';
import {BUDGETED_PATHS,budgetedProxy} from './upstream-budget.js';

const API_ORIGIN = "https://hkpetmap.onrender.com";
const PUBLIC_TTLS = new Map([
  ["/api/v1/catalog", 300],
  ["/api/v1/data-version", 30],
  ["/api/v1/activities", 60],
  ["/api/v1/parking", 30],
]);

function browserResponse(response, request) {
  const etag = response.headers.get("ETag");
  const validators = (request.headers.get("If-None-Match") || "").split(",").map(v => v.trim().replace(/^W\//, ""));
  if (etag && (validators.includes(etag) || validators.includes("*"))) {
    return new Response(null, {status:304, headers:response.headers});
  }
  return response;
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (isSecretProbe(url.pathname)) {
      return new Response('Not found', {status:404, headers:{
        'Cache-Control':'private, no-store', 'X-Content-Type-Options':'nosniff',
        'Content-Type':'text/plain; charset=utf-8',
      }});
    }
    if (url.pathname === "/api/v1" || url.pathname.startsWith("/api/v1/")) {
      const upstream = new URL(request.url);
      upstream.protocol = "https:";
      upstream.hostname = new URL(API_ORIGIN).hostname;
      upstream.port = "";
      if(request.method==='POST'&&BUDGETED_PATHS.has(url.pathname))return budgetedProxy(request,upstream);
      const ttl = PUBLIC_TTLS.get(url.pathname);
      const eligible = request.method === "GET" && ttl &&
        !request.headers.has("Authorization") && !request.headers.has("Cookie") &&
        !url.searchParams.has("latitude") && !url.searchParams.has("longitude");
      const key = new Request(url.toString(), {method:"GET"});
      if (eligible) {
        const cached = await caches.default.match(key);
        if (cached) return browserResponse(cached, request);
      }
      const response = await fetch(new Request(upstream, request));
      const policy = response.headers.get("Cache-Control") || "";
      if (eligible && response.status === 200 &&
          response.headers.get("Content-Type")?.includes("application/json") &&
          !response.headers.has("Set-Cookie") && !/private|no-store/i.test(policy)) {
        const copy = new Response(response.clone().body, response);
        copy.headers.set("Cache-Control", `public, max-age=${ttl}`);
        copy.headers.delete("X-Request-ID"); // Never reuse an origin request ID for a different request.
        ctx.waitUntil(caches.default.put(key, copy).catch(() => {}));
      }
      return response;
    }
    return env.ASSETS.fetch(request);
  },
};
