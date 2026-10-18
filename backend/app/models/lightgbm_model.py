from __future__ import annotations

try:
    from lightgbm import LGBMRegressor
except ImportError:  # pragma: no cover
    LGBMRegressor = None

from app.models.base_model import BaseModel


class LightGBMModel(BaseModel):
    def __init__(self, **kwargs):
        if LGBMRegressor is None:
            raise ImportError("lightgbm is not installed. Install it to use the LightGBM model wrapper.")
        self.model = LGBMRegressor(**kwargs)

    def fit(self, X, y):
        self.model.fit(X, y)
        return self

    def predict(self, X):
        return self.model.predict(X)
