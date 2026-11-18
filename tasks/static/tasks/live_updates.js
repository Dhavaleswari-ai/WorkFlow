(() => {
  const app = document.getElementById('workflow-app');
  if (!app || !('WebSocket' in window)) return;

  const teamId = app.dataset.teamId;
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  let reconnectTimer;

  function connect() {
    const socket = new WebSocket(`${protocol}//${window.location.host}/ws/teams/${teamId}/`);

    socket.addEventListener('message', () => {
      const notice = document.createElement('div');
      notice.className = 'live-update-notice';
      notice.innerHTML = 'Team updates are available. <button type="button">Refresh</button>';
      const button = notice.querySelector('button');
      button.addEventListener('click', () => window.location.reload());
      app.prepend(notice);

      const editingForm = document.activeElement && document.activeElement.closest('form');
      if (!editingForm) {
        window.setTimeout(() => window.location.reload(), 1200);
      }
    });

    socket.addEventListener('close', (event) => {
      if (event.code !== 4403) reconnectTimer = window.setTimeout(connect, 5000);
    });
  }

  connect();
  window.addEventListener('pagehide', () => window.clearTimeout(reconnectTimer));
})();
