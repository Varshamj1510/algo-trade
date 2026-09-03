def moving_average(values, window=5):
    if len(values) < window:
        return [sum(values) / len(values)] * len(values)

    result = []
    for idx in range(len(values) - window + 1):
        window_values = values[idx:idx + window]
        result.append(sum(window_values) / window)

    return result
