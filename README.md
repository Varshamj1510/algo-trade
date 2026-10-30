# AlgoMind

A full-stack algorithmic trading dashboard starter with a React frontend and a Flask backend.

## Project structure

- `frontend/` - React + Vite dashboard
- `backend/` - Flask API and trading indicators
- `database/` - SQLite database

## Features

- Market dashboard with stock search, watchlists, portfolio views, charts, and virtual trading
- Technical analysis indicators: RSI, MACD, moving average, VWAP
- Buy/sell signal generation
- Historical CSV-based 20/50-day moving-average backtesting
- SQLite database for local development; PostgreSQL recommended for deployment
- Strategy library with saved, user-scoped BUY/SELL condition rules and manual snapshot previews
- Hugging Face AI financial-sentiment analysis for user-provided headlines and article excerpts
- Authenticated order-protection calculator for stop/target levels, risk-based position size, and estimated trade risk
- Per-account virtual stock trading with ₹15,00,000 starting cash and virtual trades; no real payments or broker orders are submitted
- Trading Academy with YouTube Data API lesson search (`YOUTUBE_API_KEY`) restricted to trading education
- Kite-backed signal analysis with RSI, MACD, EMA/SMA, Bollinger bands, VWAP, ATR, OBV, volume context, and candle charts
- Kite-backed alpha research with historical feature engineering, Random Forest/XGBoost estimates, factor ranking, PCA, autoencoder latent factors, and rolling composite-alpha weights
- Local model explainability for alpha research using SHAP tree attributions and LIME surrogate explanations for Random Forest and XGBoost estimates; contributions are informational, not causal
- User-scoped, one-time above/below price alerts with browser notifications, quiet hours, and Kite Connect quote checks

## Frontend setup

```bash
cd AI_ALGO_TRADING/frontend
npm install
npm run dev
```

## Backend setup

```bash
cd AI_ALGO_TRADING/backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

## Deploy the full app on Render

The Render Web Service serves both the multi-page frontend (`frontend/`) and Flask API from one origin. Users should register and sign in using the Render URL; this keeps account and OTP requests on the same backend and shared database. The Vite app under `frontend/src` is a separate prototype and is not the deployed frontend.

Create one Render **Web Service** from this repository with the repository root as its root directory:

- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn --bind 0.0.0.0:$PORT run:app`
- Health check path: `/healthz`

Attach the Render PostgreSQL database to this Web Service and set `DATABASE_URL` to the database's **internal** connection string. Do not set it to a local SQLite path. Both registration and sign-in accounts are stored in that shared database.

In Render → Web Service → **Environment**, add the variables below. Replace every placeholder with your own value; do not paste secret values into source files or chat:

```text
SECRET_KEY=<generate-a-unique-random-secret>
JWT_SECRET_KEY=<generate-a-different-unique-random-secret>
DATABASE_URL=<Render-PostgreSQL-internal-connection-string>
FRONTEND_ORIGIN=https://<your-render-service>.onrender.com
APP_ORIGIN=https://<your-render-service>.onrender.com
WEBAUTHN_ORIGIN=https://<your-render-service>.onrender.com
WEBAUTHN_RP_ID=<your-render-service>.onrender.com
WEBAUTHN_RP_NAME=AlgoMind
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USE_SSL=true
SMTP_USE_TLS=false
SMTP_USER=<Gmail-address-that-sends-the-codes>
SMTP_PASS=<Google-App-Password-for-that-Gmail-account>
SMTP_FROM=<same-Gmail-address-that-sends-the-codes>
```

Use your exact Render service hostname (no trailing slash) in the four origin/RP variables. Render sets `PORT` automatically. Generate different strong values for `SECRET_KEY` and `JWT_SECRET_KEY`. For Gmail, use a Google **App Password**, not the normal account password; keep it private. `SMTP_FROM` should be the authenticated Gmail address.

The frontend and API are same-origin on Render; no separate frontend URL or API-base setting is needed.

Optional integration variables (only add the ones you use):

```dotenv
KITE_API_KEY=<kite-api-key>
KITE_API_SECRET=<kite-api-secret>
KITE_ACCESS_TOKEN=
KITE_REDIRECT_URI=https://<your-service>.onrender.com/kite/callback
YOUTUBE_API_KEY=<youtube-data-api-v3-key>
GEMINI_API_KEY=<gemini-api-key>
HUGGINGFACE_API_TOKEN=<huggingface-token>
```

Browser push variables must be configured in both the Web Service and Background Worker:

```dotenv
VAPID_PUBLIC_KEY=<vapid-public-key>
VAPID_PRIVATE_KEY=<vapid-private-key>
VAPID_SUBJECT=mailto:<contact-email>
PRICE_ALERT_POLL_SECONDS=30
```

For closed-page price-alert delivery, create a Render **Background Worker** with start command `python -m backend.alert_worker` and copy the same `DATABASE_URL` and required VAPID variables to it. Configure the same callback URL in the Kite Connect developer portal. Keep all real keys in Render Environment settings only; never commit `.env` or paste secrets into source control.

New accounts verify their email before registration completes. Email-code sign-in uses the same SMTP settings. For local development, configure SMTP values in `.env`; for the live service, configure them in Render Environment:

```dotenv
MAIL_SERVER=smtp.example.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USE_SSL=false
MAIL_USERNAME=your-smtp-username
MAIL_PASSWORD=your-smtp-password
MAIL_DEFAULT_SENDER=AlgoMind <no-reply@example.com>
```

Use the sender address authorized by your SMTP provider. Registration and email sign-in fail until the SMTP values are correctly set in the Render Web Service environment and the service has restarted/redeployed. Verification codes expire after 10 minutes, and resend requests are limited to one per 60 seconds. Local and deployed environments use separate databases; register and sign in on the same site.
The equivalent `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, and `SMTP_FROM` names are also supported. Gmail commonly uses port `465` with SSL or port `587` with TLS; use a Gmail app password rather than your normal account password. If you request another code within 60 seconds, wait for the cooldown and use the latest code. Check spam or junk if the message is delayed.

## Price alerts

Open `/alerts` to create and manage above/below price conditions. Enabling notifications requests browser permission and registers that browser for Web Push. Price conditions are checked against Kite Connect quotes. Kite credentials, a valid Kite session, VAPID keys, and the background alert worker are required for notifications while the page is closed. The worker polls every 30 seconds by default; quiet hours use the browser's configured timezone and keep triggered notifications pending until quiet hours end. A triggered alert fires once; reset it only after the quote has moved outside its condition, or change its target/direction.

Generate a VAPID key pair once and keep the private key secret. For local development, run `python -m backend.generate_vapid_keys` once; it writes the pair to the ignored `.env` file without printing the keys. Set the same `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, and a real contact such as `VAPID_SUBJECT=mailto:you@example.com` in the production server and worker environments. Then start the web app and alert worker in separate terminals:

```powershell
python -m backend.generate_vapid_keys
python run.py
python -m backend.alert_worker
```

In production, run `web` and `worker` as separate long-running processes using the commands in `Procfile`, sharing the same database and environment variables. Use HTTPS for deployed sites (localhost is allowed for development). Browser/device notification permission is required, and delivery also depends on the browser's push service and operating-system notification settings.

The default SQLite database is suitable only for a temporary demo: Render's service filesystem is not persistent, so user data can be lost when the service restarts or is redeployed. If using this demo database, leave `DATABASE_URL` unset on Render; never use a SQLite path copied from a local Windows `.env` file. For persistent production data, provision a Render Postgres database and configure `DATABASE_URL` with its connection string before relying on the service for user accounts or saved data. Both `postgres://` and `postgresql://` connection strings are supported.

Optional secure sign-in methods are available alongside account-password and email-code sign-in. In **Profile Settings**, sign in with your account password to register a device passkey (fingerprint, face, or device PIN when supported) and/or set a 6-digit Alpha PIN. PINs are stored as password hashes and lock temporarily after repeated failed attempts. If your email already has an account, sign in instead of registering again. If PIN sign-in says no PIN is configured, password sign-in will take you to **Profile Settings** to create one; there is no shared/default PIN. Passkey sign-in requires HTTPS in deployment (localhost is permitted for local development); set the relying-party values to match the exact public site:

```dotenv
WEBAUTHN_RP_ID=your-site.example.com
WEBAUTHN_RP_NAME=AlgoMind
WEBAUTHN_ORIGIN=https://your-site.example.com
```

`RP_ID` and `RP_NAME` are accepted as aliases for `WEBAUTHN_RP_ID` and `WEBAUTHN_RP_NAME`. With the development default `RP_ID=localhost`, the server uses the current page host for passkey options and verification, which prevents the browser's RP-ID mismatch error when testing through a public HTTPS tunnel. For deployment, configure `WEBAUTHN_RP_ID`, `WEBAUTHN_RP_NAME`, and `WEBAUTHN_ORIGIN` explicitly; the browser origin must match exactly, including the scheme and port.

## API endpoints

- `GET /healthz`
- `GET /api/signals` - demo trade signals calculated from the dashboard's seeded demo stocks (not live)
- `POST /api/ai-signal` - run a Kite-backed technical analysis for a symbol, exchange, and history window
- `GET /api/backtest/instruments` - symbols and date coverage available in the historical CSV
- `POST /api/backtest` - run a 20/50-day moving-average backtest against historical CSV closes
- `GET /api/backtest/history`
- `GET /api/instruments/search?q=<symbol-or-name>&exchange=<exchange>` - seeded dashboard demo-stock search
- `GET /api/instruments/<symbol>?exchange=<exchange>` - seeded dashboard demo-stock details
- `GET /api/market?q=<symbol-or-name>&exchange=<exchange>` - seeded dashboard demo instruments and sample values (up to 200 instruments per request; not live)
- `GET /api/market/overview` - locally calculated overview using seeded dashboard demo instruments (not live)
- `GET /api/market/indices`, `/api/market/gainers`, `/api/market/losers`, `/api/market/active`, `/api/market/sectors` - overview sections
- `GET /api/watchlist`, `POST /api/watchlist`, `DELETE /api/watchlist/<symbol>?exchange=<exchange>` - user watchlist
- `GET /api/alerts`, `PUT /api/alerts/settings`, `POST /api/alerts/check`, `POST /api/alerts/acknowledge`, and `/api/price-alerts` - user-scoped price alert conditions and settings
- `GET /api/alerts/push/public-key`, `POST /api/alerts/push/subscribe`, and `DELETE /api/alerts/push/subscribe` - user-scoped browser push registration
- `GET /api/paper-trading/account`, `POST /api/paper-trading/account/add-virtual-cash`, `GET /api/paper-trading/quote?symbol=<symbol>&exchange=<NSE|BSE|NFO>`, and `POST /api/paper-trading/trades` - read the signed-in user's demo account, add virtual cash, and simulate whole-share equity BUY/SELL fills without real payments or broker orders
- `GET /api/paper-trading/futures` and `POST /api/paper-trading/futures/trades` - list active NIFTY 50 futures contracts from Kite's instrument master and simulate long BUY/SELL-to-close positions using the contract lot size and full notional
- `GET /api/candlestick-chart/instruments` and `GET /api/candlestick-chart?symbol=<symbol>&timeframe=<3M|6M|1Y|5Y>` - load historical daily OHLCV candles and calculated candlestick-pattern labels from the bundled CSV
- `POST /api/protection/calculate` - calculate stop-loss, take-profit, position-size, trailing-stop, and risk/reward estimates; requires a JWT bearer token and does not place or save orders
- `GET /api/strategies` and `POST /api/strategies` - list the signed-in user's strategies and save validated indicator-rule strategies
- `POST /api/strategies/preview` - evaluate BUY/SELL rules against explicitly supplied indicator snapshot values; requires a JWT bearer token
- `POST /api/sentiment/analyze` - classify provided text with the Hugging Face financial model, falling back to Google Gemini when Hugging Face inference credits are unavailable; requires a JWT bearer token and a configured provider key
- `POST /api/ai-assistant/chat` - chat with the authenticated user's recent in-page conversation using Google Gemini; requires `GEMINI_API_KEY`, allows 10 requests per user per minute, and does not store chat history
- `GET /api/academy/access`, `POST /api/academy/premium-demo`, and `GET /api/academy/youtube-search?q=<topic>&tier=<free|premium>` - manage the user's free/Premium demo learning access and search embeddable YouTube lessons. Configure `YOUTUBE_API_KEY` only in the server environment; the ₹199/month Premium price is informational and no subscription payment is processed.
- `GET /api/alpha-research/instruments` - list NSE symbols available in the bundled historical demo CSV
- `POST /api/alpha-research` - fit and validate factor models from bundled demo candles or authenticated Kite historical candles; accepts `symbol`, `exchange`, `timeframe` (`1Y` or `5Y`), and `source` (`demo` or `kite`)

Open `/strategies` to browse ready-to-customize rule templates or select **New Strategy** to create BUY and SELL condition groups using AND/OR logic. Conditions support numeric thresholds and indicator-to-indicator comparisons for RSI, MACD, EMA, SMA, Bollinger upper/middle/lower bands, VWAP, ATR, OBV, price, moving average, and volume. Templates are starting rules, not performance claims; saved rules are scoped to the signed-in user. Signal previews use manual values supplied in the builder, show each rule's match result, and are not live market data, crossover detection, technical indicator time-series charts, or backtest results.

Open `/order-protection` to use the calculator. Supply entry price, stop-loss, account balance, and risk percentage. Quantity, take-profit, and trailing-stop distance are optional; loss/profit estimates require quantity, while risk/reward requires a take-profit price. Position size is a fractional estimate and excludes fees, slippage, and exchange lot-size constraints.

Open `/signals` to view illustrative BUY/SELL/HOLD signals calculated from seeded dashboard demo-stock daily changes. These are not live quotes, technical analysis, or trading advice.

Open `/sentiment` to analyze a headline or excerpt using the Hugging Face financial sentiment model, with Google Gemini as an alternative when Hugging Face inference credits are unavailable. If Hugging Face is not configured, Gemini is used directly. The page displays negative, neutral, and positive class scores and identifies the provider used; it does not fetch news automatically. Text is sent to the selected provider through the server, so do not submit private or sensitive information. Gemini scores are estimates rather than calibrated probabilities. Sentiment can miss context or sarcasm and is educational—not trading advice or a prediction of market movement.

The Dashboard includes a centered AlgoMind AI chat assistant. It answers educational questions about trading concepts, indicators, risk management, and app features using Google Gemini. Chat history is kept only in the open browser page and sent to Gemini for replies; AlgoMind does not persist it. The endpoint is limited to 10 requests per user per minute. The assistant has no live quote, news, or account-data access and is not a source of personalized financial advice.

To enable AI sentiment analysis locally, configure either or both providers in the project-root `.env` file (next to `run.py`):

1. For Hugging Face, create a fine-grained access token with **Inference Providers** permission from [Hugging Face token settings](https://huggingface.co/settings/tokens/new?ownUserPermissions=inference.serverless.write&tokenType=fineGrained). Add it as `HUGGINGFACE_API_TOKEN=hf_your_token`.
2. For the Gemini alternative, create an API key in [Google AI Studio](https://aistudio.google.com/apikey). Add it as `GEMINI_API_KEY=your_google_api_key`.

   ```dotenv
   HUGGINGFACE_API_TOKEN=hf_your_token
   GEMINI_API_KEY=your_google_api_key
   ```

3. Restart the Flask app. Hugging Face is tried first; if it reports that provider credits are unavailable, AlgoMind uses Gemini when `GEMINI_API_KEY` is configured. If only the Gemini key is configured, Gemini is used directly. Google AI Studio has its own model availability, quotas, and pricing; check the [Gemini API pricing and limits](https://ai.google.dev/gemini-api/docs/pricing) for your account.

Keep both keys server-side; never commit `.env` or share keys in chat. For deployment, set whichever provider keys you use in the hosting service's environment settings. Without a configured key, the API returns a setup message rather than falling back to a misleading local heuristic.

Open `/paper-trading` to practice with a separate virtual account seeded with ₹15,00,000 per user. Accounts still at the untouched original ₹1,00,000 balance are upgraded once; accounts with existing trades retain their cash balance. Stock quotes, fills, and position valuations use `backend/data/paper_trading_instruments.csv` and do not require Kite Connect. Review the built-in daily-change algorithm for any listed stock, or review a saved strategy against bundled historical candles when the selected symbol has history. Reviews explain each entry/exit condition and never place an order automatically; BUY and SELL remain user-confirmed virtual trades. Futures are not offered in this simulator because no futures contracts or prices are included in the configured instrument CSV. No order is sent to Kite or any exchange.

Open `/candlestick-chart` to display daily OHLCV candles from `symbols.csv/adani.csv`. Choose a CSV symbol and a 3-month, 6-month, 1-year, or 5-year period; the chart includes volume bars and labels for detected Doji, spinning top, Marubozu, Hammer, Shooting star, engulfing, Harami, Morning star, and Evening star patterns. The chart is historical CSV data, not Kite/live data, and pattern labels are educational rather than trading advice.

Open `/backtesting` to run the 20/50-day moving-average crossover on the historical closes in `symbols.csv/adani.csv`. The page lists the file's supported symbols and coverage dates; it does not use dashboard demo values or Kite. Results exclude fees, slippage, and dividends and are historical illustrations, not a performance guarantee.

Open `/alpha-research` for the historical research workspace. Choose **Bundled demo data** to use the repository's historical OHLCV CSV without Kite credentials, or **Kite Connect** to use candles from an authorized account. Demo mode supports the NSE symbols listed by the page and uses bundled historical CSV candles; these are not Kite data and are separate from the seeded demo quotes shown on Market Data. The workspace engineers 18 price, trend, volatility, momentum, and volume factors; fits Random Forest and XGBoost regressors to estimate the next five-session return; evaluates each model on a chronological holdout; ranks factors by rank information coefficient and model importance; and computes PCA and autoencoder latent representations. Composite alpha uses signed factor z-scores weighted by recent absolute rank IC, with a history chart showing how that composition changes. Research requires at least 120 usable labeled rows; unavailable or insufficient data is reported rather than replaced with generated prices. Results are exploratory research, not trade instructions or guaranteed returns. No predictions or factor outputs are persisted.

Kite Connect API access is separate from signing in to Zerodha. Configure `KITE_API_KEY`, `KITE_API_SECRET`, and `KITE_REDIRECT_URI` in the project `.env`, then use the Kite connection flow for features that require live Kite data. The Market Data page itself uses seeded demo stocks only. The access token is held only in the running server process and must be renewed after it expires or the server restarts. If Kite reports that a user is not enabled for the configured app, the account must be enabled for that app by its owner or Kite Connect support; AlgoMind cannot grant that permission. Existing `/api/orders` entries are local demo records and are not submitted to Zerodha. This application does not place live broker orders.

## Market overview data

The Market Data page's overview, gainers, losers, active stocks, sectors, and market-watch rows use the same seeded demo stock records shown on the dashboard. Its instrument search and instrument detail endpoint also restrict results to those seeded stocks. The page's demo market list and overview do not request Kite quotes or read the historical symbols CSV. Watchlist prices and portfolio holding valuations use the same seeded stock prices and are not live.

Report rows and account alerts are seeded or account-specific demo records; strategy previews evaluate manually supplied indicator snapshots and do not show performance metrics. Profile settings remain tied to the signed-in account. The Order Protection calculator can prefill entry and illustrative stop/target values from seeded dashboard quotes, but remains a calculator and never places an order. Alpha Research is unchanged and still requires Kite historical candles.

## Instrument CSV data

The general instrument catalog can read CSV files from `backend/data/instruments/`, `symbols.csv/`, or `backend/data/instruments.csv`; set `INSTRUMENTS_CSV` to override the configured single-file input. CSV headers are case-insensitive; `symbol` (or `ticker`) is required. The user-facing Market Data search and Watchlist are intentionally restricted to database-seeded dashboard demo stocks, while the historical Backtesting page reads `symbols.csv/adani.csv` as its separate close-price history source.

## Notes

This is a starter project intended for learning, demos, and further customization.
