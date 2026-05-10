import json
import logging
import os
from dataclasses import dataclass
from uuid import UUID

import paho.mqtt.client as mqtt

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_CLIENT_ID = os.getenv("MQTT_SIMULATOR_CLIENT_ID", "light-controller-simulator")

REGISTER_REQUEST_TOPIC = "light/register/request"
REGISTER_ACK_TOPIC = "light/register/ack"
SET_STATE_TOPIC = "light/+/set"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("light-controller-simulator")


@dataclass
class SimulatedSwitch:
    switch_id: UUID
    name: str
    state: str = "off"


class LightControllerSimulator:
    def __init__(self) -> None:
        self.switches: dict[UUID, SimulatedSwitch] = {}
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=MQTT_CLIENT_ID)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def start(self) -> None:
        self.client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
        logger.info("Simulator connected to MQTT broker %s:%s", MQTT_HOST, MQTT_PORT)
        self.client.loop_forever()

    def on_connect(self, client: mqtt.Client, userdata, flags, reason_code, properties) -> None:
        client.subscribe(REGISTER_REQUEST_TOPIC, qos=1)
        client.subscribe(SET_STATE_TOPIC, qos=1)
        logger.info("Subscribed to %s and %s", REGISTER_REQUEST_TOPIC, SET_STATE_TOPIC)

    def on_message(self, client: mqtt.Client, userdata, message: mqtt.MQTTMessage) -> None:
        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except json.JSONDecodeError:
            logger.warning("Invalid JSON on topic %s", message.topic)
            return

        if message.topic == REGISTER_REQUEST_TOPIC:
            self.handle_register(payload)
            return

        if message.topic.startswith("light/") and message.topic.endswith("/set"):
            self.handle_set_state(payload)
            return

    def handle_register(self, payload: dict) -> None:
        try:
            switch_id = UUID(payload["switch_id"])
            name = str(payload["name"])
            correlation_id = str(payload["correlation_id"])
        except (KeyError, ValueError) as exc:
            logger.warning("Invalid registration payload: %s", exc)
            return

        self.switches[switch_id] = SimulatedSwitch(switch_id=switch_id, name=name)
        logger.info("Registered switch: id=%s name=%s", switch_id, name)

        ack = {
            "correlation_id": correlation_id,
            "switch_id": str(switch_id),
            "status": "ok",
        }
        self.client.publish(REGISTER_ACK_TOPIC, json.dumps(ack), qos=1)

    def handle_set_state(self, payload: dict) -> None:
        try:
            switch_id = UUID(payload["switch_id"])
            state = str(payload["state"])
            correlation_id = str(payload["correlation_id"])
        except (KeyError, ValueError) as exc:
            logger.warning("Invalid state payload: %s", exc)
            return

        if state not in {"on", "off"}:
            logger.warning("Invalid requested state: %s", state)
            return

        switch = self.switches.get(switch_id)
        if switch is None:
            logger.warning("State change requested for unknown switch: %s", switch_id)
            status = "unknown_switch"
        else:
            switch.state = state
            status = "ok"
            logger.info("Light state changed: id=%s name=%s state=%s", switch.switch_id, switch.name, switch.state)

        response = {
            "correlation_id": correlation_id,
            "switch_id": str(switch_id),
            "state": state,
            "status": status,
        }
        self.client.publish(f"light/{switch_id}/state", json.dumps(response), qos=1)


if __name__ == "__main__":
    LightControllerSimulator().start()
