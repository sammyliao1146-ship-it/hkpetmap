const API_ORIGIN = "https://hkpetmap.onrender.com";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/api/v1" || url.pathname.startsWith("/api/v1/")) {
      const upstream = new URL(request.url);
      upstream.protocol = "https:";
      upstream.hostname = new URL(API_ORIGIN).hostname;
      upstream.port = "";

      return fetch(new Request(upstream, request));
    }

    return env.ASSETS.fetch(request);
  },
};
