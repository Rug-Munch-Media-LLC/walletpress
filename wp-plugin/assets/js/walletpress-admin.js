document.addEventListener('DOMContentLoaded', () => {
  for (const btn of document.querySelectorAll('.copy-shortcode')) {
    btn.addEventListener('click', () => {
      navigator.clipboard.writeText(btn.dataset.code).then(() => {
        btn.textContent = 'Copied!';
        setTimeout(() => { btn.textContent = 'Copy'; }, 2000);
      });
    });
  }
});
