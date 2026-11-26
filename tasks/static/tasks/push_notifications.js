(() => {
  const button = document.getElementById('push-alert-toggle');
  const status = document.getElementById('push-alert-status');
  if (!button || !status) return;

  const publicKey = button.dataset.publicKey;
  if (!publicKey || !('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
    button.hidden = true;
    status.textContent = 'Desktop alerts are not supported or are not configured for this site yet.';
    return;
  }

  const decodeKey = (encoded) => {
    const padding = '='.repeat((4 - encoded.length % 4) % 4);
    const base64 = (encoded + padding).replace(/-/g, '+').replace(/_/g, '/');
    return Uint8Array.from(atob(base64), (character) => character.charCodeAt(0));
  };

  const csrfToken = () => document.cookie.split('; ').find((part) => part.startsWith('csrftoken='))?.split('=')[1] || '';
  const sendSubscription = async (url, payload) => {
    const response = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Could not update desktop alert settings.');
    return result;
  };

  const refreshState = async () => {
    const registration = await navigator.serviceWorker.register('/service-worker.js', { scope: '/' });
    const subscription = await registration.pushManager.getSubscription();
    if (subscription && Notification.permission === 'granted') {
      await sendSubscription('/notifications/push/subscribe/', subscription.toJSON());
      button.textContent = 'Turn off desktop alerts';
      button.dataset.enabled = 'true';
      status.textContent = 'Desktop alerts are enabled on this browser.';
    } else {
      button.textContent = 'Enable desktop alerts';
      button.dataset.enabled = 'false';
      status.textContent = Notification.permission === 'denied'
        ? 'Notifications are blocked in this browser. Allow them in site settings to enable alerts.'
        : 'Get WorkFlow alerts while you use other apps.';
    }
    return { registration, subscription };
  };

  refreshState().catch(() => { status.textContent = 'Could not prepare browser alerts on this device.'; });

  button.addEventListener('click', async () => {
    button.disabled = true;
    try {
      let { registration, subscription } = await refreshState();
      if (subscription) {
        await sendSubscription('/notifications/push/unsubscribe/', { endpoint: subscription.endpoint });
        await subscription.unsubscribe();
        button.dataset.enabled = 'false';
        button.textContent = 'Enable desktop alerts';
        status.textContent = 'Desktop alerts are turned off on this browser.';
        return;
      }
      const permission = await Notification.requestPermission();
      if (permission !== 'granted') {
        status.textContent = 'Allow notifications in the browser prompt to receive alerts.';
        return;
      }
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: decodeKey(publicKey),
      });
      await sendSubscription('/notifications/push/subscribe/', subscription.toJSON());
      button.dataset.enabled = 'true';
      button.textContent = 'Turn off desktop alerts';
      status.textContent = 'Desktop alerts are enabled on this browser.';
    } catch (error) {
      status.textContent = error.message || 'Could not enable desktop alerts.';
    } finally {
      button.disabled = false;
    }
  });
})();
