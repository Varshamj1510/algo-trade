import numpy as np
import shap
from lime.lime_tabular import LimeTabularExplainer
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestRegressor

try:
    from xgboost import XGBRegressor
except ModuleNotFoundError:  # pragma: no cover - optional dependency in lightweight environments
    class XGBRegressor(RandomForestRegressor):
        def __init__(
            self,
            *,
            n_estimators=140,
            max_depth=3,
            learning_rate=0.035,
            subsample=0.85,
            colsample_bytree=0.85,
            reg_lambda=3,
            objective=None,
            tree_method=None,
            n_jobs=1,
            random_state=17,
            verbosity=0,
            **kwargs,
        ):
            self.n_estimators = n_estimators
            self.max_depth = max_depth
            self.learning_rate = learning_rate
            self.subsample = subsample
            self.colsample_bytree = colsample_bytree
            self.reg_lambda = reg_lambda
            self.objective = objective
            self.tree_method = tree_method
            self.n_jobs = n_jobs
            self.random_state = random_state
            self.verbosity = verbosity
            super().__init__(
                n_estimators=n_estimators,
                max_depth=max_depth,
                min_samples_leaf=5,
                max_features=0.8,
                n_jobs=n_jobs,
                random_state=random_state,
                **kwargs,
            )

from backend.services.indicator_engine import calculate_indicators


FORWARD_HORIZON = 5
MIN_TRAINING_SAMPLES = 120
FACTOR_NAMES = (
    'return_1d', 'momentum_5d', 'momentum_20d', 'momentum_60d',
    'volatility_20d', 'volatility_60d', 'ema20_gap', 'sma20_gap',
    'sma50_gap', 'rsi_14', 'macd_histogram_pct', 'bollinger_percent_b',
    'atr_percent', 'volume_zscore_20d', 'volume_momentum_20d',
    'obv_momentum_20d', 'vwap_deviation', 'intraday_range_pct',
)


class AlphaResearchError(ValueError):
    pass


def _rolling_mean(values, window):
    output = np.full(len(values), np.nan)
    if len(values) < window:
        return output
    cumulative = np.concatenate(([0.0], np.cumsum(values, dtype=float)))
    output[window - 1:] = (cumulative[window:] - cumulative[:-window]) / window
    return output


def _rolling_std(values, window):
    output = np.full(len(values), np.nan)
    for index in range(window - 1, len(values)):
        output[index] = np.std(values[index - window + 1:index + 1])
    return output


def _ratio(numerator, denominator):
    result = np.full(len(numerator), np.nan)
    valid = np.isfinite(numerator) & np.isfinite(denominator) & (denominator != 0)
    result[valid] = numerator[valid] / denominator[valid]
    return result


def _factor_matrix(candles):
    _, series = calculate_indicators(candles)
    close = np.asarray([candle['close'] for candle in candles], dtype=float)
    high = np.asarray([candle['high'] for candle in candles], dtype=float)
    low = np.asarray([candle['low'] for candle in candles], dtype=float)
    volume = np.asarray([candle['volume'] for candle in candles], dtype=float)
    returns = np.full(len(close), np.nan)
    returns[1:] = close[1:] / close[:-1] - 1
    returns_5d = np.full(len(close), np.nan)
    returns_20d = np.full(len(close), np.nan)
    returns_60d = np.full(len(close), np.nan)
    returns_5d[5:] = close[5:] / close[:-5] - 1
    returns_20d[20:] = close[20:] / close[:-20] - 1
    returns_60d[60:] = close[60:] / close[:-60] - 1
    volatility_20d = _rolling_std(returns, 20) * np.sqrt(252)
    volatility_60d = _rolling_std(returns, 60) * np.sqrt(252)

    def indicator_series(name):
        values = series.get(name) or []
        return np.asarray([np.nan if value is None else value for value in values], dtype=float)

    ema_20 = indicator_series('ema_20')
    sma_20 = indicator_series('sma_20')
    sma_50 = np.full(len(close), np.nan)
    if len(close) >= 50:
        cumulative = np.concatenate(([0.0], np.cumsum(close, dtype=float)))
        sma_50[49:] = (cumulative[50:] - cumulative[:-50]) / 50
    macd_histogram = indicator_series('macd_histogram')
    bollinger_upper = indicator_series('bollinger_upper')
    bollinger_lower = indicator_series('bollinger_lower')
    bollinger_range = bollinger_upper - bollinger_lower
    average_volume = _rolling_mean(volume, 20)
    volume_std = _rolling_std(volume, 20)
    volume_zscore = _ratio(volume - average_volume, volume_std)
    obv = indicator_series('obv')
    typical_price = (high + low + close) / 3
    weighted_volume = np.cumsum(typical_price * volume)
    total_volume = np.cumsum(volume)
    vwap = _ratio(weighted_volume, total_volume)
    intraday_range = _ratio(high - low, close)

    matrix = np.column_stack((
        returns,
        returns_5d,
        returns_20d,
        returns_60d,
        volatility_20d,
        volatility_60d,
        _ratio(close - ema_20, ema_20),
        _ratio(close - sma_20, sma_20),
        _ratio(close - sma_50, sma_50),
        indicator_series('rsi_14') / 100,
        _ratio(macd_histogram, close),
        _ratio(close - bollinger_lower, bollinger_range),
        _ratio(indicator_series('atr_14'), close),
        volume_zscore,
        _ratio(volume, average_volume) - 1,
        _ratio(obv - np.roll(obv, 20), np.abs(np.roll(obv, 20)) + 1),
        _ratio(close - vwap, vwap),
        intraday_range,
    ))
    return matrix


def _rank(values):
    order = np.argsort(values, kind='mergesort')
    ranks = np.empty(len(values), dtype=float)
    ranks[order] = np.arange(len(values), dtype=float)
    return ranks


def _information_coefficients(features, target):
    coefficients = []
    for index in range(features.shape[1]):
        factor = features[:, index]
        valid = np.isfinite(factor) & np.isfinite(target)
        if valid.sum() < 10 or np.std(factor[valid]) == 0 or np.std(target[valid]) == 0:
            coefficients.append(0.0)
            continue
        correlation = np.corrcoef(_rank(factor[valid]), _rank(target[valid]))[0, 1]
        coefficients.append(float(correlation) if np.isfinite(correlation) else 0.0)
    return np.asarray(coefficients)


def _standardize(train, values):
    means = np.mean(train, axis=0)
    scales = np.std(train, axis=0)
    scales[scales < 1e-8] = 1
    return (train - means) / scales, (values - means) / scales


def _make_forest():
    return RandomForestRegressor(
        n_estimators=180, max_depth=5, min_samples_leaf=5,
        max_features=0.8, n_jobs=1, random_state=17,
    )


def _make_boosted_trees():
    return XGBRegressor(
        n_estimators=140, max_depth=3, learning_rate=0.035,
        subsample=0.85, colsample_bytree=0.85, reg_lambda=3,
        objective='reg:squarederror', tree_method='hist',
        n_jobs=1, random_state=17, verbosity=0,
    )


def _model_summary(model, train_features, train_target, test_features, test_target):
    model.fit(train_features, train_target)
    prediction = model.predict(test_features)
    rmse = float(np.sqrt(np.mean((prediction - test_target) ** 2)))
    direction_accuracy = float(np.mean(np.sign(prediction) == np.sign(test_target)))
    return {
        'validation_rmse_percent': round(rmse * 100, 3),
        'validation_direction_accuracy_percent': round(direction_accuracy * 100, 1),
    }


def _explain_predictions(models, training, current):
    background = training[-min(100, len(training)):]
    lime_explainer = LimeTabularExplainer(
        training_data=training,
        feature_names=list(FACTOR_NAMES),
        mode='regression',
        random_state=17,
    )
    explanations = {}
    for model_name, model in models.items():
        shap_explainer = shap.TreeExplainer(model, data=background)
        shap_values = np.asarray(shap_explainer.shap_values(current)).reshape(-1)
        shap_base_value = float(np.asarray(shap_explainer.expected_value).reshape(-1)[0])
        lime_result = lime_explainer.explain_instance(
            current[0],
            model.predict,
            num_features=min(6, len(FACTOR_NAMES)),
            num_samples=1000,
        )
        lime_values = sorted(
            lime_result.as_map()[1],
            key=lambda item: abs(item[1]),
            reverse=True,
        )

        explanations[model_name] = {
            'shap': {
                'base_value_percent': round(shap_base_value * 100, 3),
                'features': [
                    {
                        'factor': factor,
                        'value': round(float(current[0][index]), 5),
                        'contribution_percent': round(float(shap_values[index]) * 100, 3),
                    }
                    for index, factor in enumerate(FACTOR_NAMES)
                ],
            },
            'lime': {
                'features': [
                    {
                        'factor': FACTOR_NAMES[index],
                        'value': round(float(current[0][index]), 5),
                        'contribution_percent': round(float(weight) * 100, 3),
                    }
                    for index, weight in lime_values
                ],
            },
        }
    return explanations


def _autoencoder_projection(training, current):
    rng = np.random.default_rng(23)
    input_size = training.shape[1]
    latent_size = min(3, input_size)
    encoder = rng.normal(0, np.sqrt(2 / input_size), (input_size, latent_size))
    decoder = rng.normal(0, np.sqrt(2 / latent_size), (latent_size, input_size))
    encoder_bias = np.zeros(latent_size)
    decoder_bias = np.zeros(input_size)
    learning_rate = 0.01
    for _ in range(140):
        hidden = np.tanh(training @ encoder + encoder_bias)
        reconstruction = np.tanh(hidden @ decoder + decoder_bias)
        output_gradient = 2 * (reconstruction - training) * (1 - reconstruction ** 2) / training.shape[0]
        decoder_gradient = hidden.T @ output_gradient
        decoder_bias_gradient = output_gradient.sum(axis=0)
        hidden_gradient = (output_gradient @ decoder.T) * (1 - hidden ** 2)
        encoder_gradient = training.T @ hidden_gradient
        encoder_bias_gradient = hidden_gradient.sum(axis=0)
        decoder -= learning_rate * decoder_gradient
        decoder_bias -= learning_rate * decoder_bias_gradient
        encoder -= learning_rate * encoder_gradient
        encoder_bias -= learning_rate * encoder_bias_gradient
    latent = np.tanh(current @ encoder + encoder_bias)
    reconstruction = np.tanh(latent @ decoder + decoder_bias)
    error = float(np.mean((current - reconstruction) ** 2))
    return latent[0], error


def _round_list(values, digits=4):
    return [round(float(value), digits) for value in values]


def _dynamic_composition_series(matrix, targets, candles, start_index):
    values = []
    for index in range(start_index, len(candles)):
        if not np.all(np.isfinite(matrix[index])):
            continue
        last_labeled_index = index - FORWARD_HORIZON
        if last_labeled_index < 0:
            continue
        first_labeled_index = max(0, last_labeled_index - 59)
        sample_features = matrix[first_labeled_index:last_labeled_index + 1]
        sample_targets = targets[first_labeled_index:last_labeled_index + 1]
        valid = np.all(np.isfinite(sample_features), axis=1) & np.isfinite(sample_targets)
        sample_features = sample_features[valid]
        sample_targets = sample_targets[valid]
        if len(sample_targets) < 30:
            continue
        coefficients = _information_coefficients(sample_features, sample_targets)
        weights = np.abs(coefficients)
        weight_total = weights.sum()
        weights = weights / weight_total if weight_total else np.full(len(FACTOR_NAMES), 1 / len(FACTOR_NAMES))
        deviation = np.std(sample_features, axis=0)
        deviation[deviation < 1e-8] = 1
        zscores = np.clip((matrix[index] - np.mean(sample_features, axis=0)) / deviation, -3, 3)
        score = float(np.tanh(np.sum(zscores * np.sign(coefficients) * weights)))
        values.append({
            'time': str(candles[index]['time']),
            'score': round(score, 4),
        })
    return values


def analyze_alpha(candles, symbol, exchange, timeframe):
    if len(candles) < MIN_TRAINING_SAMPLES + 70:
        raise AlphaResearchError(
            f'Alpha research needs at least {MIN_TRAINING_SAMPLES + 70} daily candles '
            'to form technical factors and a chronological validation set.'
        )

    matrix = _factor_matrix(candles)
    close = np.asarray([candle['close'] for candle in candles], dtype=float)
    targets = np.full(len(close), np.nan)
    targets[:-FORWARD_HORIZON] = (
        close[FORWARD_HORIZON:] / close[:-FORWARD_HORIZON] - 1
    )
    valid = np.all(np.isfinite(matrix), axis=1) & np.isfinite(targets)
    features = matrix[valid]
    target = targets[valid]
    current = matrix[-1:]
    if len(features) < MIN_TRAINING_SAMPLES:
        raise AlphaResearchError(
            f'Only {len(features)} usable labeled rows were available; '
            f'at least {MIN_TRAINING_SAMPLES} are required.'
        )

    split = max(int(len(features) * 0.8), MIN_TRAINING_SAMPLES)
    split = min(split, len(features) - 20)
    training, validation = features[:split], features[split:]
    training_target, validation_target = target[:split], target[split:]
    scaled_train, _ = _standardize(training, validation)
    _, scaled_current = _standardize(training, current)

    forest_validation = _make_forest()
    xgb_validation = _make_boosted_trees()
    validation_metrics = {
        'random_forest': _model_summary(
            forest_validation, training, training_target, validation, validation_target,
        ),
        'xgboost': _model_summary(
            xgb_validation, training, training_target, validation, validation_target,
        ),
    }
    forest = _make_forest().fit(features, target)
    boosted = _make_boosted_trees().fit(features, target)
    predictions = {
        'random_forest': float(forest.predict(current)[0]),
        'xgboost': float(boosted.predict(current)[0]),
    }
    predictions['ensemble'] = float(np.mean(list(predictions.values())))
    explainability = _explain_predictions(
        {'random_forest': forest, 'xgboost': boosted},
        features,
        current,
    )

    coefficients = _information_coefficients(features, target)
    ic_weights = np.abs(coefficients)
    weight_total = ic_weights.sum()
    if weight_total:
        ic_weights /= weight_total
    else:
        ic_weights = np.full(len(FACTOR_NAMES), 1 / len(FACTOR_NAMES))
    recent_features = features[-60:]
    means = np.mean(recent_features, axis=0)
    deviations = np.std(recent_features, axis=0)
    deviations[deviations < 1e-8] = 1
    current_zscores = np.clip((current[0] - means) / deviations, -3, 3)
    signed_contributions = current_zscores * np.sign(coefficients) * ic_weights
    composite_score = float(np.tanh(signed_contributions.sum()))

    forest_importance = forest.feature_importances_
    xgb_importance = boosted.feature_importances_
    factor_ranking = []
    for index, name in enumerate(FACTOR_NAMES):
        factor_ranking.append({
            'factor': name,
            'rank_ic': round(float(coefficients[index]), 4),
            'absolute_rank_ic': round(float(abs(coefficients[index])), 4),
            'random_forest_importance': round(float(forest_importance[index]), 4),
            'xgboost_importance': round(float(xgb_importance[index]), 4),
            'dynamic_weight': round(float(ic_weights[index]), 4),
            'latest_zscore': round(float(current_zscores[index]), 3),
            'contribution': round(float(signed_contributions[index]), 4),
        })
    factor_ranking.sort(key=lambda row: row['absolute_rank_ic'], reverse=True)

    pca = PCA(n_components=min(3, training.shape[1], training.shape[0]), random_state=17)
    pca.fit(scaled_train)
    pca_values = pca.transform(scaled_current)[0]
    autoencoder_values, reconstruction_error = _autoencoder_projection(scaled_train, scaled_current)
    dynamic_series = _dynamic_composition_series(
        matrix, targets, candles, max(0, len(candles) - 100),
    )

    return {
        'symbol': symbol,
        'exchange': exchange,
        'timeframe': timeframe,
        'provider': 'Kite Connect historical candles',
        'candle_count': len(candles),
        'candle_range': {
            'start': str(candles[0]['time']),
            'end': str(candles[-1]['time']),
        },
        'training_rows': len(features),
        'forward_horizon_sessions': FORWARD_HORIZON,
        'composite_alpha': {
            'score': round(composite_score, 4),
            'direction': 'POSITIVE' if composite_score > 0.1 else 'NEGATIVE' if composite_score < -0.1 else 'NEUTRAL',
            'method': 'Rolling absolute rank-IC weights, signed by information coefficient.',
            'history': dynamic_series,
        },
        'model_predictions': {
            model: round(prediction * 100, 3) for model, prediction in predictions.items()
        },
        'validation': validation_metrics,
        'explainability': {
            'models': explainability,
            'interpretation': (
                'SHAP values are additive local feature contributions for each tree model. '
                'LIME contributions are a local surrogate approximation and may differ from SHAP. '
                'Correlated market factors can share or shift attribution; neither method implies causation.'
            ),
        },
        'factor_ranking': factor_ranking,
        'latent_factors': {
            'pca': {
                f'PC{index + 1}': round(float(value), 4)
                for index, value in enumerate(pca_values)
            },
            'pca_explained_variance_ratio': _round_list(pca.explained_variance_ratio_),
            'autoencoder': {
                f'latent_{index + 1}': round(float(value), 4)
                for index, value in enumerate(autoencoder_values)
            },
            'autoencoder_reconstruction_mse': round(reconstruction_error, 5),
        },
        'disclaimer': (
            'Research outputs are historical model estimates, not investment advice or a guarantee '
            'of future returns. Validation is chronological, but results can overfit and do not '
            'include fees, slippage, or market impact.'
        ),
    }
