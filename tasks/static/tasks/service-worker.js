self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (_) {
    data = { body: event.data ? event.data.text() : 'You have a new WorkFlow update.' };
  }
  event.waitUntil(self.registration.showNotification(data.title || 'WorkFlow', {
    body: data.body || 'You have a new team update.',
    data: { url: data.url || '/notifications/' },
  }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const destination = new URL(event.notification.data?.url || '/notifications/', self.location.origin).href;
  event.waitUntil(clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windows) => {
    const existing = windows.find((windowClient) => new URL(windowClient.url).origin === self.location.origin);
    if (existing) {
      if ('navigate' in existing) existing.navigate(destination);
      return existing.focus();
    }
    return clients.openWindow(destination);
  }));
});
