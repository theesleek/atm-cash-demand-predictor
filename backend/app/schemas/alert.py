from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AlertActionRequest(BaseModel):
    source: Literal["WEB", "API"] = "API"