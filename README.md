# AI Algo Trading

A full-stack algorithmic trading dashboard starter with a React frontend and a Flask backend.

## Project structure

- `frontend/` - React + Vite dashboard
- `backend/` - Flask API and trading indicators
- `database/` - SQLite database

## Features

- Real-time-style trading dashboard
- Technical analysis indicators: RSI, MACD, moving average, VWAP
- Buy/sell signal generation
- Backtesting engine
- SQLite database placeholder for trade records

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

## API endpoints

- `GET /healthz`
- `GET /api/signals`
- `GET /api/backtest`

## Notes

This is a starter project intended for learning, demos, and further customization.
