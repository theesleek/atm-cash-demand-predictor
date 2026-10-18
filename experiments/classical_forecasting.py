from __future__ import annotations

from dataclasses import dataclass

from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.statespace.sarimax import SARIMAX


@dataclass
class ClassicalForecastConfig:
    order: tuple[int, int, int] = (1, 0, 0)
    seasonal_order: tuple[int, int, int, int] = (1, 0, 0, 7)


class ARIMAExperimentalModel:
    def __init__(self, order: tuple[int, int, int] = (1, 0, 0)):
        self.order = order

    def fit(self, series):
        self.model = ARIMA(series, order=self.order, enforce_stationarity=False, enforce_invertibility=False)
        self.results = self.model.fit()
        return self

    def predict(self, periods: int = 1):
        return self.results.forecast(steps=periods)


class SARIMAExperimentalModel:
    def __init__(self, order: tuple[int, int, int] = (1, 0, 0), seasonal_order: tuple[int, int, int, int] = (1, 0, 0, 7)):
        self.order = order
        self.seasonal_order = seasonal_order

    def fit(self, series):
        self.model = SARIMAX(series, order=self.order, seasonal_order=self.seasonal_order, enforce_stationarity=False, enforce_invertibility=False)
        self.results = self.model.fit(disp=False)
        return self

    def predict(self, periods: int = 1):
        return self.results.forecast(steps=periods)


class ProphetExperimentalModel:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def fit(self, series):
        try:
            from prophet import Prophet
        except ImportError as exc:  # pragma: no cover
            raise ImportError("Prophet is not installed in the local environment.") from exc

        self.model = Prophet(**self.kwargs)
        dataframe = series.reset_index().rename(columns={"index": "ds", "demand_target": "y"})
        self.model.fit(dataframe)
        return self

    def predict(self, periods: int = 1):
        if not hasattr(self, "model"):
            raise ValueError("Prophet model must be fitted before prediction.")
        future = self.model.make_future_dataframe(periods=periods)
        return self.model.predict(future)["yhat"].tail(periods).to_numpy()
