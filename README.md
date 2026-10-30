# AlgoMind

AlgoMind is a Flask application with a multi-page HTML/CSS/JavaScript frontend. A separate React + Vite prototype is in `frontend/src`.

## Project structure

- `backend/` — Flask application, API routes, database models, and trading services
- `frontend/` — deployed multi-page UI and separate Vite prototype
- `database/` — local SQLite databases (ignored by Git)
- `tests/` — automated tests
- `symbols.csv/` — bundled historical demo data

## Features

- Dashboard with portfolio views, charts, watchlists, and virtual trading
- Technical indicators: RSI, MACD, moving averages, and VWAP
- Historical CSV-based moving-average backtesting
- Saved trading strategies and manual rule previews
- Financial-text sentiment analysis with Hugging Face and/or Gemini
- Alpha research with Random Forest/XGBoost estimates, factor ranking, PCA, and SHAP/LIME explanations
- Order-protection calculations for stop/target levels and position sizing
- Virtual equity and futures trading; no live broker orders or real payments
- Trading Academy with YouTube Data API lesson search
- Kite Connect integration for supported market analysis and price-alert checks
- User-scoped price alerts with browser notifications and quiet hours

## Local development

Run these commands from the repository root.

### Backend

Create and activate a virtual environment, then install the root requirements:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

On macOS/Linux, activate the environment with:

```bash
source .venv/bin/activate
```

The Flask app serves the frontend and API from the same origin. The local SQLite database is configured automatically unless `DATABASE_URL` is set.

### Optional Vite prototype

The deployed UI is served from the HTML pages in `frontend/`. To run the separate React + Vite prototype:

```powershell
cd frontend
npm install
npm run dev
```

## Render deployment

Create one Render **Web Service** using the repository root:

| Setting | Value |
|---|---|
| Build command | `pip install -r requirements.txt` |
| Start command | `gunicorn --bind 0.0.0.0:$PORT run:app` |
| Health check path | `/healthz` |

For persistent accounts and saved data, attach Render PostgreSQL and set `DATABASE_URL` to its **internal connection string**. Render's local filesystem is not persistent; SQLite is suitable only for temporary demos. Do not use a local Windows SQLite path on Render.

Add these required settings in **Render → Web Service → Environment**. Replace the placeholders with your own values:

```dotenv
SECRET_KEY=<unique-random-secret>
JWT_SECRET_KEY=<different-unique-random-secret>
DATABASE_URL=<render-postgresql-internal-connection-string>
FRONTEND_ORIGIN=https://<your-service>.onrender.com
APP_ORIGIN=https://<your-service>.onrender.com
```

Render sets `PORT` automatically. The frontend and API share an origin; no separate frontend/API URL is needed. Registration does not use email verification; users sign in with their password or Alpha PIN.

### Optional integrations

Add only the variables for integrations you use:

```dotenv
KITE_API_KEY=<kite-api-key>
KITE_API_SECRET=<kite-api-secret>
KITE_ACCESS_TOKEN=
KITE_REDIRECT_URI=https://<your-service>.onrender.com/kite/callback
YOUTUBE_API_KEY=<youtube-data-api-v3-key>
GEMINI_API_KEY=<gemini-api-key>
HUGGINGFACE_API_TOKEN=<huggingface-token>
```

Keep all real keys in Render's environment settings. Never commit `.env` or put secrets in documentation or chat.

## Authentication

Users can register without email verification and sign in with their password or a 6-digit Alpha PIN. PINs are stored as password hashes and temporarily lock after repeated failed attempts. PIN setup or changes require the account password in **Profile Settings**. Each environment has its own database, so use the same site to register and sign in.

The Profile Settings page currently includes passkey registration, but passkey/fingerprint sign-in is not offered on the login page.

## Price alerts and browser notifications

Open `/alerts` to create above/below price conditions. Conditions use Kite Connect quotes. Browser permission is required for notifications; closed-page delivery also requires a valid Kite session, VAPID keys, and a background worker.

Generate a VAPID key pair locally:

```powershell
python -m backend.generate_vapid_keys
```

The command writes keys to the ignored project-root `.env` file without printing them. Configure the same values for the Render Web Service and Background Worker:

```dotenv
VAPID_PUBLIC_KEY=<vapid-public-key>
VAPID_PRIVATE_KEY=<vapid-private-key>
VAPID_SUBJECT=mailto:<contact-email>
PRICE_ALERT_POLL_SECONDS=30
```

Create a Render **Background Worker** with start command `python -m backend.alert_worker`. Give it the same `DATABASE_URL` and VAPID settings as the Web Service. In production, the `Procfile` defines the `web` and `worker` commands. Use HTTPS and allow browser notifications in the browser and operating system.

## Sentiment analysis and AI assistant

The `/sentiment` page analyzes text that you provide; it does not fetch news. Configure `HUGGINGFACE_API_TOKEN`, `GEMINI_API_KEY`, or both. Hugging Face is tried first; Gemini is used as a fallback if configured, or directly if it is the only provider. Sentiment can miss context or sarcasm and is not a trading signal. Text is sent to the configured provider, so do not submit private information.

The dashboard AI assistant uses Gemini and requires `GEMINI_API_KEY`. It answers educational questions, allows 10 requests per user per minute, and does not persist chat history. It does not have live quote, news, or account-data access.

For local development, add the provider keys to the project-root `.env` file and restart the app. For Render, add them in the Web Service's Environment settings and redeploy.

To create provider keys:

1. Hugging Face: create a fine-grained token with **Inference Providers** permission in [Hugging Face token settings](https://huggingface.co/settings/tokens/new?ownUserPermissions=inference.serverless.write&tokenType=fineGrained).
2. Gemini: create a key in [Google AI Studio](https://aistudio.google.com/apikey). Review [Gemini API pricing and limits](https://ai.google.dev/gemini-api/docs/pricing).

## Trading feature notes

### Strategies and signals

Open `/strategies` to use templates or create BUY/SELL condition groups with AND/OR logic. Rules can use RSI, MACD, EMA, SMA, Bollinger bands, VWAP, ATR, OBV, price, moving average, and volume. Previews evaluate manually entered indicator values; they are not live data, backtests, or performance claims.

Open `/signals` for illustrative BUY/SELL/HOLD signals based on seeded demo-stock changes. These are not live quotes or trading advice.

### Order protection

Open `/order-protection` and enter an entry price, stop-loss, account balance, and risk percentage. Quantity, take-profit, and trailing-stop distance are optional. Loss/profit estimates require quantity; risk/reward requires a take-profit price. Estimates exclude fees, slippage, and exchange lot-size constraints. This tool does not place or save orders.

### Virtual trading

Open `/paper-trading` to use the separate simulated account, seeded with ₹15,00,000 per user. Quotes and fills use `backend/data/paper_trading_instruments.csv` and do not require Kite Connect. Trades are virtual; no orders are sent to Kite or an exchange.

### Backtesting and charts

Open `/backtesting` to run a 20/50-day moving-average crossover using historical closes in `symbols.csv/adani.csv`. Open `/candlestick-chart` for historical daily OHLCV candles and educational candlestick-pattern labels from the bundled CSV. These are historical examples, not live Kite data or performance guarantees.

### Alpha Research and explainability

Open `/alpha-research` and select bundled demo data or Kite Connect. The workspace engineers market factors, estimates five-session returns with Random Forest and XGBoost, evaluates models on a chronological holdout, ranks factors, and calculates PCA/autoencoder representations. SHAP and LIME provide model explanations; their feature contributions are informational, not causal. Results are exploratory research, not trade instructions or guaranteed returns.

### Market data and Kite Connect

Market Data, dashboard overview, watchlist, and portfolio valuations use seeded demo prices and are not live quotes. Kite Connect is a separate integration for supported analysis and price-alert checks. Configure `KITE_API_KEY`, `KITE_API_SECRET`, and `KITE_REDIRECT_URI`; the access token is held in the running server and must be renewed after expiry or restart. Existing order records are local demo records; this application does not submit live broker orders.

## API reference

- `GET /healthz` — health check
- `GET /api/signals` — demo signals
- `POST /api/ai-signal` — Kite-backed technical analysis
- `GET /api/backtest/instruments`, `POST /api/backtest`, `GET /api/backtest/history` — historical backtests
- `GET /api/instruments/search`, `GET /api/instruments/<symbol>` — seeded demo-stock search and details
- `GET /api/market`, `GET /api/market/overview` — demo market data and overview
- `GET /api/market/indices`, `/api/market/gainers`, `/api/market/losers`, `/api/market/active`, `/api/market/sectors` — overview sections
- `GET /api/watchlist`, `POST /api/watchlist`, `DELETE /api/watchlist/<symbol>` — user watchlist
- `GET /api/alerts`, `PUT /api/alerts/settings`, `POST /api/alerts/check`, `POST /api/alerts/acknowledge`, `/api/price-alerts` — price alerts and settings
- `GET /api/alerts/push/public-key`, `POST /api/alerts/push/subscribe`, `DELETE /api/alerts/push/subscribe` — browser push subscriptions
- `/api/paper-trading/*` — simulated account, quotes, equity trades, and futures
- `/api/candlestick-chart/*` — bundled historical candles and pattern labels
- `POST /api/protection/calculate` — authenticated risk calculations
- `GET /api/strategies`, `POST /api/strategies`, `POST /api/strategies/preview` — user strategies and manual previews
- `POST /api/sentiment/analyze` — authenticated sentiment analysis; needs a provider key
- `POST /api/ai-assistant/chat` — authenticated Gemini assistant; needs `GEMINI_API_KEY`
- `/api/academy/*` — learning access and YouTube lesson search; needs `YOUTUBE_API_KEY`
- `GET /api/alpha-research/instruments`, `POST /api/alpha-research` — historical factor research

## Instrument and historical data

The instrument catalog can read `backend/data/instruments/`, `symbols.csv/`, or `backend/data/instruments.csv`. Set `INSTRUMENTS_CSV` to use a different single CSV file. CSV headers are case-insensitive; a `symbol` or `ticker` column is required.

Market Data search and Watchlist intentionally use seeded demo stocks. Historical Backtesting and chart pages use the bundled CSV data separately.

## Notes

This project is intended for learning, demos, and further customization. Market estimates, model outputs, and strategy examples are not financial advice.
