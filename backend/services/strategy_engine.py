import json

from backend.services.condition_evaluator import (
    evaluate_condition_group,
    validate_condition_group,
    validate_indicator_values,
)


def validate_strategy_rules(data):
    buy_logic = str(data.get('buy_logic', 'AND')).strip().upper()
    sell_logic = str(data.get('sell_logic', 'AND')).strip().upper()
    buy_conditions = validate_condition_group(data.get('buy_conditions'), buy_logic, 'BUY')
    sell_conditions = validate_condition_group(data.get('sell_conditions'), sell_logic, 'SELL')
    return {
        'buy_logic': buy_logic,
        'buy_conditions': buy_conditions,
        'sell_logic': sell_logic,
        'sell_conditions': sell_conditions,
    }


def encode_conditions(conditions):
    return json.dumps(conditions, separators=(',', ':'))


def preview_strategy(rules, indicator_values):
    values = validate_indicator_values(indicator_values, [
        rules['buy_conditions'],
        rules['sell_conditions'],
    ])
    buy_matches, buy_results = evaluate_condition_group(
        rules['buy_conditions'], rules['buy_logic'], values
    )
    sell_matches, sell_results = evaluate_condition_group(
        rules['sell_conditions'], rules['sell_logic'], values
    )
    signal = 'BUY' if buy_matches and not sell_matches else 'SELL' if sell_matches and not buy_matches else 'HOLD'
    return {
        'signal': signal,
        'buy_matches': buy_matches,
        'sell_matches': sell_matches,
        'buy_results': buy_results,
        'sell_results': sell_results,
        'conflict': buy_matches and sell_matches,
    }
