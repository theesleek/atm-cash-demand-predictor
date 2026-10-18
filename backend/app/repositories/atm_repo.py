from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.atm import ATM


class ATMRepository:
    def __init__(self, session: Session):
        self.session = session

    def list(self, *, limit: int = 100, offset: int = 0) -> list[ATM]:
        return self.session.query(ATM).order_by(ATM.atm_code.asc()).offset(offset).limit(limit).all()

    def get_by_code(self, atm_code: str) -> ATM | None:
        return self.session.query(ATM).filter(ATM.atm_code == atm_code).first()

    def get(self, atm_id: int) -> ATM | None:
        return self.session.get(ATM, atm_id)

    def count(self) -> int:
        return self.session.query(ATM).count()
