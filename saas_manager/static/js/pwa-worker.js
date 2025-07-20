// pwa-worker.js
const CACHE_NAME = "odoo-saas-cache-v2";
const DYNAMIC_CACHE_NAME = "odoo-saas-dynamic-cache-v2";
const OFFLINE_PAGE = "/offline.html";

// Core assets to cache during installation
const STATIC_ASSETS = [
  "/",
  "/static/css/style.css",
  "/static/js/app.js",
  "/static/img/kdoo-logo.png",
  "/static/img/favicon.ico",
  "/static/img/favicon.ico",
  "/login",
  "/register",
  "/dashboard",
  "/tenant/create",
  "/offline.html",
];

// API endpoints that should use network-first strategy
const API_ENDPOINTS = ["/api/", "/billing/", "/tenant/"];

// Check if a request is for an API endpoint
const isApiRequest = (url) => {
  return API_ENDPOINTS.some((endpoint) => url.includes(endpoint));
};

// Install event: Cache static assets
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => {
        console.log("Service Worker: Installing and caching static assets");
        return cache.addAll(STATIC_ASSETS).catch((error) => {
          console.error("Service Worker: Failed to cache asset", error);
        });
      })
      .catch((error) => {
        console.error("Service Worker: Installation failed", error);
      })
  );
  self.skipWaiting();
});

// Activate event: Clean up old caches
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((cacheNames) => {
        return Promise.all(
          cacheNames.map((cacheName) => {
            if (cacheName !== CACHE_NAME && cacheName !== DYNAMIC_CACHE_NAME) {
              console.log("Service Worker: Deleting old cache", cacheName);
              return caches.delete(cacheName);
            }
          })
        );
      })
      .then(() => {
        console.log("Service Worker: Activated");
        return self.clients.claim();
      })
      .catch((error) => {
        console.error("Service Worker: Activation failed", error);
      })
  );
});

// Fetch event: Handle requests
self.addEventListener("fetch", (event) => {
  const requestUrl = new URL(event.request.url);
  const isSameOrigin = requestUrl.origin === self.location.origin;

  // Handle API requests (network-first)
  if (isApiRequest(requestUrl.pathname) && isSameOrigin) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          if (response.status === 200) {
            caches.open(DYNAMIC_CACHE_NAME).then((cache) => {
              cache.put(event.request, response.clone());
            });
          }
          return response;
        })
        .catch(() => {
          return caches.match(event.request).then((cachedResponse) => {
            return (
              cachedResponse ||
              new Response(
                JSON.stringify({
                  error: "Network unavailable, using cached data or offline",
                }),
                { status: 503, headers: { "Content-Type": "application/json" } }
              )
            );
          });
        })
    );
    return;
  }

  // Handle static assets and pages (cache-first)
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      if (cachedResponse) {
        console.log("Service Worker: Serving from cache", event.request.url);
        return cachedResponse;
      }

      return fetch(event.request)
        .then((networkResponse) => {
          if (
            !networkResponse ||
            networkResponse.status !== 200 ||
            networkResponse.type !== "basic"
          ) {
            return networkResponse;
          }

          return caches.open(DYNAMIC_CACHE_NAME).then((cache) => {
            cache.put(event.request, networkResponse.clone());
            return networkResponse;
          });
        })
        .catch(() => {
          if (event.request.mode === "navigate") {
            console.log("Service Worker: Serving offline page");
            return caches.match(OFFLINE_PAGE);
          }
          return new Response("Resource not available offline", {
            status: 404,
          });
        });
    })
  );
});
