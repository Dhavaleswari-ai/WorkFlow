document.querySelectorAll('.password-toggle').forEach((button) => {
  button.addEventListener('click', () => {
    const password = document.getElementById(button.getAttribute('aria-controls'));
    if (!password) return;

    const showing = password.type === 'password';
    password.type = showing ? 'text' : 'password';
    button.setAttribute('aria-pressed', String(showing));
    button.setAttribute('aria-label', showing ? 'Hide password' : 'Show password');
    button.title = showing ? 'Hide password' : 'Show password';
  });
});
