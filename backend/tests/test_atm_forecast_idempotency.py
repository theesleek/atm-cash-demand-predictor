from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError

from app.repositories.forecast_repository import ForecastRepository
from app.services.atm_service import ATMService


class _ForecastRepository:
    def __init__(self, persisted_forecast, created: bool) -> None:
        self.persisted_forecast = persisted_forecast
        self.created = created

    def get_or_create(self, **_kwargs):
        return self.persisted_forecast, self.created


class _AlertService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create_or_update_risk_alert(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["severity"] == "NORMAL":
            return None
        return SimpleNamespace(id=91)


class _NotificationService:
    calls: list[tuple[str, str]] = []

    def __init__(self, _session) -> None:
        pass

    def notification_status(self, event_type: str, event_key: str):
        self.calls.append((event_type, event_key))
        return {"status": "queued"}


def _service(monkeypatch: pytest.MonkeyPatch, *, created: bool, risk_level: str):
    atm = SimpleNamespace(id=7, atm_code="ATM-7", current_cash=5000.0, capacity=10000.0, daily_demand=1000.0)
    generated = SimpleNamespace(
        atm_id="ATM-7",
        predicted_demand=999.0,
        predicted_signed_net_cash_flow=-999.0,
        risk_level="CRITICAL",
        recommended_top_up=900.0,
        current_cash=5000.0,
        capacity=10000.0,
        forecast_date="2026-10-20T00:00:00+00:00",
        target="withdrawal_demand",
        forecast_type="withdrawal_demand",
        model_name="generated-model",
        model_version="model-v1",
        projected_cash=1.0,
        warning_threshold=999.0,
        high_threshold=999.0,
        critical_threshold=999.0,
        safety_buffer=999.0,
        risk_evaluation_status="AVAILABLE",
        risk_evaluation_reason=None,
        source="uploaded_dataset",
    )
    persisted = SimpleNamespace(
        id=24,
        atm_id=atm.id,
        forecast_date=datetime(2026, 10, 20, tzinfo=timezone.utc),
        predicted_demand=100.0,
        predicted_signed_net_cash_flow=-100.0,
        risk_level="WARNING",
        recommended_top_up=50.0,
        risk_evaluation_status="AVAILABLE",
        risk_evaluation_reason=None,
        model_version="model-v1",
        forecast_type="withdrawal_demand",
    )
    alerts = _AlertService()
    assessed_forecasts = []
    assessment = SimpleNamespace(
        current_cash=4900.0,
        predicted_demand=100.0,
        projected_cash=4900.0,
        warning_threshold=80.0,
        high_threshold=60.0,
        critical_threshold=40.0,
        safety_buffer=20.0,
        risk_level=risk_level,
        recommended_top_up=40.0,
    )

    def assess_persisted(forecast, _current_cash, _capacity):
        assessed_forecasts.append(forecast)
        return assessment

    monkeypatch.setattr(ATMService, "_assess_persisted_forecast", staticmethod(assess_persisted))
    monkeypatch.setattr("app.services.atm_service.ForecastService", lambda history_frame: SimpleNamespace(generate_forecast=lambda **_kwargs: generated))
    monkeypatch.setattr("app.services.notification_service.NotificationService", _NotificationService)
    _NotificationService.calls = []
    service = ATMService.__new__(ATMService)
    service.session = object()
    service.repository = SimpleNamespace(get_by_code=lambda _atm_code: atm)
    service.inventory_repository = SimpleNamespace(latest_for_atm=lambda _atm_id: None)
    service.ingestion_service = SimpleNamespace(
        readiness=lambda _atm: {"status": "READY"},
        uploaded_daily_history=lambda _atm: object(),
    )
    service.forecast_repository = _ForecastRepository(persisted, created)
    service.alert_service = alerts
    return service, persisted, generated, alerts, assessed_forecasts, assessment


@pytest.mark.parametrize("created", [True, False], ids=["first-create", "existing-or-concurrent-winner"])
@pytest.mark.parametrize("risk_level", ["NORMAL", "HIGH", "CRITICAL"])
def test_get_forecast_uses_persisted_forecast_for_response_risk_and_notifications(
    monkeypatch: pytest.MonkeyPatch, created: bool, risk_level: str
) -> None:
    service, persisted, generated, alerts, assessed_forecasts, assessment = _service(
        monkeypatch, created=created, risk_level=risk_level
    )

    result = service.get_forecast("ATM-7")

    assert result["forecast_id"] == persisted.id
    assert result["forecast_created"] is created
    assert result["forecast_date"] == persisted.forecast_date.date().isoformat()
    assert result["forecast_type"] == persisted.forecast_type
    assert result["predicted_demand"] == persisted.predicted_demand
    assert result["predicted_demand"] != generated.predicted_demand
    assert result["predicted_signed_net_cash_flow"] == persisted.predicted_signed_net_cash_flow
    assert result["risk_level"] == risk_level
    assert result["projected_cash"] == assessment.projected_cash
    assert result["recommended_top_up"] == assessment.recommended_top_up
    assert result["risk_evaluation_status"] == persisted.risk_evaluation_status
    assert assessed_forecasts == [persisted]

    if risk_level == "NORMAL":
        assert alerts.calls == [
            {
                "atm_id": 7,
                "atm_code": "ATM-7",
                "forecast_id": persisted.id,
                "severity": "NORMAL",
                "projected_cash": assessment.projected_cash,
            }
        ]
        assert result["notification"] == {"status": "not_applicable"}
    else:
        assert alerts.calls == [
            {
                "atm_id": 7,
                "atm_code": "ATM-7",
                "forecast_id": persisted.id,
                "severity": risk_level,
                "projected_cash": assessment.projected_cash,
            }
        ]
        assert _NotificationService.calls == [(f"RISK_{risk_level}", f"RISK_{risk_level}:91")]
        assert result["notification"] == {"status": "queued"}


class _Query:
    def __init__(self, values) -> None:
        self.values = iter(values)

    def filter(self, *_criteria):
        return self

    def one_or_none(self):
        return next(self.values)


class _CommitConflictSession:
    def __init__(self, error: IntegrityError, query_results) -> None:
        self.error = error
        self.query_results = list(query_results)
        self.rollback_count = 0

    def query(self, _model):
        return _Query([self.query_results.pop(0)])

    def add(self, _item) -> None:
        pass

    def commit(self) -> None:
        raise self.error

    def rollback(self) -> None:
        self.rollback_count += 1


def _integrity_error(constraint_name: str, *, sqlstate: str = "23505") -> IntegrityError:
    original = SimpleNamespace(
        pgcode=sqlstate,
        sqlstate=sqlstate,
        diag=SimpleNamespace(constraint_name=constraint_name),
    )
    return IntegrityError("INSERT", {}, original)


def test_get_or_create_recovers_only_from_forecast_identity_conflict() -> None:
    winner = SimpleNamespace(id=24)
    session = _CommitConflictSession(
        _integrity_error(ForecastRepository.FORECAST_IDENTITY_CONSTRAINT),
        [None, winner],
    )

    result, created = ForecastRepository(session).get_or_create(
        atm_id=7,
        predicted_demand=100.0,
        risk_level="NORMAL",
        recommended_top_up=0.0,
        forecast_date=datetime(2026, 10, 20, tzinfo=timezone.utc),
        model_version="model-v1",
        forecast_type="withdrawal_demand",
    )

    assert result is winner
    assert created is False
    assert session.rollback_count == 1


def test_get_or_create_reraises_unrelated_integrity_error() -> None:
    error = _integrity_error("other_constraint")
    session = _CommitConflictSession(error, [None])

    with pytest.raises(IntegrityError) as raised:
        ForecastRepository(session).get_or_create(
            atm_id=7,
            predicted_demand=100.0,
            risk_level="NORMAL",
            recommended_top_up=0.0,
            forecast_date=datetime(2026, 10, 20, tzinfo=timezone.utc),
            model_version="model-v1",
            forecast_type="withdrawal_demand",
        )

    assert raised.value is error
    assert session.rollback_count == 1
    assert session.query_results == []
