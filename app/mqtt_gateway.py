import asyncio
import json
import os
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import paho.mqtt.client as mqtt

from app.models import LightState

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "fastapi-light-web")

REGISTER_REQUEST_TOPIC = "light/register/request"
REGISTER_ACK_TOPIC = "light/register/ack"
STATE_ACK_TOPIC = "light/+/state"


class MqttTimeoutError(RuntimeError):
    pass


class MqttGateway:
    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=MQTT_CLIENT_ID)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.pending_registration: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self.pending_state: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self.state_callbacks: list[Callable[[UUID, LightState], None]] = []

    def add_state_callback(self, callback: Callable[[UUID, LightState], None]) -> None:
        self.state_callbacks.append(callback)

    async def start(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
        self.client.loop_start()

    async def stop(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()

    async def register_switch(self, switch_id: UUID, name: str, timeout: float = 5.0) -> dict[str, Any]:
        correlation_id = str(uuid4())
        future = self._create_future(self.pending_registration, correlation_id)
        payload = {
            "correlation_id": correlation_id,
            "switch_id": str(switch_id),
            "name": name,
        }
        self.client.publish(REGISTER_REQUEST_TOPIC, json.dumps(payload), qos=1)
        return await self._wait_for_future(future, self.pending_registration, correlation_id, timeout)

    async def set_light_state(self, switch_id: UUID, state: LightState, timeout: float = 5.0) -> dict[str, Any]:
        correlation_id = str(uuid4())
        future = self._create_future(self.pending_state, correlation_id)
        payload = {
            "correlation_id": correlation_id,
            "switch_id": str(switch_id),
            "state": state.value,
        }
        self.client.publish(f"light/{switch_id}/set", json.dumps(payload), qos=1)
        return await self._wait_for_future(future, self.pending_state, correlation_id, timeout)

    def _create_future(self, bucket: dict[str, asyncio.Future], correlation_id: str) -> asyncio.Future:
        if self.loop is None:
            raise RuntimeError("MQTT gateway has not been started")
        future: asyncio.Future[dict[str, Any]] = self.loop.create_future()
        bucket[correlation_id] = future
        return future

    async def _wait_for_future(
        self,
        future: asyncio.Future,
        bucket: dict[str, asyncio.Future],
        correlation_id: str,
        timeout: float,
    ) -> dict[str, Any]:
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise MqttTimeoutError("No MQTT acknowledgement received") from exc
        finally:
            bucket.pop(correlation_id, None)

    def _on_connect(self, client: mqtt.Client, userdata: Any, flags: mqtt.ConnectFlags, reason_code: mqtt.ReasonCode, properties: mqtt.Properties | None) -> None:
        client.subscribe(REGISTER_ACK_TOPIC, qos=1)
        client.subscribe(STATE_ACK_TOPIC, qos=1)

    def _on_message(self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except json.JSONDecodeError:
            return

        topic = message.topic
        if topic == REGISTER_ACK_TOPIC:
            self._complete_pending(self.pending_registration, payload)
            return

        if topic.startswith("light/") and topic.endswith("/state"):
            self._complete_pending(self.pending_state, payload)
            self._notify_state_change(payload)

    def _complete_pending(self, bucket: dict[str, asyncio.Future], payload: dict[str, Any]) -> None:
        correlation_id = payload.get("correlation_id")
        future = bucket.get(correlation_id)
        if self.loop is None or future is None or future.done():
            return
        self.loop.call_soon_threadsafe(future.set_result, payload)

    def _notify_state_change(self, payload: dict[str, Any]) -> None:
        try:
            switch_id = UUID(payload["switch_id"])
            state = LightState(payload["state"])
        except (KeyError, ValueError):
            return

        for callback in self.state_callbacks:
            callback(switch_id, state)
