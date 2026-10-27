import math


INDICATORS = {
    'price': 'Price',
    'rsi': 'RSI',
    'macd': 'MACD',
    'ema': 'EMA',
    'sma': 'SMA',
    'bollinger_upper': 'Bollinger upper band',
    'bollinger_middle': 'Bollinger middle band',
    'bollinger_lower': 'Bollinger lower band',
    'moving_average': 'Moving average',
    'vwap': 'VWAP',
    'atr': 'ATR',
    'obv': 'OBV',
    'volume': 'Volume',
}

SIGNED_INDICATORS = {'macd', 'obv'}

OPERATORS = {
    'gt': ('>', lambda actual, expected: actual > expected),
    'gte': ('>=', lambda actual, expected: actual >= expected),
    'lt': ('<', lambda actual, expected: actual < expected),
    'lte': ('<=', lambda actual, expected: actual <= expected),
    'eq': ('=', lambda actual, expected: actual == expected),
}

MAX_CONDITIONS_PER_SIDE = 10


def validate_condition_group(conditions, logic, label):
    if logic not in {'AND', 'OR'}:
        raise ValueError(f'{label} logic must be AND or OR.')
    if not isinstance(conditions, list) or not 1 <= len(conditions) <= MAX_CONDITIONS_PER_SIDE:
        raise ValueError(f'{label} must contain between 1 and {MAX_CONDITIONS_PER_SIDE} conditions.')

    validated = []
    for index, condition in enumerate(conditions, start=1):
        if not isinstance(condition, dict):
            raise ValueError(f'{label} condition {index} must be an object.')
        indicator = condition.get('indicator')
        operator = condition.get('operator')
        threshold = condition.get('value')
        if not isinstance(indicator, str) or indicator not in INDICATORS:
            raise ValueError(f'{label} condition {index} uses an unsupported indicator.')
        if not isinstance(operator, str) or operator not in OPERATORS:
            raise ValueError(f'{label} condition {index} uses an unsupported comparison.')
        compare_to = condition.get('compare_to')
        if compare_to is not None:
            if not isinstance(compare_to, str) or compare_to not in INDICATORS or compare_to == indicator:
                raise ValueError(f'{label} condition {index} uses an unsupported comparison indicator.')
            if threshold is not None:
                raise ValueError(f'{label} condition {index} must compare to either a number or an indicator.')
            validated.append({
                'indicator': indicator,
                'operator': operator,
                'compare_to': compare_to,
            })
        else:
            if isinstance(threshold, bool):
                raise ValueError(f'{label} condition {index} value must be a valid number.')
            try:
                threshold = float(threshold)
            except (TypeError, ValueError):
                raise ValueError(f'{label} condition {index} value must be a valid number.') from None
            if not math.isfinite(threshold):
                raise ValueError(f'{label} condition {index} value must be finite.')
            if indicator not in SIGNED_INDICATORS and threshold < 0:
                raise ValueError(f'{INDICATORS[indicator]} condition values cannot be negative.')
            if indicator == 'rsi' and threshold > 100:
                raise ValueError(f'{label} RSI condition values must be between 0 and 100.')
            validated.append({
                'indicator': indicator,
                'operator': operator,
                'value': threshold,
            })
    return validated


def evaluate_condition_group(conditions, logic, indicator_values):
    outcomes = []
    results = []
    for condition in conditions:
        indicator = condition['indicator']
        if indicator not in indicator_values:
            raise ValueError(f'{INDICATORS[indicator]} value is required for preview.')
        actual = indicator_values[indicator]
        if isinstance(actual, bool):
            raise ValueError(f'{INDICATORS[indicator]} preview value must be a valid number.')
        try:
            actual = float(actual)
        except (TypeError, ValueError):
            raise ValueError(f'{INDICATORS[indicator]} preview value must be a valid number.') from None
        if not math.isfinite(actual) or (indicator not in SIGNED_INDICATORS and actual < 0):
            raise ValueError(f'{INDICATORS[indicator]} preview value is invalid.')
        if indicator == 'rsi' and actual > 100:
            raise ValueError('RSI preview value must be between 0 and 100.')
        if 'compare_to' in condition:
            compare_to = condition['compare_to']
            if compare_to not in indicator_values:
                raise ValueError(f'{INDICATORS[compare_to]} value is required for preview.')
            expected = indicator_values[compare_to]
            if isinstance(expected, bool):
                raise ValueError(f'{INDICATORS[compare_to]} preview value must be a valid number.')
            try:
                expected = float(expected)
            except (TypeError, ValueError):
                raise ValueError(f'{INDICATORS[compare_to]} preview value must be a valid number.') from None
            if not math.isfinite(expected) or (compare_to not in SIGNED_INDICATORS and expected < 0):
                raise ValueError(f'{INDICATORS[compare_to]} preview value is invalid.')
            if compare_to == 'rsi' and expected > 100:
                raise ValueError('RSI preview value must be between 0 and 100.')
            threshold_label = INDICATORS[compare_to]
        else:
            expected = condition['value']
            threshold_label = f'{expected:g}'
        operator_label, compare = OPERATORS[condition['operator']]
        matched = compare(actual, expected)
        outcomes.append(matched)
        results.append({
            **condition,
            'actual': actual,
            'expected': expected,
            'matched': matched,
            'label': f"{INDICATORS[indicator]} {operator_label} {threshold_label}",
        })
    return (all(outcomes) if logic == 'AND' else any(outcomes)), results


def validate_indicator_values(values, conditions):
    if not isinstance(values, dict):
        raise ValueError('Indicator values must be an object.')
    required_indicators = {
        indicator
        for group in conditions
        for condition in group
        for indicator in (condition['indicator'], condition.get('compare_to'))
        if indicator is not None
    }
    normalized = {}
    for indicator in required_indicators:
        if indicator not in values:
            raise ValueError(f'{INDICATORS[indicator]} value is required for preview.')
        value = values[indicator]
        if isinstance(value, bool):
            raise ValueError(f'{INDICATORS[indicator]} preview value must be a valid number.')
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise ValueError(f'{INDICATORS[indicator]} preview value must be a valid number.') from None
        if not math.isfinite(value) or (indicator not in SIGNED_INDICATORS and value < 0):
            raise ValueError(f'{INDICATORS[indicator]} preview value is invalid.')
        if indicator == 'rsi' and value > 100:
            raise ValueError('RSI preview value must be between 0 and 100.')
        normalized[indicator] = value
    return normalized
