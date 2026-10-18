from __future__ import annotations

import uuid

import pytest

from app.db.session import SessionLocal, create_db_and_tables, seed_security_data
from app.models.auth import AuditLog, Role, User
from app.models.model_registry import ModelRegistry
from app.services.model_lifecycle_service import ModelLifecycleError, ModelLifecycleService


@pytest.fixture()
def lifecycle_environment(tmp_path):
    create_db_and_tables()
    session = SessionLocal()
    target = f"test_target_{uuid.uuid4().hex}"
    version_a = f"test-{uuid.uuid4().hex}"
    version_b = f"test-{uuid.uuid4().hex}"
    role = session.query(Role).filter(Role.name == "SUPER_ADMIN").one()
    actor = User(username=f"lifecycle-{uuid.uuid4().hex}", password_hash="not-used", role_id=role.id)
    session.add(actor)
    session.commit()
    artifact = tmp_path / "model.joblib"
    artifact.write_bytes(b"valid test artifact")
    yield session, actor.id, target, version_a, version_b, {"model": artifact}
    session.query(AuditLog).filter(AuditLog.entity_type == "MODEL", AuditLog.entity_id.in_([version_a, version_b])).delete(synchronize_session=False)
    session.query(ModelRegistry).filter(ModelRegistry.target == target).delete(synchronize_session=False)
    session.query(User).filter(User.id == actor.id).delete(synchronize_session=False)
    session.commit()
    session.close()


def _register(service, target, version, artifacts, actor_id):
    return service.register_trained(
        target=target,
        model_name="test-model",
        model_version=version,
        dataset_version="dataset-test",
        feature_version="features-test",
        artifacts=artifacts,
        actor_id=actor_id,
    )


def _metrics():
    return {"mae": 1.0, "rmse": 2.0, "bias": 0.1, "r2": 0.9}


def test_lifecycle_requires_evaluation_and_approves_before_activation(lifecycle_environment):
    session, actor_id, target, version_a, _, artifacts = lifecycle_environment
    service = ModelLifecycleService(session)
    _register(service, target, version_a, artifacts, actor_id)
    with pytest.raises(ModelLifecycleError):
        service.approve(version_a, actor_id)
    with pytest.raises(ModelLifecycleError):
        service.activate(version_a, actor_id, artifacts)
    service.evaluate(version_a, _metrics(), actor_id)
    service.approve(version_a, actor_id)
    active = service.activate(version_a, actor_id, artifacts)
    assert active.status == "ACTIVE"


def test_activation_retires_previous_model_and_rollback_is_audited(lifecycle_environment):
    session, actor_id, target, version_a, version_b, artifacts = lifecycle_environment
    service = ModelLifecycleService(session)
    for version in (version_a, version_b):
        _register(service, target, version, artifacts, actor_id)
        service.evaluate(version, _metrics(), actor_id)
        service.approve(version, actor_id)
    service.activate(version_a, actor_id, artifacts)
    service.activate(version_b, actor_id, artifacts)
    assert session.query(ModelRegistry).filter_by(target=target, status="ACTIVE").count() == 1
    assert session.query(ModelRegistry).filter_by(model_version=version_a).one().status == "RETIRED"
    service.retire(version_b, actor_id)
    service.activate(version_a, actor_id, artifacts, rollback=True)
    assert session.query(ModelRegistry).filter_by(model_version=version_a).one().status == "ACTIVE"
    actions = {entry.action for entry in session.query(AuditLog).filter(AuditLog.entity_type == "MODEL", AuditLog.entity_id == version_a).all()}
    assert {"MODEL_TRAINED", "MODEL_EVALUATED", "MODEL_APPROVED", "MODEL_ACTIVATED", "MODEL_RETIRED", "MODEL_ROLLBACK"} <= actions


def test_invalid_artifact_cannot_become_active(lifecycle_environment, tmp_path):
    session, actor_id, target, version_a, _, artifacts = lifecycle_environment
    service = ModelLifecycleService(session)
    _register(service, target, version_a, artifacts, actor_id)
    service.evaluate(version_a, _metrics(), actor_id)
    service.approve(version_a, actor_id)
    missing = tmp_path / "missing.joblib"
    with pytest.raises(ModelLifecycleError):
        service.activate(version_a, actor_id, {"model": missing})
