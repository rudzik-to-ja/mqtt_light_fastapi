import asyncio
from uuid import UUID

from app.models import LightState, SwitchRecord


class SwitchRepository:
    def __init__(self) -> None:
        self._items: dict[UUID, SwitchRecord] = {}
        self._lock = asyncio.Lock()

    async def add(self, record: SwitchRecord) -> SwitchRecord:
        async with self._lock:
            self._items[record.id] = record
            return record

    async def get(self, switch_id: UUID) -> SwitchRecord | None:
        async with self._lock:
            return self._items.get(switch_id)

    async def list_all(self) -> list[SwitchRecord]:
        async with self._lock:
            return list(self._items.values())

    async def set_state(self, switch_id: UUID, state: LightState) -> SwitchRecord | None:
        async with self._lock:
            record = self._items.get(switch_id)
            if record is None:
                return None
            record.set_state(state)
            return record
