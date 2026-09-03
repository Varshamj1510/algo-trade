const API_BASE = 'http://127.0.0.1:5000';

function getToken() {
  return localStorage.getItem('algotrade_token');
}

function requireAuth() {
  if (!getToken()) {
    redirectTo('/login');
    return false;
  }
  return true;
}

function apiRequest(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  const token = getToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  return fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  }).then(async (response) => {
    const contentType = response.headers.get('content-type') || '';
    const data = contentType.includes('application/json') ? await response.json().catch(() => ({})) : {};
    if (!response.ok) {
      throw new Error(data.message || data.msg || 'Request failed');
    }
    return data;
  });
}

function redirectTo(path) {
  window.location.href = path;
}

function logoutUser() {
  localStorage.removeItem('algotrade_token');
  localStorage.removeItem('algotrade_user');
  redirectTo('/login');
}

function parseUser() {
  try {
    return JSON.parse(localStorage.getItem('algotrade_user') || 'null');
  } catch {
    return null;
  }
}

function bindSidebarNavigation() {
  document.querySelectorAll('.nav-item[data-page]').forEach((item) => {
    item.style.cursor = 'pointer';
    item.onclick = () => {
      const page = item.dataset.page;
      if (page) {
        window.location.href = `/${page}`;
      }
    };
  });
}

function formatCurrency(value, digits = 2) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(Number(value || 0));
}
