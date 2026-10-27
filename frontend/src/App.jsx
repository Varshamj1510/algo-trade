import React, { useEffect, useState } from 'react';

const API_BASE = '';

const statCards = [
  { label: 'Total Portfolio Value', value: '₹ 2,45,678.90', delta: '+2.35% Today' },
  { label: "Today's P&L", value: '₹ 5,678.30', delta: '+1.89%' },
  { label: 'Total Profit', value: '₹ 25,430.50', delta: '+12.45%' },
  { label: 'Winning Trades', value: '68.42%', delta: '3 Buy / 4 Sell' },
];

const signalRows = [
  { symbol: 'RELIANCE', side: 'BUY', price: '₹2,056.40', time: '10:29 AM' },
  { symbol: 'TCS', side: 'BUY', price: '₹3,620.15', time: '10:28 AM' },
  { symbol: 'INFY', side: 'SELL', price: '₹1,512.80', time: '10:27 AM' },
  { symbol: 'HDFCBANK', side: 'BUY', price: '₹1,685.30', time: '10:26 AM' },
  { symbol: 'ICICIBANK', side: 'SELL', price: '₹1,245.60', time: '10:25 AM' },
];

const portfolioSegments = [
  { label: 'Stocks', value: 60, color: '#4f8cff' },
  { label: 'Mutual Funds', value: 25, color: '#6d5efc' },
  { label: 'ETFs', value: 10, color: '#2cd4a3' },
  { label: 'Others', value: 5, color: '#f7c948' },
];

const topGainers = [
  { symbol: 'BEL', price: '₹306.75', change: '+4.35%' },
  { symbol: 'NTPC', price: '₹335.40', change: '+3.20%' },
  { symbol: 'M&M', price: '₹2,742.10', change: '+2.87%' },
  { symbol: 'TATASTEEL', price: '₹155.65', change: '+2.20%' },
  { symbol: 'ADANIENT', price: '₹2,651.30', change: '+2.10%' },
];

const topLosers = [
  { symbol: 'WIPRO', price: '₹245.80', change: '-1.85%' },
  { symbol: 'HCLTECH', price: '₹1,789.80', change: '-1.45%' },
  { symbol: 'SBIN', price: '₹812.40', change: '-1.20%' },
  { symbol: 'AXISBANK', price: '₹1,062.30', change: '-0.35%' },
];

const recentActivity = [
  { label: 'Buy Signal Generated', value: '10:29 AM', item: 'RELIANCE' },
  { label: 'Strategy Backtested Completed', value: '10:20 AM', item: 'Momentum Strategy' },
  { label: 'Report Generated', value: '09:48 AM', item: 'My Performance Report' },
];

const pageCards = [
  { title: 'Market Data', accent: 'purple' },
  { title: 'Trade Signals', accent: 'blue' },
  { title: 'Portfolio Overview', accent: 'indigo' },
  { title: 'Backtesting', accent: 'cyan' },
  { title: 'Reports', accent: 'green' },
  { title: 'Profile Settings', accent: 'pink' },
];

const emptyForm = {
  fullName: '',
  email: '',
  username: '',
  password: '',
  confirmPassword: '',
  remember: false,
};

function App() {
  const [authMode, setAuthMode] = useState('login');
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [form, setForm] = useState(emptyForm);

  useEffect(() => {
    const storedUser = localStorage.getItem('algoTradeUser');
    if (storedUser) {
      setUser(JSON.parse(storedUser));
    }
  }, []);

  const handleChange = (event) => {
    const { name, value, type, checked } = event.target;
    setForm((prev) => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value,
    }));
  };

  const handleRegister = async (event) => {
    event.preventDefault();
    setError('');

    if (!form.fullName || !form.email || !form.username || !form.password || !form.confirmPassword) {
      setError('Please fill in all the fields.');
      return;
    }

    if (form.password !== form.confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    setLoading(true);

    try {
      const response = await fetch(`${API_BASE}/api/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          fullName: form.fullName,
          email: form.email,
          username: form.username,
          password: form.password,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || 'Registration failed.');
      }

      if (form.remember) {
        localStorage.setItem('algoTradeUser', JSON.stringify(data.user));
      }

      setUser(data.user);
      setAuthMode('login');
      setForm({ ...emptyForm, remember: form.remember });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleLogin = async (event) => {
    event.preventDefault();
    setError('');

    if (!form.email || !form.password) {
      setError('Please enter your email and password.');
      return;
    }

    setLoading(true);

    try {
      const response = await fetch(`${API_BASE}/api/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: form.email,
          password: form.password,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || 'Login failed.');
      }

      const loggedUser = data.user;
      if (form.remember) {
        localStorage.setItem('algoTradeUser', JSON.stringify(loggedUser));
      }

      setUser(loggedUser);
      setForm({ ...emptyForm, remember: form.remember });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('algoTradeUser');
    setUser(null);
    setAuthMode('login');
    setForm(emptyForm);
    setError('');
  };

  if (user) {
    return (
      <div className="dashboard-page">
        <header className="page-header">
          <h1>ALGORITHMIC TRADING SYSTEM - ALL PAGES OVERVIEW</h1>
          <p>Complete Web Application - Pages, Features &amp; Dashboard Summary</p>
        </header>

        <main className="overview-layout">
          <section className="mini-panel login-panel">
            <div className="brand-block">
              <div className="brand-mark">AI</div>
              <h2>AlgoMind</h2>
              <p>Smart Trades. Better Tomorrow.</p>
            </div>

            <div className="login-form">
              <div className="field-label">Email or Username</div>
              <div className="input-box"> </div>
              <div className="field-label">Password</div>
              <div className="input-box"> </div>
              <div className="option-row">
                <span>Remember Me</span>
                <span>Forgot Password?</span>
              </div>
              <button className="primary-button">Login</button>
              <div className="signup-line">Don't have an account? <span>Register</span></div>
            </div>
          </section>

          <section className="mini-panel register-panel">
            <div className="brand-block small">
              <div className="brand-mark">AI</div>
              <h2>AlgoMind</h2>
              <p>Smart Trades. Better Tomorrow.</p>
            </div>

            <div className="register-form">
              <div className="field-label">Full Name</div>
              <div className="input-box"> </div>
              <div className="field-label">Email</div>
              <div className="input-box"> </div>
              <div className="field-label">Username</div>
              <div className="input-box"> </div>
              <div className="field-label">Password</div>
              <div className="input-box"> </div>
              <div className="field-label">Confirm Password</div>
              <div className="input-box"> </div>
              <label className="checkbox-row"><input type="checkbox" /> I agree to the Terms &amp; Conditions</label>
              <button className="primary-button">Register</button>
              <div className="signup-line">Already have an account? <span>Login</span></div>
            </div>
          </section>

          <aside className="mini-panel sidebar-panel">
            <div className="sidebar-title">Main Navigation</div>
            <ul className="sidebar-menu">
              <li>Dashboard</li>
              <li>Market Data</li>
              <li>Trade Signals</li>
              <li>Strategies</li>
              <li>Portfolio</li>
              <li>Backtesting</li>
              <li>Reports</li>
              <li>Watchlist</li>
              <li>Alerts</li>
              <li>Profile Settings</li>
              <li className="logout" onClick={handleLogout}>Logout</li>
            </ul>
          </aside>

          <section className="main-dashboard">
            <header className="dashboard-header">
              <div className="dashboard-brand">Dashboard</div>
              <div className="user-box">
                <div className="avatar">{user.fullName ? user.fullName.charAt(0).toUpperCase() : 'V'}</div>
                <div>
                  <div className="username">{user.fullName || user.username}</div>
                  <div className="user-role">Premium Plan</div>
                </div>
              </div>
            </header>

            <div className="welcome-bar">
              <div>
                <div className="welcome-title">Welcome back, {user.username || 'Varshitha'}</div>
                <div className="welcome-subtitle">Here's what's happening in the market today.</div>
              </div>
              <div className="date-box">
                <span>03 June 2025</span>
                <span>10:30 AM</span>
              </div>
            </div>

            <div className="stat-grid">
              {statCards.map((card) => (
                <div className="stat-card" key={card.label}>
                  <div className="stat-label">{card.label}</div>
                  <div className="stat-value">{card.value}</div>
                  <div className="stat-delta">{card.delta}</div>
                </div>
              ))}
            </div>

            <div className="panel-row">
              <div className="market-panel">
                <div className="panel-top">
                  <div className="panel-title">Market Overview</div>
                  <div className="tab-row">
                    <span>NIFTY 50</span>
                    <span>SENSEX</span>
                    <span>BANK NIFTY</span>
                    <span className="active">1D</span>
                    <span>1W</span>
                    <span>1M</span>
                    <span>1Y</span>
                  </div>
                </div>

                <div className="chart-box">
                  <svg viewBox="0 0 680 240" className="market-chart" aria-label="market chart">
                    <defs>
                      <linearGradient id="chartFillDark" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#4f8cff" stopOpacity="0.38" />
                        <stop offset="100%" stopColor="#4f8cff" stopOpacity="0.02" />
                      </linearGradient>
                    </defs>
                    <path d="M0 180 C80 170, 120 140, 170 150 S260 100, 320 110 S410 70, 470 80 S560 40, 680 70 L680 240 L0 240 Z" fill="url(#chartFillDark)" />
                    <path d="M0 180 C80 170, 120 140, 170 150 S260 100, 320 110 S410 70, 470 80 S560 40, 680 70" fill="none" stroke="#4f8cff" strokeWidth="3" strokeLinecap="round" />
                  </svg>
                </div>
              </div>

              <div className="signal-panel">
                <div className="panel-top narrow">
                  <div className="panel-title">AI Trade Signals</div>
                  <button className="ghost-button">View All</button>
                </div>

                <div className="trade-list">
                  {signalRows.map((row) => (
                    <div className="trade-row" key={row.symbol}>
                      <span className="trade-symbol">{row.symbol}</span>
                      <span className={`trade-side ${row.side.toLowerCase()}`}>{row.side}</span>
                      <span className="trade-price">{row.price}</span>
                      <span className="trade-time">{row.time}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="bottom-grid">
              <div className="info-panel">
                <div className="panel-title">Portfolio Allocation</div>
                <div className="donut-wrap">
                  <div className="donut-chart">
                    <div className="donut-center">60%</div>
                  </div>
                  <div className="legend-list">
                    {portfolioSegments.map((segment) => (
                      <div className="legend-item" key={segment.label}>
                        <span className="dot" style={{ background: segment.color }}></span>
                        {segment.label}
                        <strong>{segment.value}%</strong>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div className="info-panel table-panel">
                <div className="panel-title">Top Gainers</div>
                <div className="metric-list">
                  {topGainers.map((item) => (
                    <div className="metric-row" key={item.symbol}>
                      <span className="metric-symbol">{item.symbol}</span>
                      <span className="metric-price">{item.price}</span>
                      <span className="metric-change positive">{item.change}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="info-panel table-panel">
                <div className="panel-title">Top Losers</div>
                <div className="metric-list">
                  {topLosers.map((item) => (
                    <div className="metric-row" key={item.symbol}>
                      <span className="metric-symbol">{item.symbol}</span>
                      <span className="metric-price">{item.price}</span>
                      <span className="metric-change negative">{item.change}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="info-panel activity-panel">
                <div className="panel-title">Recent Activity</div>
                <div className="activity-list">
                  {recentActivity.map((item) => (
                    <div className="activity-item" key={item.label}>
                      <div className="activity-badge"></div>
                      <div>
                        <div className="activity-line">{item.label}</div>
                        <div className="activity-meta">{item.value} · {item.item}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </section>
        </main>

        <section className="mini-cards">
          {pageCards.map((card) => (
            <div className={`preview-card ${card.accent}`} key={card.title}>
              <div className="preview-header">{card.title}</div>
              <div className="preview-graph">
                <span className="graph-line"></span>
              </div>
            </div>
          ))}
        </section>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <div className="auth-shell">
        <div className="auth-side">
          <div className="brand-block auth-brand">
            <div className="brand-mark">AI</div>
            <h2>AlgoMind</h2>
            <p>Smart Trades. Better Tomorrow.</p>
          </div>
        </div>

        <div className="login-card">
          <div className="login-title">{authMode === 'login' ? 'Welcome Back!' : 'Create New Account'}</div>
          <p className="login-subtitle">{authMode === 'login' ? 'Login to your account' : 'Fill in the details to get started'}</p>

          {authMode === 'login' ? (
            <form onSubmit={handleLogin} className="auth-form">
              <label className="field-wrap">
                <span>Email or Username</span>
                <input
                  type="text"
                  name="email"
                  value={form.email}
                  onChange={handleChange}
                  placeholder="Email or Username"
                />
              </label>

              <label className="field-wrap">
                <span>Password</span>
                <input
                  type="password"
                  name="password"
                  value={form.password}
                  onChange={handleChange}
                  placeholder="Password"
                />
              </label>

              <div className="form-row">
                <label className="remember-box">
                  <input type="checkbox" name="remember" checked={form.remember} onChange={handleChange} />
                  <span>Remember Me</span>
                </label>
                <a href="#">Forgot Password?</a>
              </div>

              {error && <div className="error-message">{error}</div>}

              <button type="submit" className="primary-button auth-button" disabled={loading}>
                {loading ? 'Logging in...' : 'Login'}
              </button>
            </form>
          ) : (
            <form onSubmit={handleRegister} className="auth-form">
              <label className="field-wrap">
                <span>Full Name</span>
                <input type="text" name="fullName" value={form.fullName} onChange={handleChange} placeholder="Full Name" />
              </label>

              <label className="field-wrap">
                <span>Email</span>
                <input type="email" name="email" value={form.email} onChange={handleChange} placeholder="Email" />
              </label>

              <label className="field-wrap">
                <span>Username</span>
                <input type="text" name="username" value={form.username} onChange={handleChange} placeholder="Username" />
              </label>

              <label className="field-wrap">
                <span>Password</span>
                <input type="password" name="password" value={form.password} onChange={handleChange} placeholder="Password" />
              </label>

              <label className="field-wrap">
                <span>Confirm Password</span>
                <input type="password" name="confirmPassword" value={form.confirmPassword} onChange={handleChange} placeholder="Confirm Password" />
              </label>

              <label className="remember-box checkbox-inline">
                <input type="checkbox" name="remember" checked={form.remember} onChange={handleChange} />
                <span>I agree to the Terms &amp; Conditions</span>
              </label>

              {error && <div className="error-message">{error}</div>}

              <button type="submit" className="primary-button auth-button" disabled={loading}>
                {loading ? 'Creating account...' : 'Register'}
              </button>
            </form>
          )}

          <div className="signup-line">
            {authMode === 'login' ? "Don't have an account? " : 'Already have an account? '}
            <span onClick={() => { setAuthMode(authMode === 'login' ? 'register' : 'login'); setError(''); }}>
              {authMode === 'login' ? 'Register' : 'Login'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
