"""Common base for the decoded readings of every meter profile."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any


class BaseMeterData(ABC):
    """One decoded telegram, ready to be published.

    Every profile maps its meter's telegram onto a subclass. The MQTT side
    only relies on ``to_json`` (the state payload the sensor templates read)
    and ``meter_id`` (the serial number shown in Home Assistant, if the
    meter sends one).
    """

    meter_id: str | None = None

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Return the values keyed by the names the sensor templates use."""

    def to_json(self) -> str:
        return json.dumps(self.to_dict())
