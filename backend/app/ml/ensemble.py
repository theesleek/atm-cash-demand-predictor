from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from app.ml.model_loader import MODEL_NAMES, ModelConfigurationError


def predict_ensemble(models: Mapping[str, Any], features: pd.DataFrame) -> float:
	missing_models = set(MODEL_NAMES) - set(models)
	if missing_models:
		raise ModelConfigurationError(
			f"The production ensemble is missing models: {', '.join(sorted(missing_models))}."
		)
	if len(features) != 1:
		raise ValueError("Forecast inference requires exactly one feature row.")

	predictions: dict[str, float] = {}
	for model_name in MODEL_NAMES:
		values = np.asarray(models[model_name].predict(features), dtype=float).reshape(-1)
		if values.size != 1 or not np.isfinite(values[0]):
			raise ValueError(f"{model_name} returned an invalid forecast prediction.")
		predictions[model_name] = float(values[0])

	return 0.5 * predictions["linear_regression"] + 0.5 * predictions["random_forest"]
