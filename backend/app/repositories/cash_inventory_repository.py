from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.atm import CashInventory


class CashInventoryRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_for_atm(self, atm_id: int) -> list[CashInventory]:
        return self.session.query(CashInventory).filter(CashInventory.atm_id == atm_id).order_by(CashInventory.inventory_date.desc()).all()

    def latest_for_atm(self, atm_id: int) -> CashInventory | None:
        return self.session.query(CashInventory).filter(CashInventory.atm_id == atm_id).order_by(CashInventory.inventory_date.desc()).first()
