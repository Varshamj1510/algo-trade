const API_BASE = (window.__ALGOMIND_API_BASE__ || '').replace(/\/+$/, '');

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
      const message = data.message || data.msg || 'Request failed';
      if (response.status === 401 && token && !path.startsWith('/api/auth/')) {
        logoutUser();
      }
      throw new Error(message);
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
  const savedTheme = localStorage.getItem('alphamind_theme');
  const useLightTheme = savedTheme !== 'dark';
  document.body.classList.toggle('theme-light', useLightTheme);

  const topbarRight = document.querySelector('.topbar-right');
  if (topbarRight && !topbarRight.querySelector('.theme-toggle')) {
    const themeButton = document.createElement('button');
    themeButton.type = 'button';
    themeButton.className = 'secondary-btn theme-toggle';
    themeButton.setAttribute('aria-pressed', String(useLightTheme));
    themeButton.addEventListener('click', () => {
      const enableLightTheme = !document.body.classList.contains('theme-light');
      document.body.classList.toggle('theme-light', enableLightTheme);
      localStorage.setItem('alphamind_theme', enableLightTheme ? 'light' : 'dark');
      themeButton.setAttribute('aria-pressed', String(enableLightTheme));
      themeButton.innerHTML = `<i class="fa-solid ${enableLightTheme ? 'fa-moon' : 'fa-sun'}" aria-hidden="true"></i> ${enableLightTheme ? 'Dark mode' : 'Light mode'}`;
      window.dispatchEvent(new Event('alphamind-theme-change'));
    });
    themeButton.innerHTML = `<i class="fa-solid ${useLightTheme ? 'fa-moon' : 'fa-sun'}" aria-hidden="true"></i> ${useLightTheme ? 'Dark mode' : 'Light mode'}`;
    topbarRight.prepend(themeButton);
  }

  const sidebarNav = document.querySelector('.sidebar-nav');
  if (sidebarNav) {
    const pages = [
      ['dashboard', 'fa-chart-line', 'Dashboard'],
      ['market', 'fa-chart-column', 'Market Data'],
      ['stocks', 'fa-address-book', 'Stock Directory'],
      ['signals', 'fa-bolt', 'Trade Signals'],
      ['sentiment', 'fa-comments', 'Sentiment Analysis'],
      ['strategies', 'fa-diagram-project', 'Strategies'],
      ['alpha-research', 'fa-flask', 'Alpha Research'],
      ['candlestick-chart', 'fa-chart-simple', 'Candlesticks'],
      ['portfolio', 'fa-wallet', 'Portfolio'],
      ['paper-trading', 'fa-shuffle', 'Virtual Trading'],
      ['backtesting', 'fa-flask-vial', 'Backtesting'],
      ['reports', 'fa-file-lines', 'Reports'],
      ['watchlist', 'fa-star', 'Watchlist'],
      ['alerts', 'fa-bell', 'Alerts'],
      ['order-protection', 'fa-shield-halved', 'Order Protection'],
      ['trading-academy', 'fa-graduation-cap', 'Trading Academy'],
      ['profile', 'fa-user', 'Profile Settings'],
    ];
    const logoutItem = sidebarNav.querySelector('#logout-btn');
    const currentPath = window.location.pathname.replace(/\/+$/, '') || '/';
    const pageItems = pages.map(([page, icon, label]) => {
      const item = document.createElement('li');
      item.className = 'nav-item';
      item.dataset.page = page;
      item.innerHTML = `<i class="fa-solid ${icon}" aria-hidden="true"></i> ${label}`;
      if (currentPath === `/${page}`) {
        item.classList.add('active');
        item.setAttribute('aria-current', 'page');
      }
      return item;
    });
    sidebarNav.replaceChildren(...pageItems, ...(logoutItem ? [logoutItem] : []));
  }

  document.querySelectorAll('.nav-item[data-page]').forEach((item) => {
    item.style.cursor = 'pointer';
    item.onclick = () => {
      const page = item.dataset.page;
      if (page) {
        window.location.assign(`/${page}`);
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
