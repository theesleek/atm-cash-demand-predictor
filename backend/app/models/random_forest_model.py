from __future__ import annotations

from sklearn.ensemble import RandomForestRegressor

from app.models.base_model import BaseModel


class RandomForestModel(BaseModel):
    def __init__(self, n_estimators: int = 200, random_state: int = 42, **kwargs):
        self.model = RandomForestRegressor(n_estimators=n_estimators, random_state=random_state, **kwargs)

    def fit(self, X, y):
        self.model.fit(X, y)
        return self

    def predict(self, X):
        return self.model.predict(X)
