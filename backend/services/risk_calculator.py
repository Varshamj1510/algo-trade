import math


def calculate_protection(data):
    side = str(data.get('side', '')).strip().upper()
    if side not in {'BUY', 'SELL'}:
        raise ValueError('Side must be BUY (long) or SELL (short).')

    entry_price = _positive_number(data, 'entry_price', 'Entry price')
    stop_loss_price = _positive_number(data, 'stop_loss_price', 'Stop-loss price')
    account_balance = _positive_number(data, 'account_balance', 'Account balance')
    risk_percent = _positive_number(data, 'risk_percent', 'Risk percent')
    if risk_percent > 100:
        raise ValueError('Risk percent must be 100 or less.')

    stop_distance = entry_price - stop_loss_price if side == 'BUY' else stop_loss_price - entry_price
    if stop_distance <= 0:
        raise ValueError('Stop-loss must be below entry for BUY and above entry for SELL.')

    take_profit_price = _optional_positive_number(data, 'take_profit_price', 'Take-profit price')
    if take_profit_price is not None:
        target_distance = (
            take_profit_price - entry_price if side == 'BUY'
            else entry_price - take_profit_price
        )
        if target_distance <= 0:
            raise ValueError('Take-profit must be above entry for BUY and below entry for SELL.')
    else:
        target_distance = None

    quantity = _optional_positive_number(data, 'quantity', 'Quantity')
    trailing_percent = _optional_positive_number(data, 'trailing_percent', 'Trailing-stop percent')
    if trailing_percent is not None and trailing_percent >= 100:
        raise ValueError('Trailing-stop percent must be less than 100.')

    risk_amount = account_balance * risk_percent / 100
    position_size = risk_amount / stop_distance
    max_loss = stop_distance * quantity if quantity is not None else None
    potential_profit = (
        target_distance * quantity
        if target_distance is not None and quantity is not None
        else None
    )
    risk_reward_ratio = target_distance / stop_distance if target_distance is not None else None
    trailing_stop_price = None
    if trailing_percent is not None:
        trailing_stop_price = entry_price * (
            1 - trailing_percent / 100 if side == 'BUY' else 1 + trailing_percent / 100
        )

    return {
        'side': side,
        'entry_price': _rounded(entry_price),
        'stop_loss_price': _rounded(stop_loss_price),
        'take_profit_price': _rounded(take_profit_price),
        'stop_distance_per_unit': _rounded(stop_distance),
        'risk_amount': _rounded(risk_amount),
        'position_size': _rounded(position_size),
        'quantity': _rounded(quantity),
        'maximum_loss': _rounded(max_loss),
        'potential_profit': _rounded(potential_profit),
        'risk_reward_ratio': _rounded(risk_reward_ratio),
        'trailing_percent': _rounded(trailing_percent),
        'trailing_stop_price': _rounded(trailing_stop_price),
    }


def _positive_number(data, key, label):
    value = _optional_positive_number(data, key, label)
    if value is None:
        raise ValueError(f'{label} is required.')
    return value


def _optional_positive_number(data, key, label):
    raw_value = data.get(key)
    if raw_value in (None, ''):
        return None
    if isinstance(raw_value, bool):
        raise ValueError(f'{label} must be a valid number greater than zero.')
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        raise ValueError(f'{label} must be a valid number greater than zero.') from None
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f'{label} must be a valid number greater than zero.')
    return value


def _rounded(value):
    if value is None:
        return None
    if not math.isfinite(value):
        raise ValueError('Calculated values exceed the supported numeric range.')
    return round(value, 2)
