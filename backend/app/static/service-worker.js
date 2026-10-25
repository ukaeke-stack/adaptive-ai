const CACHE_NAME = "adaptive-ai-shell-v1";
const APP_SHELL = ["/app/"];
self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(APP_SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", event => {
  const request = event.request;
  const url = new URL(request.url);
  // Never cache API calls, authentication responses, or user data.
  if (url.origin !== self.location.origin || url.pathname.startsWith("/v1/") || request.method !== "GET") return;
  if (request.mode === "navigate" && url.pathname.startsWith("/app")) {
    event.respondWith(fetch(request).then(response => {
      if (response.ok) caches.open(CACHE_NAME).then(cache => cache.put("/app/", response.clone()));
      return response;
    }).catch(() => caches.match("/app/")));
  }
});
