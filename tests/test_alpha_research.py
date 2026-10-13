import math

import pytest

import backend.routes.alpha_research_routes as alpha_routes
from backend.app import app
from backend.services.alpha_research import AlphaResearchError, analyze_alpha


def make_candles(count=320):
    candles = []
    for index in range(count):
        close = 100 + index * 0.08 + math.sin(index / 7) * 2 + math.sin(index / 29) * 4
        volume = 1500 + (index % 23) * 35 + abs(math.sin(index / 5)) * 400
        candles.append({
            'time': f'2025-01-{(index % 28) + 1:02d}T09:15:00+05:30',
            'open': close - 0.4,
            'high': close + 1.1 + (index % 3) * 0.1,
            'low': close - 1.2,
            'close': close,
            'volume': volume,
        })
    return candles


def test_alpha_research_trains_models_ranks_factors_and_composes_alpha():
    result = analyze_alpha(make_candles(), 'ALPHA', 'NSE', '1Y')

    assert result['provider'] == 'Kite Connect historical candles'
    assert result['candle_range']['start']
    assert result['candle_range']['end']
    assert result['forward_horizon_sessions'] == 5
    assert result['training_rows'] >= 120
    assert set(result['model_predictions']) == {'random_forest', 'xgboost', 'ensemble'}
    assert set(result['validation']) == {'random_forest', 'xgboost'}
    assert len(result['factor_ranking']) == 18
    assert abs(sum(item['dynamic_weight'] for item in result['factor_ranking']) - 1) < 0.001
    assert result['composite_alpha']['direction'] in {'POSITIVE', 'NEGATIVE', 'NEUTRAL'}
    assert len(result['composite_alpha']['history']) > 1
    assert len(result['latent_factors']['pca']) == 3
    assert len(result['latent_factors']['autoencoder']) == 3
    assert all(math.isfinite(value) for value in result['model_predictions'].values())


def test_alpha_research_requires_sufficient_history():
    with pytest.raises(AlphaResearchError, match='at least 190 daily candles'):
        analyze_alpha(make_candles(100), 'ALPHA', 'NSE', '3M')


def test_alpha_research_api_requires_authentication():
    response = app.test_client().post('/api/alpha-research', json={
        'symbol': 'ALPHA', 'exchange': 'NSE', 'timeframe': '1Y',
    })

    assert response.status_code == 401


def test_alpha_research_api_uses_real_candles_for_requested_instrument(monkeypatch):
    candles = make_candles()
    result = {'symbol': 'ALPHA', 'factor_ranking': []}
    monkeypatch.setattr(alpha_routes, 'find_instrument', lambda symbol, exchange: {
        'symbol': symbol, 'exchange': exchange,
    })
    monkeypatch.setattr(alpha_routes, 'get_historical_candles', lambda instrument, timeframe: candles)
    monkeypatch.setattr(
        alpha_routes, 'analyze_alpha',
        lambda historical, symbol, exchange, timeframe: result,
    )
    client = app.test_client()
    login = client.post('/api/auth/login', json={
        'email': 'demo@algotrade.com', 'password': 'demo123',
    })
    headers = {'Authorization': f"Bearer {login.get_json()['token']}"}
    response = client.post('/api/alpha-research', headers=headers, json={
        'symbol': 'alpha', 'exchange': 'nse', 'timeframe': '1y',
    })

    assert response.status_code == 200
    assert response.get_json()['data'] == result


def test_alpha_research_api_validates_request_and_reports_unavailable_kite(monkeypatch):
    client = app.test_client()
    login = client.post('/api/auth/login', json={
        'email': 'demo@algotrade.com', 'password': 'demo123',
    })
    headers = {'Authorization': f"Bearer {login.get_json()['token']}"}

    invalid = client.post('/api/alpha-research', headers=headers, json={
        'symbol': 'ALPHA', 'exchange': 'NSE', 'timeframe': '10Y',
    })
    assert invalid.status_code == 400

    def unavailable(instrument, timeframe):
        raise alpha_routes.KiteConfigurationError('Kite is not connected.')

    monkeypatch.setattr(alpha_routes, 'find_instrument', lambda symbol, exchange: {
        'symbol': symbol, 'exchange': exchange,
    })
    monkeypatch.setattr(alpha_routes, 'get_historical_candles', unavailable)
    response = client.post('/api/alpha-research', headers=headers, json={
        'symbol': 'ALPHA', 'exchange': 'NSE', 'timeframe': '1Y',
    })

    assert response.status_code == 503
    assert response.get_json()['message'] == 'Kite is not connected.'
