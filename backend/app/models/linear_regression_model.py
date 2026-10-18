from __future__ import annotations

from sklearn.linear_model import LinearRegression

from app.models.base_model import BaseModel


class LinearRegressionModel(BaseModel):
    def __init__(self, **kwargs):
        model_kwargs = {key: value for key, value in kwargs.items() if key != "random_state"}
        self.model = LinearRegression(**model_kwargs)

    def fit(self, X, y):
        self.model.fit(X, y)
        return self

    def predict(self, X):
        return self.model.predict(X)
