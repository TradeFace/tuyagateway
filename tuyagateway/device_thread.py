"""DeviceThread."""
import time
import paho.mqtt.client as mqtt
import json
import queue
import threading
from .configure import logger
from .device import Device
from tuyagateway.transform.homeassistant import Transform
from tuyaface.tuyaclient import TuyaClient


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


class DeviceThread(threading.Thread):
    """Run thread for device."""

    delay = 0.1
    transform_delay = 10

    def __init__(self, key: str, device: Device, transform: Transform, parent):
        """Initialize DeviceThread."""
        super().__init__()
        self.key = key
        self.name = key  # Set thread name to key

        self._device = device
        self.parent = parent
        self.config = self.parent.config

        self._transform = transform

        self._availability = False
        self._tuya_client = None
        self.stop = threading.Event()
        self._mqtt_client = mqtt.Client()

        self.command_queue = queue.Queue()

    def mqtt_connect(self):
        """Create MQTT client."""
        self._mqtt_client.enable_logger()
        if self.config["MQTT"]["user"] and self.config["MQTT"]["pass"]:
            self._mqtt_client.username_pw_set(
                self.config["MQTT"]["user"], self.config["MQTT"]["pass"]
            )

        # BUG: only last item is set, does it take a list?
        # problem only 1 per connection
        for item in self._transform.get_publish_availability(False):
            self._mqtt_client.will_set(
                item["topic"], item["payload"], retain=True,
            )

        self._mqtt_client.connect_async(
            self.config["MQTT"].get("host", "127.0.0.1"),
            int(self.config["MQTT"].get("port", 1883)),
            60,
        )
        self._mqtt_client.on_connect = self.on_mqtt_connect
        self._mqtt_client.on_message = self.on_mqtt_message
        self._mqtt_client.loop_start()

    def on_mqtt_message(self, client, userdata, message):
        """MQTT message callback, executed in the MQTT client's context."""
        if message.topic[-7:] != "command":
            return

        logger.debug(
            "(%s) topic %s retained %s message received %s",
            self._device.get_ip_address(),
            message.topic,
            message.retain,
            str(message.payload.decode("utf-8")),
        )

        # We're in the MQTT client's context, queue a call to handle the message
        self.command_queue.put((self._handle_mqtt_message, (message,)))

    def _handle_mqtt_message(self, message):

        topic_parts = message.topic.split("/")
        try:
            payload = json.loads(message.payload)
        except Exception:
            payload = message.payload

        self._transform.set_input_payload(topic_parts, payload)
        gw_payload = self._transform.get_gateway_payload()
        # print(gw_payload)

        self._device.set_gateway_payload(gw_payload)
        device_payload = self._device.get_device_payload()

        self.set_status(device_payload)

    def on_mqtt_connect(self, client, userdata, flags, return_code):
        """MQTT connect callback, executed in the MQTT client's context."""
        logger.info(
            "MQTT Connection state: %s for %s",
            connack_string(return_code),
            self._device.get_ip_address(),
        )
        # listen only to command topics we can process
        topics = self._transform.get_subscribe_topics()
        client.subscribe(topics)

    def _set_availability(self, availability: bool):

        if availability == self._availability:
            return

        self._availability = availability
        logger.debug("->publish %s/availability", self._device.get_ip_address())

        pub_content = self._transform.get_publish_availability(availability)
        for item in pub_content:
            # print(item["topic"], item["payload"])
            self._mqtt_client.publish(
                item["topic"], item["payload"], retain=True,
            )

    def on_tuya_connected(self, connected: bool):
        """Tuya connection state updated."""
        self._set_availability(connected)
        # We're in TuyaClient's context, queue a call to tuyaclient.status
        self.command_queue.put((self.request_status, ("mqtt",)))

    def on_tuya_status(self, data: dict, status_from: str):
        """Tuya status message callback."""
        via = "tuya"
        if status_from == "command":
            via = "mqtt"
        # load values in device transformer
        self._device.set_device_payload(data, via=via)
        # get the internal state
        device_state = self._device.get_device_state()
        # set state to output transformer
        self._transform.set_device_state(device_state)

        # get the sanitized state and set it to output transformer
        self._transform.set_gateway_payload(self._device.get_gateway_payload())
        for item in self._transform.get_publish_content():
            # get_output_payload():
            print(item["topic"], item["payload"])
            self._mqtt_client.publish(item["topic"], item["payload"])

    def request_status(self, via: str = "tuya"):
        """Poll Tuya device for status."""
        try:
            data = self._tuya_client.status()
            if not data:
                return
            self._device.set_device_payload(data, via=via)
            device_state = self._device.get_device_state()
            self._transform.set_device_state(device_state)

            self._transform.set_gateway_payload(self._device.get_gateway_payload())
            for item in self._transform.get_output_payload():
                self._mqtt_client.publish(item["topic"], item["payload"])
        except Exception:
            logger.exception("(%s) status request error", self._device.get_ip_address())

    def _log_request_error(self, request_type: str):
        logger.error(
            "(%s) %s request failed",
            self._device.get_ip_address(),
            request_type,
            exc_info=True,
        )

    def set_state(self, dps_item: int, payload):
        """Set state of Tuya device."""
        try:
            result = self._tuya_client.set_state(payload, dps_item)
            if not result:
                self._log_request_error("set_state")
        except Exception:
            self._log_request_error("set_state")

    def set_status(self, device_payload: dict):
        """Set status of Tuya device."""
        try:
            # print(device_payload)
            result = self._tuya_client.set_status(device_payload)
            if not result:
                self._log_request_error("set_status")
        except Exception:
            self._log_request_error("set_status")

    def run(self):
        """Tuya MQTTEntity main loop."""

        time_start = time.time()
        while not self.stop.is_set():
            # wait for transform to become valid
            if not self._transform.is_valid():
                time.sleep(self.delay)
                if time_start + self.transform_delay < time.time():
                    logger.error(
                        "No transformer config for %s, within %f seconds",
                        self._device.get_ip_address(),
                        self.transform_delay,
                    )
                    return
                continue
            break

        self.mqtt_connect()
        self._tuya_client = TuyaClient(
            self._device.get_tuyaface_config(),
            self.on_tuya_status,
            self.on_tuya_connected,
        )
        self._tuya_client.start()

        while not self.stop.is_set():

            while not self.command_queue.empty():
                command, args = self.command_queue.get()
                command(*args)

            time.sleep(self.delay)

    def stop_entity(self):
        """Shut down MQTT client, TuyaClient and worker thread."""
        logger.info("Stopping DeviceThread %s", self.name)
        self._tuya_client.stop_client()
        self._mqtt_client.loop_stop()
        self.stop.set()
        self.join()
