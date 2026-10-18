from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.atm import ATM, Forecast
from app.models.replenishment import Replenishment


class ReplenishmentRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, replenishment_id: int) -> Replenishment | None:
        return self.session.get(Replenishment, replenishment_id)

    def get_for_update(self, replenishment_id: int) -> Replenishment | None:
        return self.session.query(Replenishment).filter(Replenishment.id == replenishment_id).with_for_update().first()

    def count_by_status(self, status: str) -> int:
        return self.session.query(func.count(Replenishment.id)).filter(Replenishment.status == status).scalar() or 0

    def latest_for_atms(
        self,
        atm_ids: list[int],
        requested_by: int | None = None,
    ) -> dict[int, Replenishment]:
        if not atm_ids:
            return {}
        query = self.session.query(Replenishment).filter(Replenishment.atm_id.in_(atm_ids))
        if requested_by is not None:
            query = query.filter(Replenishment.requested_by == requested_by)
        records = query.order_by(Replenishment.created_at.desc(), Replenishment.id.desc()).all()
        latest: dict[int, Replenishment] = {}
        for replenishment in records:
            latest.setdefault(replenishment.atm_id, replenishment)
        return latest

    def list_for_user(self, user_id: int, role_name: str, status: str | None = None, *, limit: int = 100, offset: int = 0) -> list[Replenishment]:
        query = self.session.query(Replenishment)
        if role_name == "OPERATIONS_OFFICER":
            query = query.filter(Replenishment.requested_by == user_id)
        if status is not None:
            query = query.filter(Replenishment.status == status)
        return query.order_by(Replenishment.created_at.desc(), Replenishment.id.desc()).offset(offset).limit(limit).all()

    def create(self, replenishment: Replenishment, *, commit: bool = True) -> Replenishment:
        self.session.add(replenishment)
        if commit:
            self._commit()
        else:
            self.session.flush()
        self.session.refresh(replenishment)
        return replenishment

    def save(self, replenishment: Replenishment, *, commit: bool = True) -> Replenishment:
        self.session.add(replenishment)
        if commit:
            self._commit()
        else:
            self.session.flush()
        self.session.refresh(replenishment)
        return replenishment

    def _commit(self) -> None:
        try:
            self.session.commit()
        except SQLAlchemyError:
            self.session.rollback()
            raise

    def get_atm(self, atm_code: str) -> ATM | None:
        return self.session.query(ATM).filter(ATM.atm_code == atm_code).first()

    def get_atm_by_id(self, atm_id: int) -> ATM | None:
        return self.session.get(ATM, atm_id)

    def get_forecast(self, forecast_id: int) -> Forecast | None:
        return self.session.get(Forecast, forecast_id)

    def latest_forecast_for_atm(self, atm_id: int) -> Forecast | None:
        return (
            self.session.query(Forecast)
            .filter(Forecast.atm_id == atm_id)
            .order_by(Forecast.forecast_date.desc(), Forecast.id.desc())
            .first()
        )
