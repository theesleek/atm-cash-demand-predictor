from __future__ import annotations

from app.models.linear_regression_model import LinearRegressionModel
from app.models.random_forest_model import RandomForestModel
from app.models.xgboost_model import XGBoostModel
from app.models.lightgbm_model import LightGBMModel

MODEL_REGISTRY = {
    "linear_regression": LinearRegressionModel,
    "random_forest": RandomForestModel,
    "xgboost": XGBoostModel,
    "lightgbm": LightGBMModel,
}


def get_model(name: str, **kwargs):
    model_cls = MODEL_REGISTRY.get(name)
    if model_cls is None:
        raise ValueError(f"Unsupported model: {name}")
    return model_cls(**kwargs)
