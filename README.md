# AI Algo Trading

A full-stack algorithmic trading dashboard starter with a React frontend and a Flask backend.

## Project structure

- `frontend/` - React + Vite dashboard
- `backend/` - Flask API and trading indicators
- `database/` - SQLite database

## Features

- Seeded dashboard demo prices across Market Data, Watchlist, and Portfolio
- Technical analysis indicators: RSI, MACD, moving average, VWAP
- Buy/sell signal generation
- Historical CSV-based 20/50-day moving-average backtesting
- SQLite database placeholder for trade records
- Strategy library with saved, user-scoped BUY/SELL condition rules and manual snapshot previews
- Authenticated order-protection calculator for stop/target levels, risk-based position size, and estimated trade risk
- Kite-backed signal analysis with RSI, MACD, EMA/SMA, Bollinger bands, VWAP, ATR, OBV, volume context, and candle charts
- Kite-backed alpha research with historical feature engineering, Random Forest/XGBoost estimates, factor ranking, PCA, autoencoder latent factors, and rolling composite-alpha weights

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

## Deploy on Render

Create a **Web Service** from this repository with the repository root as the root directory. Render can use the root `requirements.txt` and `Procfile`; if setting commands manually, use:

- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn --bind 0.0.0.0:$PORT run:app`

Set `SECRET_KEY` and `JWT_SECRET_KEY` as separate, strong random secrets in the Render service's **Environment** settings. Do not use the placeholder values in `.env.example`, commit a `.env` file, or share secrets in chat. Set `KITE_API_KEY`, `KITE_API_SECRET`, and `KITE_REDIRECT_URI` only if enabling Kite Connect; the redirect URI must be `https://<your-render-service>.onrender.com/kite/callback` and must match the URI configured for the Kite app.

The default SQLite database is suitable only for a temporary demo: Render's service filesystem is not persistent, so user data can be lost when the service restarts or is redeployed. If using this demo database, leave `DATABASE_URL` unset on Render; never use a SQLite path copied from a local Windows `.env` file. For persistent production data, provision a Render Postgres database and configure `DATABASE_URL` with its connection string before relying on the service for user accounts or saved data. Both `postgres://` and `postgresql://` connection strings are supported.

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
- `POST /api/protection/calculate` - calculate stop-loss, take-profit, position-size, trailing-stop, and risk/reward estimates; requires a JWT bearer token and does not place or save orders
- `GET /api/strategies` and `POST /api/strategies` - list the signed-in user's strategies and save validated indicator-rule strategies
- `POST /api/strategies/preview` - evaluate BUY/SELL rules against explicitly supplied indicator snapshot values; requires a JWT bearer token
- `POST /api/alpha-research` - fit and validate factor models from authenticated Kite historical candles; accepts `symbol`, `exchange`, and `timeframe` (`1Y` or `5Y`)

Open `/strategies` and select **New Strategy** to create BUY and SELL condition groups using AND/OR logic. Conditions support RSI, MACD, EMA, SMA, Bollinger upper/middle/lower bands, VWAP, ATR, OBV, price, moving average, and volume comparisons. Saved rules are scoped to the signed-in user. Signal previews use manual values supplied in the builder, show each rule's match result, and are not live market data, technical indicator time-series charts, or backtest results.

Open `/order-protection` to use the calculator. Supply entry price, stop-loss, account balance, and risk percentage. Quantity, take-profit, and trailing-stop distance are optional; loss/profit estimates require quantity, while risk/reward requires a take-profit price. Position size is a fractional estimate and excludes fees, slippage, and exchange lot-size constraints.

Open `/signals` to view illustrative BUY/SELL/HOLD signals calculated from seeded dashboard demo-stock daily changes. These are not live quotes, technical analysis, or trading advice.

Open `/backtesting` to run the 20/50-day moving-average crossover on the historical closes in `symbols.csv/adani.csv`. The page lists the file's supported symbols and coverage dates; it does not use dashboard demo values or Kite. Results exclude fees, slippage, and dividends and are historical illustrations, not a performance guarantee.

Open `/alpha-research` for the historical research workspace. It engineers 18 price, trend, volatility, momentum, and volume factors; fits Random Forest and XGBoost regressors to estimate the next five-session return; evaluates each model on a chronological holdout; ranks factors by rank information coefficient and model importance; and computes PCA and autoencoder latent representations. Composite alpha uses signed factor z-scores weighted by recent absolute rank IC, with a history chart showing how that composition changes. Research requires at least 120 usable labeled rows and is based only on Kite Connect candles; unavailable or insufficient data is reported rather than replaced with generated prices. Results are exploratory research, not trade instructions or guaranteed returns. No predictions or factor outputs are persisted.

Kite Connect API access is separate from signing in to Zerodha. Configure `KITE_API_KEY`, `KITE_API_SECRET`, and `KITE_REDIRECT_URI` in the project `.env`, then use the Kite connection flow for features that require live Kite data. The Market Data page itself uses seeded demo stocks only. The access token is held only in the running server process and must be renewed after it expires or the server restarts. If Kite reports that a user is not enabled for the configured app, the account must be enabled for that app by its owner or Kite Connect support; AlgoTrade cannot grant that permission. Existing `/api/orders` entries are local demo records and are not submitted to Zerodha. This application does not place live broker orders.

## Market overview data

The Market Data page's overview, gainers, losers, active stocks, sectors, and market-watch rows use the same seeded demo stock records shown on the dashboard. Its instrument search and instrument detail endpoint also restrict results to those seeded stocks. The page's demo market list and overview do not request Kite quotes or read the historical symbols CSV. Watchlist prices and portfolio holding valuations use the same seeded stock prices and are not live.

Strategy library metrics, report rows, and account alerts are seeded or account-specific demo records; the strategy builder still evaluates manually supplied indicator snapshots. Profile settings remain tied to the signed-in account. The Order Protection calculator can prefill entry and illustrative stop/target values from seeded dashboard quotes, but remains a calculator and never places an order. Alpha Research is unchanged and still requires Kite historical candles.

## Instrument CSV data

The general instrument catalog can read CSV files from `backend/data/instruments/`, `symbols.csv/`, or `backend/data/instruments.csv`; set `INSTRUMENTS_CSV` to override the configured single-file input. CSV headers are case-insensitive; `symbol` (or `ticker`) is required. The user-facing Market Data search and Watchlist are intentionally restricted to database-seeded dashboard demo stocks, while the historical Backtesting page reads `symbols.csv/adani.csv` as its separate close-price history source.

## Notes

This is a starter project intended for learning, demos, and further customization.
