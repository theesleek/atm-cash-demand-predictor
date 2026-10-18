from __future__ import annotations

import json
import hashlib
import warnings
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import sklearn
from sklearn.exceptions import InconsistentVersionWarning

from app.core.config import settings


ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
MODEL_NAMES = ("linear_regression", "random_forest")


class ModelConfigurationError(RuntimeError):
	"""Raised when the production model configuration is unusable."""


class ModelArtifactCompatibilityError(ModelConfigurationError):
	"""Raised when a serialized model cannot be loaded in this environment."""


@dataclass(frozen=True)
class ModelBundle:
	models: dict[str, Any]
	config: dict[str, Any]

	@property
	def features(self) -> list[str]:
		return self.config["features"]

	@property
	def model_version(self) -> str | None:
		version = self.config.get("model_version")
		return str(version) if version is not None else "phase4-production-50-50"


@lru_cache(maxsize=4)
def load_model_bundle(artifact_dir: str | None = None) -> ModelBundle:
	directory = Path(artifact_dir).resolve() if artifact_dir else ARTIFACT_DIR.resolve()
	config_path = directory / "model_config.json"
	if not config_path.is_file():
		raise ModelConfigurationError(f"Missing model configuration: {config_path}")

	try:
		config = json.loads(config_path.read_text(encoding="utf-8"))
	except (OSError, json.JSONDecodeError) as exc:
		raise ModelConfigurationError(f"Could not read model configuration: {config_path}") from exc

	features = config.get("features")
	if not isinstance(features, list) or not features or any(not isinstance(name, str) for name in features):
		raise ModelConfigurationError("model_config.json must define a non-empty ordered 'features' list.")
	if len(features) != len(set(features)):
		raise ModelConfigurationError("model_config.json contains duplicate feature names.")
	if config.get("target") != "next_day_cash_flow":
		raise ModelConfigurationError("model_config.json target must be 'next_day_cash_flow'.")
	configured_models = config.get("models")
	if (
		not isinstance(configured_models, list)
		or any(not isinstance(name, str) for name in configured_models)
		or set(configured_models) != set(MODEL_NAMES)
	):
		raise ModelConfigurationError("model_config.json must list linear_regression and random_forest.")
	if config.get("ensemble") != "50/50":
		raise ModelConfigurationError("model_config.json must specify the validated '50/50' ensemble.")
	checksums = config.get("artifact_checksums")
	if not isinstance(checksums, dict) and settings.environment == "production":
		raise ModelConfigurationError("model_config.json must define artifact_checksums.")

	models: dict[str, Any] = {}
	for model_name in MODEL_NAMES:
		artifact_path = (directory / f"{model_name}.joblib").resolve()
		if artifact_path.parent != directory or not artifact_path.is_file():
			raise ModelConfigurationError(f"Missing trained model artifact: {directory / f'{model_name}.joblib'}")
		if isinstance(checksums, dict):
			expected_checksum = checksums.get(model_name)
			try:
				actual_checksum = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
			except OSError:
				if settings.environment == "production":
					raise ModelConfigurationError(f"Could not read artifact for integrity check: {artifact_path.name}")
				actual_checksum = None
			if actual_checksum is not None and (not isinstance(expected_checksum, str) or actual_checksum.lower() != expected_checksum.lower()):
				raise ModelConfigurationError(f"Integrity check failed for {artifact_path.name}.")

		with warnings.catch_warnings(record=True) as captured:
			warnings.simplefilter("always", InconsistentVersionWarning)
			try:
				model = joblib.load(artifact_path)
			except Exception as exc:
				serialized_versions = {
					warning.message.original_sklearn_version
					for warning in captured
					if isinstance(warning.message, InconsistentVersionWarning)
				}
				if serialized_versions:
					saved_version = ", ".join(sorted(serialized_versions))
					raise ModelArtifactCompatibilityError(
						f"Could not load {artifact_path.name} with scikit-learn {sklearn.__version__}; "
						f"artifact estimator version is {saved_version}. Install a compatible scikit-learn "
						"environment; the artifact was not modified."
					) from exc
				raise ModelConfigurationError(f"Could not load trained model artifact: {artifact_path}") from exc
		serialized_versions = {
			warning.message.original_sklearn_version
			for warning in captured
			if isinstance(warning.message, InconsistentVersionWarning)
		}
		if serialized_versions:
			saved_version = ", ".join(sorted(serialized_versions))
			raise ModelArtifactCompatibilityError(
				f"{artifact_path.name} was serialized with scikit-learn {saved_version}, "
				f"but this environment has {sklearn.__version__}. Install a compatible "
				"scikit-learn environment; the artifact was not modified."
			)
		model_features = getattr(model, "feature_names_in_", None)
		if model_features is not None and list(model_features) != features:
			raise ModelConfigurationError(
				f"{artifact_path.name} feature names/order do not match model_config.json."
			)
		model_feature_count = getattr(model, "n_features_in_", None)
		if model_feature_count is not None and model_feature_count != len(features):
			raise ModelConfigurationError(
				f"{artifact_path.name} expects {model_feature_count} features; "
				f"model_config.json defines {len(features)}."
			)
		models[model_name] = model

	return ModelBundle(models=models, config=config)
