// sw.js - Service Worker for Odoo SaaS Platform
const CACHE_NAME = "odoo-saas-v3";
const DYNAMIC_CACHE_NAME = "odoo-saas-dynamic-v3";
const OFFLINE_PAGE = "/offline.html";

// Core assets to cache during installation
const STATIC_ASSETS = [
  "/",
  "/static/css/style.css",
  "/static/js/app.js",
  "/static/js/style.js",
  "/static/img/kdoo-logo.png",
  "/static/img/favicon.ico",
  "/favicon.ico",
  "/login",
  "/register",
  "/dashboard",
  "/tenant/create",
  "/offline.html",
  "/manifest.json",
  // Bootstrap and FontAwesome from CDN (if used)
  "https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css",
  "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css",
];

// API endpoints that should use network-first strategy
const API_ENDPOINTS = ["/api/", "/billing/", "/tenant/", "/admin/", "/health"];

// Routes that should always be fetched from network (no caching)
const NETWORK_ONLY_ROUTES = [
  "/logout",
  "/api/tenant/",
  "/billing/webhook",
  "/billing/success",
  "/billing/cancel",
];

// Check if a request is for an API endpoint
const isApiRequest = (url) => {
  return API_ENDPOINTS.some((endpoint) => url.includes(endpoint));
};

// Check if a request should never be cached
const isNetworkOnlyRequest = (url) => {
  return NETWORK_ONLY_ROUTES.some((route) => url.includes(route));
};

// Check if request is for static assets
const isStaticAsset = (url) => {
  return (
    url.includes("/static/") ||
    url.includes(".css") ||
    url.includes(".js") ||
    url.includes(".png") ||
    url.includes(".jpg") ||
    url.includes(".svg") ||
    url.includes(".ico") ||
    url.includes(".woff") ||
    url.includes(".woff2")
  );
};

// Install event: Cache static assets
self.addEventListener("install", (event) => {
  console.log("Service Worker: Installing v3");

  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => {
        console.log("Service Worker: Caching static assets");
        return cache
          .addAll(
            STATIC_ASSETS.filter(
              (asset) => !asset.startsWith("http") // Only cache local assets during install
            )
          )
          .catch((error) => {
            console.error("Service Worker: Failed to cache asset", error);
            // Cache external assets individually to avoid blocking installation
            return Promise.allSettled(
              STATIC_ASSETS.filter((asset) => asset.startsWith("http")).map(
                (asset) =>
                  cache
                    .add(asset)
                    .catch((err) =>
                      console.warn(`Failed to cache ${asset}:`, err)
                    )
              )
            );
          });
      })
      .catch((error) => {
        console.error("Service Worker: Installation failed", error);
      })
  );

  // Skip waiting to activate immediately
  self.skipWaiting();
});

// Activate event: Clean up old caches
self.addEventListener("activate", (event) => {
  console.log("Service Worker: Activating v3");

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
        console.log("Service Worker: Activated and claimed clients");
        return self.clients.claim();
      })
      .catch((error) => {
        console.error("Service Worker: Activation failed", error);
      })
  );
});

// Fetch event: Handle requests with different strategies
self.addEventListener("fetch", (event) => {
  const requestUrl = new URL(event.request.url);
  const isSameOrigin = requestUrl.origin === self.location.origin;

  // Skip non-GET requests and different origins (except for CDN assets)
  if (event.request.method !== "GET") {
    return;
  }

  // Handle different origins (like CDN assets)
  if (
    !isSameOrigin &&
    !requestUrl.href.includes("cdn.jsdelivr.net") &&
    !requestUrl.href.includes("cdnjs.cloudflare.com")
  ) {
    return;
  }

  // Network-only requests (never cache)
  if (isNetworkOnlyRequest(requestUrl.pathname)) {
    event.respondWith(fetch(event.request));
    return;
  }

  // API requests: Network-first with cache fallback
  if (isApiRequest(requestUrl.pathname) && isSameOrigin) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          // Only cache successful responses
          if (response.status === 200) {
            const responseClone = response.clone();
            caches.open(DYNAMIC_CACHE_NAME).then((cache) => {
              cache.put(event.request, responseClone);
            });
          }
          return response;
        })
        .catch(() => {
          // Return cached version if network fails
          return caches.match(event.request).then((cachedResponse) => {
            if (cachedResponse) {
              return cachedResponse;
            }

            // Return offline response for API requests
            return new Response(
              JSON.stringify({
                error: "Network unavailable",
                message:
                  "This data may be outdated. Please try again when online.",
                offline: true,
                timestamp: new Date().toISOString(),
              }),
              {
                status: 503,
                headers: {
                  "Content-Type": "application/json",
                  "Cache-Control": "no-cache",
                },
              }
            );
          });
        })
    );
    return;
  }

  // Static assets: Cache-first strategy
  if (isStaticAsset(requestUrl.pathname) || !isSameOrigin) {
    event.respondWith(
      caches.match(event.request).then((cachedResponse) => {
        if (cachedResponse) {
          // Serve from cache, but also fetch in background to update cache
          fetch(event.request)
            .then((networkResponse) => {
              if (networkResponse.status === 200) {
                caches.open(CACHE_NAME).then((cache) => {
                  cache.put(event.request, networkResponse.clone());
                });
              }
            })
            .catch(() => {
              // Ignore network errors for background updates
            });

          return cachedResponse;
        }

        // Not in cache, fetch from network
        return fetch(event.request)
          .then((networkResponse) => {
            if (networkResponse.status === 200) {
              const responseClone = networkResponse.clone();
              caches.open(CACHE_NAME).then((cache) => {
                cache.put(event.request, responseClone);
              });
            }
            return networkResponse;
          })
          .catch(() => {
            return new Response("Asset not available offline", {
              status: 404,
              headers: { "Content-Type": "text/plain" },
            });
          });
      })
    );
    return;
  }

  // HTML pages: Network-first with cache fallback
  event.respondWith(
    fetch(event.request)
      .then((networkResponse) => {
        // Cache successful HTML responses
        if (
          networkResponse.status === 200 &&
          event.request.headers.get("Accept")?.includes("text/html")
        ) {
          const responseClone = networkResponse.clone();
          caches.open(DYNAMIC_CACHE_NAME).then((cache) => {
            cache.put(event.request, responseClone);
          });
        }
        return networkResponse;
      })
      .catch(() => {
        // Try to serve from cache
        return caches.match(event.request).then((cachedResponse) => {
          if (cachedResponse) {
            return cachedResponse;
          }

          // For navigation requests, serve offline page
          if (event.request.mode === "navigate") {
            return caches.match(OFFLINE_PAGE).then((offlinePage) => {
              return (
                offlinePage ||
                new Response(
                  `<!DOCTYPE html>
                <html>
                <head>
                  <title>Offline - Odoo SaaS Platform</title>
                  <meta name="viewport" content="width=device-width, initial-scale=1">
                  <style>
                    body { 
                      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
                      display: flex; 
                      align-items: center; 
                      justify-content: center; 
                      min-height: 100vh; 
                      margin: 0;
                      background: linear-gradient(135deg, #714b67 0%, #4a90e2 100%);
                      color: white;
                      text-align: center;
                    }
                    .offline-container {
                      max-width: 400px;
                      padding: 2rem;
                    }
                    .offline-icon {
                      font-size: 4rem;
                      margin-bottom: 1rem;
                      opacity: 0.8;
                    }
                    .retry-button {
                      background: rgba(255,255,255,0.2);
                      border: 2px solid rgba(255,255,255,0.3);
                      color: white;
                      padding: 12px 24px;
                      border-radius: 8px;
                      cursor: pointer;
                      margin-top: 1rem;
                      transition: all 0.3s ease;
                    }
                    .retry-button:hover {
                      background: rgba(255,255,255,0.3);
                      transform: translateY(-2px);
                    }
                  </style>
                </head>
                <body>
                  <div class="offline-container">
                    <div class="offline-icon">☁️</div>
                    <h1>You're Offline</h1>
                    <p>Sorry, you need an internet connection to access this page. Please check your connection and try again.</p>
                    <button class="retry-button" onclick="window.location.reload()">
                      🔄 Try Again
                    </button>
                  </div>
                </body>
                </html>`,
                  {
                    status: 200,
                    headers: { "Content-Type": "text/html" },
                  }
                )
              );
            });
          }

          return new Response("Page not available offline", {
            status: 404,
            headers: { "Content-Type": "text/plain" },
          });
        });
      })
  );
});

// Handle background sync for when connection is restored
self.addEventListener("sync", (event) => {
  console.log("Service Worker: Background sync triggered", event.tag);

  if (event.tag === "background-sync") {
    event.waitUntil(
      // Perform background sync tasks
      syncData()
    );
  }
});

// Handle push notifications (if implemented later)
self.addEventListener("push", (event) => {
  console.log("Service Worker: Push message received", event);

  const options = {
    body: event.data
      ? event.data.text()
      : "New notification from Odoo SaaS Platform",
    icon: "/static/img/kdoo-logo.png",
    badge: "/static/img/favicon.ico",
    vibrate: [200, 100, 200],
    data: {
      dateOfArrival: Date.now(),
      primaryKey: 1,
    },
    actions: [
      {
        action: "explore",
        title: "Open Dashboard",
        icon: "/static/img/kdoo-logo.png",
      },
      {
        action: "close",
        title: "Close",
        icon: "/static/img/favicon.ico",
      },
    ],
  };

  event.waitUntil(
    self.registration.showNotification("Odoo SaaS Platform", options)
  );
});

// Handle notification clicks
self.addEventListener("notificationclick", (event) => {
  console.log("Service Worker: Notification click received", event);

  event.notification.close();

  if (event.action === "explore") {
    event.waitUntil(clients.openWindow("/dashboard"));
  } else if (event.action === "close") {
    // Just close the notification
  } else {
    // Default action - open the app
    event.waitUntil(clients.openWindow("/dashboard"));
  }
});

// Background sync function
async function syncData() {
  try {
    // Implement background sync logic here
    // For example: sync offline actions, update cached data, etc.
    console.log("Service Worker: Performing background sync");

    // Clear old cache entries
    const cache = await caches.open(DYNAMIC_CACHE_NAME);
    const requests = await cache.keys();
    const oneHourAgo = Date.now() - 60 * 60 * 1000;

    for (const request of requests) {
      const response = await cache.match(request);
      if (response) {
        const dateHeader = response.headers.get("date");
        if (dateHeader && new Date(dateHeader).getTime() < oneHourAgo) {
          await cache.delete(request);
          console.log("Service Worker: Deleted old cache entry", request.url);
        }
      }
    }

    return Promise.resolve();
  } catch (error) {
    console.error("Service Worker: Background sync failed", error);
    return Promise.reject(error);
  }
}

// Log service worker lifecycle events
console.log("Service Worker: Script loaded");
