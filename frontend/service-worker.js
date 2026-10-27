self.addEventListener('push', (event) => {
  let payload = {};
  if (event.data) {
    const text = event.data.text();
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { body: text };
    }
  }

  event.waitUntil(self.registration.showNotification(payload.title || 'AlphaMind price alert', {
    body: payload.body || 'A saved price alert condition was met.',
    tag: payload.tag || 'alphamind-price-alert',
    data: { url: '/alerts' },
  }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil((async () => {
    const clients = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of clients) {
      if ('focus' in client) {
        await client.focus();
        return;
      }
    }
    await self.clients.openWindow('/alerts');
  })());
});
