"""Meter profiles: one place for every decision about a meter's interface.

A profile describes how the customer interface of one grid operator's
meter works and how to turn it into Home Assistant sensors:

- the serial line defaults (baudrate, byte size, parity, stop bits),
- how often the meter pushes a telegram,
- which reader (framing + decryption) handles the line,
- how a decoded telegram maps to a ``MeterData`` object,
- the Home Assistant device metadata and sensor catalog.

The rest of the program (config validation, reader construction, MQTT
publishing) asks the selected profile instead of branching on the
``meter_type`` name. Adding a meter therefore means adding a profile here
plus its data class and sensor catalog — nothing else has to change.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import serial

from .bgld.data import MeterData as BgldMeterData
from .bgld.sensors import SENSOR_SPECS as BGLD_SENSORS
from .meter_data import BaseMeterData
from .mqtt.sensor_spec import SensorSpec
from .noe.read import NoeMeterReader
from .noe.sensors import SENSOR_SPECS as NOE_SENSORS
from .obis.framing import TelegramFramer
from .obis.reader import ObisMeterReader
from .obis.sensors import (
    E450_STEIERMARK_FIELDS,
    H1_FIELDS,
    KAIFA_FIELDS,
    build_sensor_specs,
)
from .serial.read import MeterReader as HdlcMeterReader
from .serial.transport import SerialSettings
from .wien.data import MeterData as WienMeterData
from .wien.sensors import SENSOR_SPECS as WIEN_SENSORS

DEFAULT_METER_TYPE = "burgenland"

_PARITY_NAME_TO_LETTER = {v.upper(): k for k, v in serial.PARITY_NAMES.items()}


class MeterReaderLike(Protocol):
    """A reader reads until it is cancelled and raises on any fault.

    Readers never retry on their own: ``meter.supervisor`` opens a new one.
    """

    async def run(self) -> None: ...


MeterDataCallback = Callable[[Any], None]


def _parity_letter(value: str) -> str:
    if value in serial.PARITY_NAMES:
        return value
    return _PARITY_NAME_TO_LETTER.get(str(value).upper(), serial.PARITY_NONE)


def _override(dlms: dict, key: str, default: Any) -> Any:
    """Return ``dlms[key]`` unless it is unset (missing, ``None`` or ``""``)."""
    value = dlms.get(key)
    if value is None or value == "":
        return default
    return value


@dataclass(frozen=True)
class MeterProfile(ABC):
    """Base class of all meter profiles.

    Subclasses pick the reader in ``create_reader``; everything else is
    data on the instance, so a new meter that reuses an existing interface
    is just another instance with different values.
    """

    name: str
    manufacturer: str
    model: str
    sensor_specs: tuple[SensorSpec, ...]
    default_baudrate: int
    default_parity: str = serial.PARITY_NONE
    default_bytesize: int = serial.EIGHTBITS
    default_stopbits: int = serial.STOPBITS_ONE
    # Seconds between two telegrams pushed by the meter. Used to turn the
    # user's ``publish_interval`` (seconds) into "publish every n-th reading".
    push_interval_seconds: float = 5.0

    def serial_settings(self, config: dict) -> SerialSettings:
        """Merge the profile's serial defaults with ``config["dlms"]``."""
        dlms = config.get("dlms") or {}
        return SerialSettings(
            port=_override(dlms, "port", "/dev/ttyUSB0"),
            baudrate=int(_override(dlms, "baudrate", self.default_baudrate)),
            bytesize=int(_override(dlms, "bytesize", self.default_bytesize)),
            parity=_parity_letter(_override(dlms, "parity", self.default_parity)),
            stopbits=int(_override(dlms, "stopbits", self.default_stopbits)),
        )

    def readings_per_publish(self, publish_interval_seconds: float) -> int:
        """Number of received telegrams per MQTT publish (at least 1)."""
        return max(1, math.ceil(publish_interval_seconds / self.push_interval_seconds))

    @property
    def stale_after_seconds(self) -> float:
        """Silence after which the readings count as unavailable.

        Six missed telegrams, but at least a minute, so a single garbled
        telegram or a short hiccup does not flap the sensors.
        """
        return max(60.0, 6 * self.push_interval_seconds)

    @abstractmethod
    def create_reader(
        self, config: dict, callback: MeterDataCallback
    ) -> MeterReaderLike:
        """Return a reader for this meter's customer interface."""


@dataclass(frozen=True)
class HdlcDlmsProfile(MeterProfile):
    """DLMS/COSEM data notifications in HDLC frames (IR or wired P1 port).

    gurux handles framing and decryption; ``data_factory`` maps the decoded
    notification (a list of values) onto the profile's ``MeterData``.
    """

    data_factory: Callable[[list[Any]], BaseMeterData] = BgldMeterData

    def create_reader(
        self, config: dict, callback: MeterDataCallback
    ) -> HdlcMeterReader:
        dlms = config.get("dlms") or {}
        return HdlcMeterReader(
            key=dlms.get("key") or "",
            settings=self.serial_settings(config),
            interface_type=config.get("interface_type") or "OPTICAL",
            hdlc_frame_size=int(dlms.get("hdlc_frame_size") or 120),
            callback=callback,
            data_factory=self.data_factory,
        )


@dataclass(frozen=True)
class MBusDlmsProfile(MeterProfile):
    """Encrypted DLMS APDUs in wired M-Bus long frames (Sagemcom T210-D)."""

    def create_reader(
        self, config: dict, callback: MeterDataCallback
    ) -> NoeMeterReader:
        dlms = config.get("dlms") or {}
        return NoeMeterReader(
            key_hex=dlms.get("key") or "",
            settings=self.serial_settings(config),
            callback=callback,
        )


@dataclass(frozen=True)
class ObisProfile(MeterProfile):
    """Encrypted OBIS telegrams decoded by the generic ``meter.obis`` pipeline.

    The flags pick the transports the framer looks for; the payload is
    always a (ciphered) DLMS data-notification or a DSMR telegram whose
    values are named by OBIS code.
    """

    mbus: bool = False
    hdlc: bool = False
    p1: bool = False

    def framer(self) -> TelegramFramer:
        return TelegramFramer(mbus=self.mbus, hdlc=self.hdlc, p1=self.p1)

    def create_reader(
        self, config: dict, callback: MeterDataCallback
    ) -> ObisMeterReader:
        dlms = config.get("dlms") or {}
        return ObisMeterReader(
            key_hex=dlms.get("key") or "",
            framer_factory=self.framer,
            settings=self.serial_settings(config),
            callback=callback,
        )


_PROFILES: dict[str, MeterProfile] = {
    profile.name: profile
    for profile in (
        HdlcDlmsProfile(
            name="burgenland",
            manufacturer="Landis+Gyr",
            model="E450",
            sensor_specs=BGLD_SENSORS,
            default_baudrate=9600,
            push_interval_seconds=5.0,
            data_factory=BgldMeterData,
        ),
        MBusDlmsProfile(
            name="noe_evn",
            manufacturer="Sagemcom",
            model="T210-D",
            sensor_specs=NOE_SENSORS,
            default_baudrate=2400,
            default_parity=serial.PARITY_EVEN,
            push_interval_seconds=5.0,
        ),
        HdlcDlmsProfile(
            name="wien",
            # Wiener Netze installs meters from several vendors (Siemens,
            # Iskraemeco, Landis+Gyr); they all share one notification layout.
            manufacturer="Wiener Netze",
            model="IM350 / AM550 / E450",
            sensor_specs=WIEN_SENSORS,
            default_baudrate=9600,
            push_interval_seconds=1.0,
            data_factory=WienMeterData,
        ),
        # The profiles below follow the operators' published specifications
        # but have not been verified with a real telegram yet (see README).
        ObisProfile(
            name="steiermark",
            manufacturer="Landis+Gyr",
            model="E450 (Energienetze Steiermark)",
            sensor_specs=build_sensor_specs(E450_STEIERMARK_FIELDS),
            default_baudrate=2400,
            default_parity=serial.PARITY_EVEN,
            push_interval_seconds=10.0,
            # Wired M-Bus; community reports show HDLC frames on the wire.
            hdlc=True,
            mbus=True,
        ),
        ObisProfile(
            name="steiermark_sagemcom",
            manufacturer="Sagemcom",
            model="DSMR P1 (Energienetze Steiermark)",
            sensor_specs=build_sensor_specs(E450_STEIERMARK_FIELDS),
            default_baudrate=115200,
            push_interval_seconds=10.0,
            p1=True,
            hdlc=True,
        ),
        ObisProfile(
            name="salzburg",
            manufacturer="Kaifa / Honeywell",
            model="MA309M (Salzburg Netz)",
            sensor_specs=build_sensor_specs(KAIFA_FIELDS),
            default_baudrate=2400,
            default_parity=serial.PARITY_EVEN,
            push_interval_seconds=5.0,
            mbus=True,
        ),
        ObisProfile(
            name="tirol",
            manufacturer="Kaifa / Honeywell",
            model="MA110M / MA309M (TINETZ)",
            sensor_specs=build_sensor_specs(KAIFA_FIELDS),
            default_baudrate=2400,
            default_parity=serial.PARITY_EVEN,
            push_interval_seconds=5.0,
            mbus=True,
        ),
        ObisProfile(
            name="h1",
            manufacturer="Smart Meter 2.0",
            model="H1 customer interface (DSMR P1)",
            sensor_specs=build_sensor_specs(H1_FIELDS),
            default_baudrate=115200,
            push_interval_seconds=1.0,
            p1=True,
            hdlc=True,
        ),
    )
}


def known_meter_types() -> list[str]:
    """Names accepted for ``meter_type``, in registration order."""
    return list(_PROFILES)


def get_profile(meter_type: str) -> MeterProfile:
    """Return the ``MeterProfile`` for ``meter_type`` or raise."""
    try:
        return _PROFILES[meter_type]
    except KeyError as exc:
        raise ValueError(
            f"unknown meter_type {meter_type!r}; "
            f"known: {sorted(_PROFILES)}"
        ) from exc
