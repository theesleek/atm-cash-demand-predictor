from __future__ import annotations

from dataclasses import dataclass
import pandas as pd

from app.ml.ensemble import predict_ensemble
from app.ml.model_loader import ModelBundle, load_model_bundle


@dataclass(frozen=True)
class InferenceResult:
	prediction: float
	target: str
	model_name: str
	model_version: str | None


class ProductionInferenceService:
	def __init__(self, bundle: ModelBundle | None = None):
		self.bundle = bundle

	def _get_bundle(self) -> ModelBundle:
		if self.bundle is None:
			self.bundle = load_model_bundle()
		return self.bundle

	@property
	def feature_names(self) -> list[str]:
		return self._get_bundle().features

	def predict(self, features: pd.DataFrame) -> InferenceResult:
		bundle = self._get_bundle()
		expected_features = bundle.features
		if list(features.columns) != expected_features:
			raise ValueError(
				"Inference columns must exactly match model_config.json feature names and order. "
				f"Expected {expected_features}; received {list(features.columns)}."
			)
		if len(features) != 1:
			raise ValueError("Production forecast inference requires exactly one feature row.")

		prediction = predict_ensemble(bundle.models, features)
		return InferenceResult(
			prediction=prediction,
			target=bundle.config["target"],
			model_name="linear_regression+random_forest",
			model_version=bundle.model_version,
		)
