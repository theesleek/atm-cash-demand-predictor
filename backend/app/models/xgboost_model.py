from __future__ import annotations

try:
    from xgboost import XGBRegressor
except ImportError:  # pragma: no cover
    XGBRegressor = None

from app.models.base_model import BaseModel


class XGBoostModel(BaseModel):
    def __init__(self, **kwargs):
        if XGBRegressor is None:
            raise ImportError("xgboost is not installed. Install it to use the XGBoost model wrapper.")
        self.model = XGBRegressor(**kwargs)

    def fit(self, X, y):
        self.model.fit(X, y)
        return self

    def predict(self, X):
        return self.model.predict(X)
