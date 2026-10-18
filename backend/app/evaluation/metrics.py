from __future__ import annotations

import numpy as np


def mean_absolute_error(actual: np.ndarray, predicted: np.ndarray) -> float:
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    return float(np.mean(np.abs(actual - predicted)))


def root_mean_squared_error(actual: np.ndarray, predicted: np.ndarray) -> float:
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    return float(np.sqrt(np.mean((actual - predicted) ** 2)))


def s_map_e(actual: np.ndarray, predicted: np.ndarray) -> float:
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    denominator = (np.abs(actual) + np.abs(predicted)) / 2.0
    denominator = np.where(denominator == 0, 1.0, denominator)
    return float(np.mean(np.abs(actual - predicted) / denominator) * 100.0)


def forecast_bias(actual: np.ndarray, predicted: np.ndarray) -> float:
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    return float(np.mean(predicted - actual))


def underforecast_rate(actual: np.ndarray, predicted: np.ndarray) -> float:
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    if actual.size == 0:
        return 0.0
    underforecast_mask = predicted < actual
    return float(np.mean(underforecast_mask.astype(float)))


def r_squared(actual: np.ndarray, predicted: np.ndarray) -> float:
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    if actual.size == 0:
        return 0.0
    total_sum_of_squares = float(np.sum((actual - np.mean(actual)) ** 2))
    if total_sum_of_squares == 0.0:
        return 0.0
    residual_sum_of_squares = float(np.sum((actual - predicted) ** 2))
    return float(1.0 - residual_sum_of_squares / total_sum_of_squares)


def compute_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    return {
        "mae": mean_absolute_error(actual, predicted),
        "rmse": root_mean_squared_error(actual, predicted),
        "smape": s_map_e(actual, predicted),
        "bias": forecast_bias(actual, predicted),
        "r2": r_squared(actual, predicted),
        "underforecast_rate": underforecast_rate(actual, predicted),
    }
