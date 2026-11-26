"""Contract tests for the parts of gurux-dlms the add-on relies on.

gurux-dlms has repeatedly changed behaviour in patch releases (#98, #105) and
1.0.194 to 1.0.197 do not even import on Python 3.15 (#128). These
tests pin down every gurux interface and behaviour the readers depend on, so
a gurux upgrade or a new Python version in the base image is caught in CI
instead of on a user's meter.

The telegrams are built without gurux (``tests/fixtures/bgld_sample_frame``),
so gurux is checked against an independent reference.
"""

from __future__ import annotations

import pytest
from gurux_common import GXCommon
from gurux_dlms import (
    GXByteBuffer,
    GXDLMSException,
    GXDLMSTranslator,
    GXDLMSTranslatorMessage,
    GXReplyData,
)
from gurux_dlms.enums import InterfaceType, Security, TranslatorOutputType
from gurux_dlms.secure import GXDLMSSecureClient

from smartmeter_austria.bgld.data import MeterData
from smartmeter_austria.dlms.read import (
    convert_to_xml,
    parse_dlms_data,
    parse_pyhiscal_dlms_data,
    parse_xml,
)
from smartmeter_austria.serial import read as serial_read
from smartmeter_austria.serial.read import PARSE_ERRORS, MeterReader
from smartmeter_austria.serial.transport import PortClosedError
from tests.fake_port import EOF, SETTINGS, FakePort, run_until
from tests.fixtures.bgld_sample_frame import (
    EXPECTED_VALUES,
    build_apdu,
    build_sample_telegram,
)

TELEGRAM = build_sample_telegram()
WRONG_KEY = "00" * 16

EXPECTED_DICT = {
    "u1": 236,
    "u2": 235,
    "u3": 237,
    "i1": 5.12,
    "i2": 0.48,
    "i3": 19.99,
    "w_con": 3314,
    "w_prov": 0,
    "total_con": 49244276,
    "total_prov": 1234567,
    "angle1": 17,
    "angle2": 195,
    "angle3": 304,
}


def decode_optical(frame: bytes, key: str = TELEGRAM.key_hex):
    return parse_dlms_data(frame, key).value


def decode_physical(frame: bytes, key: str = TELEGRAM.key_hex) -> list:
    return parse_xml(parse_pyhiscal_dlms_data(frame, key))


DECODERS = [
    pytest.param(decode_optical, id="optical"),
    pytest.param(decode_physical, id="physical"),
]


# --- API surface ----------------------------------------------------------


def test_enums_used_by_the_readers_exist() -> None:
    assert InterfaceType.HDLC is not None
    assert Security.ENCRYPTION is not None
    assert TranslatorOutputType.SIMPLE_XML is not None


def test_secure_client_interface() -> None:
    client = GXDLMSSecureClient()
    client.interfaceType = InterfaceType.HDLC
    client.ciphering.security = Security.ENCRYPTION
    client.ciphering.blockCipherKey = GXCommon.hexToBytes(TELEGRAM.key_hex)
    assert callable(client.getData)
    reply = GXReplyData()
    assert hasattr(reply, "value")
    assert hasattr(reply, "data")


def test_translator_interface() -> None:
    translator = GXDLMSTranslator()
    translator.blockCipherKey = GXByteBuffer(TELEGRAM.key_hex)
    translator.comments = True
    translator.completePdu = True
    message = GXDLMSTranslatorMessage()
    message.message = GXByteBuffer(TELEGRAM.frame)
    message.interfaceType = InterfaceType.HDLC
    assert callable(translator.findNextFrame)
    assert callable(translator.messageToXml)
    assert callable(translator.pduToXml)
    assert callable(translator.dataToXml)


def test_gxdlms_exception_is_an_exception() -> None:
    assert issubclass(GXDLMSException, Exception)


# --- decoding valid telegrams -------------------------------------------------


@pytest.mark.parametrize("decode", DECODERS)
def test_decodes_independently_built_telegram(decode) -> None:
    values = decode(TELEGRAM.frame)

    assert list(values[:-1]) == EXPECTED_VALUES[:-1]
    assert bytes(values[-1]) == EXPECTED_VALUES[-1]
    assert all(isinstance(v, int) for v in values[:-1])


@pytest.mark.parametrize("decode", DECODERS)
def test_meter_data_from_decoded_values(decode) -> None:
    data = MeterData(decode(TELEGRAM.frame))

    assert data.to_dict() == EXPECTED_DICT
    assert data.meter_id == "1LGZ0012345678"


@pytest.mark.parametrize("decode", DECODERS)
@pytest.mark.parametrize(
    "values",
    [
        pytest.param([0] * 13 + [b""], id="zeros"),
        pytest.param(
            [0xFFFF] * 6 + [0xFFFFFFFF] * 4 + [0xFFFF] * 3 + [b"X" * 16],
            id="max",
        ),
    ],
)
def test_value_ranges(decode, values) -> None:
    telegram = build_sample_telegram(values=values, frame_counter=0xFFFFFFFE)

    decoded = decode(telegram.frame)

    assert list(decoded[:-1]) == values[:-1]
    assert bytes(decoded[-1]) == values[-1]


@pytest.mark.parametrize("decode", DECODERS)
def test_leading_noise_is_skipped(decode) -> None:
    """Bytes before the opening flag (e.g. line noise) do not hide a telegram."""
    assert decode(b"\x00\x13\x99" + TELEGRAM.frame)[:3] == [236, 235, 237]


@pytest.mark.parametrize("decode", DECODERS)
def test_first_of_two_concatenated_telegrams_is_decoded(decode) -> None:
    assert decode(TELEGRAM.frame + TELEGRAM.frame)[:3] == [236, 235, 237]


def test_convert_to_xml_contains_values() -> None:
    xml = convert_to_xml(parse_dlms_data(TELEGRAM.frame, TELEGRAM.key_hex))

    assert "Structure" in xml
    assert format(49244276, "X") in xml.upper()


def test_pdu_to_xml_of_plain_apdu() -> None:
    """Used by the Netz NÖ reader on the already decrypted APDU."""
    xml = GXDLMSTranslator().pduToXml(build_apdu().hex())

    assert "DataNotification" in xml
    assert format(49244276, "X") in xml.upper()


def test_pdu_to_xml_rejects_truncated_apdu_with_value_error() -> None:
    """The Netz NÖ reader only survives this because it is a ValueError."""
    with pytest.raises(ValueError):
        GXDLMSTranslator().pduToXml("0f")


# --- broken input -----------------------------------------------------------
# The serial reader relies on gurux either returning "no value" or raising an
# exception (never hanging, never returning wrong numbers) for bad input.


@pytest.mark.parametrize("decode", DECODERS)
@pytest.mark.parametrize(
    "chunk",
    [
        pytest.param(TELEGRAM.frame[:13], id="head"),
        pytest.param(TELEGRAM.frame[13:], id="tail"),
        pytest.param(TELEGRAM.frame[:60], id="first-half"),
        pytest.param(b"~", id="bare-flag"),
        pytest.param(b"", id="empty"),
    ],
)
def test_split_telegram_yields_no_values(decode, chunk) -> None:
    """A telegram cut in two (#128) is silently dropped, both halves."""
    assert not decode(chunk)


def test_wrong_key_optical_raises_value_error() -> None:
    with pytest.raises(ValueError):
        decode_optical(TELEGRAM.frame, WRONG_KEY)


def test_wrong_key_physical_yields_no_values() -> None:
    assert decode_physical(TELEGRAM.frame, WRONG_KEY) == []


@pytest.mark.parametrize("decode", DECODERS)
def test_corrupted_telegram_raises(decode) -> None:
    corrupted = bytearray(TELEGRAM.frame)
    corrupted[40] ^= 0xFF

    with pytest.raises(Exception) as excinfo:  # noqa: B017 - gurux raises bare Exception
        decode(bytes(corrupted))

    assert isinstance(excinfo.value, PARSE_ERRORS)


# --- through the serial reader ----------------------------------------------


async def run_reader(steps: list, interface_type: str) -> list[MeterData]:
    """Feed ``steps`` through the reader built for a real port; end on EOF."""
    received: list[MeterData] = []
    reader = MeterReader(
        key=TELEGRAM.key_hex,
        settings=SETTINGS,
        interface_type=interface_type,
        hdlc_frame_size=len(TELEGRAM.frame),
        callback=received.append,
        open_stream=FakePort([*steps, EOF]),
    )
    task = await run_until(reader.run, lambda: False)
    assert isinstance(task.exception(), PortClosedError)
    return received


@pytest.mark.parametrize("interface_type", ["OPTICAL", "PHYSICAL"])
async def test_reader_survives_garbage_and_keeps_decoding(
    interface_type: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(serial_read, "OPTICAL_IDLE_GAP_SECONDS", 0.02)
    corrupted = bytearray(TELEGRAM.frame)
    corrupted[40] ^= 0xFF
    steps = [
        # one telegram delivered in two USB chunks
        TELEGRAM.frame[:13],
        TELEGRAM.frame[13:],
        0.1,
        bytes(corrupted),
        0.1,
        TELEGRAM.frame,
        0.1,
        TELEGRAM.frame,
        0.1,
    ]

    received = await run_reader(steps, interface_type)

    assert [d.to_dict() for d in received] == [EXPECTED_DICT] * 3
