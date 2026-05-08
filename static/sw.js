/* CINEMAWAY - Service Worker (Push Notifications) */
const CACHE_NAME = 'cinemaway-v1';

self.addEventListener('install', e => {
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(clients.claim());
});

/* Réception d'une notification push */
self.addEventListener('push', e => {
  let data = { title: 'CINEMAWAY', body: 'Nouvelle notification' };
  try { data = e.data.json(); } catch {}

  e.waitUntil(
    self.registration.showNotification(data.title || 'CINEMAWAY', {
      body: data.body || '',
      icon: '/static/icon.png',
      badge: '/static/badge.png',
      data: { url: data.url || '/' },
      vibrate: [200, 100, 200],
      actions: [{ action: 'open', title: 'Voir' }]
    })
  );
});

/* Clic sur la notification */
self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = e.notification.data?.url || '/';
  e.waitUntil(
    clients.matchAll({ type: 'window' }).then(list => {
      for (const client of list) {
        if (client.url === url && 'focus' in client) return client.focus();
      }
      if (clients.openWindow) return clients.openWindow(url);
    })
  );
});
