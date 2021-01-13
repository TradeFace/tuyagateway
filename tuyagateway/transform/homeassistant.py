"""Transformer for Home assistant."""
import json


def _subscribe_topic(item: dict) -> tuple:
    return (item["full"], 0)


def _get_topic_value(output_topic, data):
    value = list(
        filter(lambda item: item["tuya_value"] == data, output_topic["values"])
    )
    if len(value) == 0:
        return None
    return value[0]["default_value"]


class TransformDataPoint:
    """Transform DataPoint."""

    def __init__(self, device_key: str, data_point: dict):
        """Initialize TransformDataPoint."""
        self._is_valid = False
        self._device_key = device_key
        self._dp_key = data_point["key"]
        self._command_value = None
        self._state_data = None
        self._attribute_data = {}
        self.data_point = data_point
        self.component_config = None
        self.homeassistant_config = None

    def set_homeassistant_config(self, config):
        """Set the Home Assistant datapoint config."""
        self.homeassistant_config = config
        self.is_valid()

    def get_component_name(self) -> str:
        """Return the data point component name."""
        if not self.data_point:
            return "not_initialized"
        return self.data_point["device_component"]

    def set_component_config(self, config):
        """Set the Home Assistant variable model for datapoint."""
        self.component_config = config
        self.is_valid()

    def is_valid(self) -> bool:
        """Check if all configurations are valid and sane."""
        # TODO: check sane/valid homeassistant_config
        if self.homeassistant_config is None:
            return self._is_valid
        # TODO: check sane/valid component_config
        if self.component_config is None:
            return self._is_valid
        # TODO: check is_valid device
        self._is_valid = True
        return self._is_valid

    def set_data(self, data: bytes):
        """Set value for command."""
        self._command_value = data.decode("utf-8")

    def set_output_data(self, data):
        """Set device return value."""
        self._state_data = data

    def set_attribute_data(self, data):
        """Set device attribute value."""
        self._attribute_data = data

    def get_gateway_payload(self):
        """Get payload in gateway format."""
        if not self.is_valid():
            return

        command_topic_list = list(
            filter(
                lambda item: "publish_topic" in item
                and item["publish_topic"] == self.data_point["device_topic"],
                self.component_config["topics"],
            )
        )
        if len(command_topic_list) == 0:
            return

        gw_value_list = list(
            filter(
                lambda item: item["default_value"] == self._command_value,
                command_topic_list[0]["values"],
            )
        )

        if len(gw_value_list) == 0:
            return
        return gw_value_list[0]["tuya_value"]

    def _full_topic(self, item: dict):

        full = item.replace("~", self.homeassistant_config["~"])
        return {
            "full": full,
            # "key": self._device_key,
            "dp_key": self._dp_key,
            "topic": item.replace("~", ""),
        }

    def _get_topics_by_type(self, topic_type: str) -> list:

        return list(
            filter(
                lambda item: item["topic_type"] == topic_type,
                self.component_config["topics"],
            )
        )

    def _get_topic_by_type_and_name(self, topic_type: str, name: str) -> dict:

        filtered = list(
            filter(
                lambda item: item["topic_type"] == topic_type and item["name"] == name,
                self.component_config["topics"],
            )
        )
        return filtered[0]

    def get_subscribe_topics(self) -> dict:
        """Get the topics to subscribe to for the datapoint."""
        if not self.is_valid():
            return

        output_topic_list = self._get_topics_by_type("subscribe")
        for output_topic in output_topic_list:
            if output_topic["abbreviation"] not in self.homeassistant_config:
                continue
            item = self.homeassistant_config[output_topic["abbreviation"]]
            yield _subscribe_topic(self._full_topic(item))

    def get_publish_availability(self, data: bool):
        """Get the availability topic and ha payload."""
        if not self.is_valid():
            return

        output_topic_dict = self._get_topic_by_type_and_name(
            "publish", "availability_topic"
        )
        if not output_topic_dict:
            return
        if output_topic_dict["abbreviation"] not in self.homeassistant_config:
            return

        return {
            "topic": self.homeassistant_config[output_topic_dict["abbreviation"]],
            "payload": _get_topic_value(output_topic_dict, data),
        }

    def _get_fallback_topic(self, topic):

        map_dict = {"state_topic": "command_topic"}
        find_topic = map_dict[topic]

        output_topic_list = self._get_topics_by_type("subscribe")
        for output_topic in output_topic_list:
            if find_topic == output_topic["name"]:
                return output_topic

    def get_publish_content(self):
        """Get the topic and ha payload."""
        if not self.is_valid():
            return

        output_topic_list = self._get_topics_by_type("publish")
        for output_topic in output_topic_list:

            if output_topic["abbreviation"] not in self.homeassistant_config:
                continue
            if self.data_point["device_topic"] == output_topic["name"]:

                topic = self._full_topic(output_topic["default_value"])["full"]
                payload = _get_topic_value(output_topic, self._state_data)
                if payload is None and self.data_point["device_topic"] == "state_topic":
                    fallback_topic = self._get_fallback_topic(
                        self.data_point["device_topic"]
                    )
                    payload = _get_topic_value(fallback_topic, self._state_data)
                if payload is None:
                    payload = self._state_data
                self._command_value = payload

                yield {"topic": topic, "payload": payload}
            elif output_topic["name"] == "json_attributes_topic":
                topic = self._full_topic(output_topic["default_value"])["full"]
                payload = json.dumps(self._attribute_data)
                yield {"topic": topic, "payload": payload}


class Transform:
    """Transform Home Assistant I/O data."""

    def __init__(self, device_config: dict):
        """Initialize transform."""
        self._device_config = device_config
        self._data_points = {}
        self._is_valid = False
        self._component_config = None
        self._homeassistant_config = None
        self._raw_gateway_payload = None
        self._raw_device_state = None

        for dp_value in self._device_config["dps"]:
            self._data_points[dp_value["key"]] = TransformDataPoint(
                self._device_config["deviceid"], dp_value
            )
        # self._is_valid = False

    def set_homeassistant_config(self, idx, ha_dict):
        """Pass the HA config to datapoint."""
        if idx in self._data_points:
            self._data_points[idx].set_homeassistant_config(ha_dict)

    def set_component_config(self, payload_dict: dict, component_name: str):
        """Pass the HA component config to datapoint."""
        for _, data_point in self._data_points.items():
            if data_point and component_name == data_point.get_component_name():
                data_point.set_component_config(payload_dict)

    def is_valid(self) -> bool:
        """Return true if the configuration validated."""
        for _, data_point in self._data_points.items():
            if not data_point.is_valid():
                return False
        self._is_valid = True
        return self._is_valid

    def data_point(self, idx: int) -> TransformDataPoint:
        """Return TransformDataPoint."""
        if idx in self._data_points:
            return self._data_points[idx]

    def get_subscribe_topics(self):
        """Return subscribe topics for all datapoints."""
        topics = []
        for _, data_point in self._data_points.items():
            for topic in data_point.get_subscribe_topics():
                topics.append(topic)
        return topics

    def get_publish_availability(self, data: bool):
        """Get availability content for all datapoints."""
        # TODO: rewrite once GC is fixed
        avail = {}
        topic = None
        for _, data_point in self._data_points.items():
            if not data_point.is_valid():
                continue

            avail_dp = data_point.get_publish_availability(data)
            avail[avail_dp["topic"]] = avail_dp
            topic = avail_dp["topic"]
        if topic:
            yield avail[avail_dp["topic"]]

    def get_publish_content(self):
        """Get publish content for all datapoints."""
        for _, data_point in self._data_points.items():
            yield from data_point.get_publish_content()
        # TODO: rewrite once GC is fixed
        yield {
            "topic": f"tuya/{self._device_config['deviceid']}/attributes",
            "payload": json.dumps(self._raw_gateway_payload),
        }

    def set_input_payload(self, topic_parts: list, message):
        """Set the incomming data to the data points.

        message: can be str value or dict of str value
        """

        # we don't really know the topic structure
        # assume GC ha config was used to gen the message

        if isinstance(message, dict):
            # TODO: use map
            for idx, item in message:
                self._data_points[int(idx)].set_data(item)
            return

        if isinstance(message, bytes) and topic_parts[len(topic_parts) - 2].isnumeric():
            idx = int(topic_parts[len(topic_parts) - 2])
            self._data_points[idx].set_data(message)

    def get_gateway_payload(self) -> dict:
        """Get the data gateway format."""
        dict_values = {}
        for idx, data_point in self._data_points.items():
            dict_values[idx] = data_point.get_gateway_payload()
        return dict_values

    def set_gateway_payload(self, gw_payload: dict):
        """Set the data gateway format."""
        self._raw_gateway_payload = gw_payload
        for idx, gw_dp_payload in gw_payload.items():
            if idx in self._data_points:
                self._data_points[idx].set_output_data(gw_dp_payload)

    def set_device_state(self, device_state: dict):
        """Set the device state."""
        self._raw_device_state = device_state
        for idx, dp_device_state in device_state.items():
            if idx in self._data_points:
                self._data_points[idx].set_attribute_data(dp_device_state)

    def get_output_payload(self) -> dict:
        """Get publish content for all datapoints."""
        for _, data_point in self._data_points.items():
            yield from data_point.get_publish_content()
