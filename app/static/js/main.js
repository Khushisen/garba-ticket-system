// Minimal shared helpers used across pages.
function getCsrfToken() {
  const el = document.querySelector('meta[name="csrf-token"]');
  return el ? el.content : '';
}

async function postJson(url, data) {
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCsrfToken(),
    },
    body: JSON.stringify(data),
  });
  return res.json();
}
