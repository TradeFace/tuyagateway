"""TuyaMQTT."""
import time
import paho.mqtt.client as mqtt
import json
from .device_thread import DeviceThread
from .configure import logger
from .device import Device
from tuyagateway.transform.homeassistant import Transform


def connack_string(state):
    """Return mqtt connection string."""
    states = [
        "Connection successful",
        "Connection refused - incorrect protocol version",
        "Connection refused - invalid client identifier",
        "Connection refused - server unavailable",
        "Connection refused - bad username or password",
        "Connection refused - not authorised",
    ]
    return states[state]


def on_mqtt_connect(client, userdata, flags, return_code):
    """Write something useful."""
    logger.info(
        "MQTT Connection state: %s for topic %s",
        connack_string(return_code),
        "tuyagateway/#",
    )
    client.subscribe([("homeassistant/#", 0), ("tuyagateway/#", 0)])


# TODO: why is this a class? declass
class TuyaMQTT:
    """Manages a set of TuyaMQTTEntities."""

    delay = 0.1
    config = []
    _devices = {}
    _transform = {}
    worker_threads = {}
    _ha_config = {}
    _ha_component = {}

    def __init__(self, config):
        """Initialize DeviceThread."""
        self.config = config
        self.mqtt_client = mqtt.Client()

    def mqtt_connect(self):
        """Create MQTT client."""
        self.mqtt_client.enable_logger()
        if self.config["MQTT"]["user"] and self.config["MQTT"]["pass"]:
            self.mqtt_client.username_pw_set(
                self.config["MQTT"]["user"], self.config["MQTT"]["pass"]
            )
        self.mqtt_client.connect_async(
            self.config["MQTT"].get("host", "127.0.0.1"),
            int(self.config["MQTT"].get("port", 1883)),
            60,
        )
        self.mqtt_client.on_connect = on_mqtt_connect
        self.mqtt_client.on_message = self.on_mqtt_message
        self.mqtt_client.loop_start()

    def _start_device_thread(self, key, device, transform):
        thread_object = DeviceThread(key, device, transform, self)
        thread_object.setName(f"tuyagateway_{key}")
        thread_object.start()
        self.worker_threads[key] = thread_object

    def _find_device_keys(self, key: str, ip_address=None):
        # TODO: use filter
        keys = []
        for ent_key, item in self._devices.items():
            if item.get_ip_address() == ip_address:
                keys.append(ent_key)

        if key in self._devices:
            keys.append(key)

        return keys

    def _handle_discover_message(self, topic: dict, message):
        """Handle discover message from GismoCaster.

        If a discover message arrives we kill the thread for the
        device (if any), and restart with new config (if any)
        """

        logger.info(
            "discovery message received %s topic %s retained %s ",
            str(message.payload.decode("utf-8")),
            message.topic,
            message.retain,
        )

        discover_dict = {}
        try:
            if message.payload:
                discover_dict = json.loads(message.payload)
        except Exception as ex:
            print("_handle_discover_message", ex)
            return

        device_key = topic[2]
        device = Device(discover_dict)
        # TODO: check ha_publish
        if not device.is_valid():
            return

        transform = Transform(discover_dict)

        device_keys = self._find_device_keys(device_key, device.get_ip_address())

        for device_key in device_keys:
            if device_key in self.worker_threads:
                try:
                    self.worker_threads[device_key].stop_entity()
                    self.worker_threads[device_key].join()
                except Exception:
                    pass

        if not device.is_valid():
            return

        self._devices[device.get_key()] = device
        self._transform[device.get_key()] = transform

        # push the ha config
        for id_int, ha_dict in self._ha_config[device.get_key()].items():
            self._transform[device.get_key()].set_homeassistant_config(id_int, ha_dict)

        self._start_device_thread(device.get_key(), device, transform)

    def _handle_ha_config_message(self, topic: dict, message):
        if not message.payload:
            return

        try:
            ha_dict = json.loads(message.payload)
        except Exception as ex:
            print(ex)
            return

        # add context to ha_dict
        ha_dict["device_component"] = topic[1]

        if "uniq_id" not in ha_dict:
            # skip it for now
            return

        if topic[2] != ha_dict["uniq_id"]:
            return
        id_parts = ha_dict["uniq_id"].split("_")
        if id_parts[0] not in ha_dict["device"]["identifiers"]:
            return
        if id_parts[0] not in self._ha_config:
            self._ha_config[id_parts[0]] = {}
        if not id_parts[1].isnumeric():
            return

        id_int = int(id_parts[1])
        self._ha_config[id_parts[0]][id_int] = ha_dict

        # transformer might not yet be instanciated
        if id_parts[0] in self._transform:
            self._transform[id_parts[0]].set_homeassistant_config(id_int, ha_dict)

    # async def get_ha_component(self, key: str):
    #     """Get the HomeAssistant component configuration."""
    #     # wait till conf available
    #     while key not in self._ha_component:
    #         asyncio.sleep(0.1)
    #     return self._ha_component[key]

    def _handle_ha_component_message(self, topic: dict, message):

        logger.info(
            "config message topic %s retained %s ", message.topic, message.retain,
        )
        try:
            payload_dict = json.loads(message.payload)
        except Exception as ex:
            print(ex)

        component_name = topic[3]
        self._ha_component[component_name] = payload_dict

        for _, transform in self._transform.items():
            transform.set_component_config(payload_dict, component_name)

    def on_mqtt_message(self, client, userdata, message):
        """MQTT message callback, executed in the MQTT client's context."""
        topic_parts = message.topic.split("/")
        # print(topic_parts)
        if (
            topic_parts[0] == "homeassistant"
            and topic_parts[len(topic_parts) - 1] == "config"
        ):
            self._handle_ha_config_message(topic_parts, message)
            return
        if topic_parts[0] == "tuyagateway":

            if topic_parts[1] == "config" and topic_parts[2] == "homeassistant":
                self._handle_ha_component_message(topic_parts, message)
                return

            if topic_parts[1] == "discovery":
                self._handle_discover_message(topic_parts, message)
                return

    def main_loop(self):
        """Send / receive from tuya devices."""
        try:
            self.mqtt_connect()
            # TODO: wait for config to arrive and start threads that have full config
            # ha conf
            # gc conf
            # ha component conf
            # TODO: when solved, remove main param transform
            while True:
                time.sleep(self.delay)

        except KeyboardInterrupt:
            for _, thread in self.worker_threads.items():
                thread.stop_entity()
                thread.join()
