from datetime import datetime, timezone
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class LightState(str, Enum):
    ON = "on"
    OFF = "off"


class CreateSwitchRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class CreateSwitchResponse(BaseModel):
    id: UUID
    name: str
    state: LightState


class SetStateRequest(BaseModel):
    state: LightState


class SwitchView(BaseModel):
    id: UUID
    name: str
    state: LightState
    created_at: datetime
    updated_at: datetime


class SwitchStats(BaseModel):
    id: UUID
    name: str
    state: LightState
    total_on_seconds: float
    current_session_seconds: float
    total_on_seconds_including_current_session: float


class SwitchRecord:
    def __init__(self, switch_id: UUID, name: str) -> None:
        now = datetime.now(timezone.utc)
        self.id = switch_id
        self.name = name
        self.state = LightState.OFF
        self.created_at = now
        self.updated_at = now
        self.total_on_seconds = 0.0
        self.last_on_at: datetime | None = None

    def set_state(self, new_state: LightState) -> None:
        now = datetime.now(timezone.utc)

        if self.state == LightState.OFF and new_state == LightState.ON:
            self.last_on_at = now

        if self.state == LightState.ON and new_state == LightState.OFF:
            if self.last_on_at is not None:
                self.total_on_seconds += (now - self.last_on_at).total_seconds()
            self.last_on_at = None

        self.state = new_state
        self.updated_at = now

    def current_session_seconds(self) -> float:
        if self.state == LightState.ON and self.last_on_at is not None:
            return (datetime.now(timezone.utc) - self.last_on_at).total_seconds()
        return 0.0

    def as_view(self) -> SwitchView:
        return SwitchView(
            id=self.id,
            name=self.name,
            state=self.state,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    def as_stats(self) -> SwitchStats:
        current = self.current_session_seconds()
        return SwitchStats(
            id=self.id,
            name=self.name,
            state=self.state,
            total_on_seconds=round(self.total_on_seconds, 3),
            current_session_seconds=round(current, 3),
            total_on_seconds_including_current_session=round(self.total_on_seconds + current, 3),
        )
