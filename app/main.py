import asyncio
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, status

from app.models import CreateSwitchRequest, CreateSwitchResponse, LightState, SetStateRequest, SwitchRecord, SwitchStats, SwitchView
from app.mqtt_gateway import MqttGateway, MqttTimeoutError
from app.repository import SwitchRepository

repo = SwitchRepository()
mqtt_gateway = MqttGateway()


def save_external_state_change(switch_id: UUID, state: LightState) -> None:
    # Callback jest wywoływany z wątku klienta MQTT, dlatego aktualizacja repozytorium
    # jest przekazywana do pętli zdarzeń aplikacji FastAPI.
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = mqtt_gateway.loop

    if loop is not None:
        asyncio.run_coroutine_threadsafe(repo.set_state(switch_id, state), loop)


@asynccontextmanager
async def lifespan(app: FastAPI):
    mqtt_gateway.add_state_callback(save_external_state_change)
    await mqtt_gateway.start()
    yield
    await mqtt_gateway.stop()


app = FastAPI(title="MQTT Light Switch API", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/switches", response_model=CreateSwitchResponse, status_code=status.HTTP_201_CREATED)
async def create_switch(body: CreateSwitchRequest) -> CreateSwitchResponse:
    switch_id = uuid4()

    try:
        ack = await mqtt_gateway.register_switch(switch_id=switch_id, name=body.name)
    except MqttTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Switch was not registered because MQTT acknowledgement was not received.",
        ) from exc

    if ack.get("status") != "ok" or ack.get("switch_id") != str(switch_id):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Invalid MQTT registration acknowledgement.",
        )

    record = await repo.add(SwitchRecord(switch_id=switch_id, name=body.name))
    return CreateSwitchResponse(id=record.id, name=record.name, state=record.state)


@app.get("/switches", response_model=list[SwitchView])
async def list_switches() -> list[SwitchView]:
    return [item.as_view() for item in await repo.list_all()]


@app.get("/switches/{switch_id}", response_model=SwitchView)
async def get_switch(switch_id: UUID) -> SwitchView:
    record = await repo.get(switch_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Switch not found")
    return record.as_view()


@app.post("/switches/{switch_id}/state", response_model=SwitchView)
async def set_switch_state(switch_id: UUID, body: SetStateRequest) -> SwitchView:
    record = await repo.get(switch_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Switch not found")

    try:
        ack = await mqtt_gateway.set_light_state(switch_id=switch_id, state=body.state)
    except MqttTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Light state was not changed because MQTT acknowledgement was not received.",
        ) from exc

    if ack.get("status") != "ok" or ack.get("switch_id") != str(switch_id) or ack.get("state") != body.state.value:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Invalid MQTT state acknowledgement.")

    updated = await repo.set_state(switch_id, body.state)
    assert updated is not None
    return updated.as_view()


@app.get("/switches/{switch_id}/stats", response_model=SwitchStats)
async def get_switch_stats(switch_id: UUID) -> SwitchStats:
    record = await repo.get(switch_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Switch not found")
    return record.as_stats()
