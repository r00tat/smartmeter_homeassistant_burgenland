"""End-to-end pipeline test: M-Bus frame → decrypt → XML → MeterData."""

from gurux_dlms import GXDLMSTranslator

from meter.noe.data import MeterData
from meter.noe.decrypt import aes_gcm_decrypt
from meter.noe.mbus import MBusFrame
from meter.noe.obis import parse_obis_xml
from tests.fixtures.noe_sample_frame import build_sample_frame


def test_full_pipeline_reproduces_plaintext_values() -> None:
    sample = build_sample_frame()

    parsed = MBusFrame.parse(sample.frame_hex)
    assert parsed.system_title == sample.system_title
    assert parsed.frame_counter == sample.frame_counter

    plaintext_apdu = aes_gcm_decrypt(
        parsed.ciphertext,
        sample.key,
        parsed.system_title + parsed.frame_counter,
    )
    assert plaintext_apdu == sample.apdu_plaintext

    xml = GXDLMSTranslator().pduToXml(plaintext_apdu.hex())
    obis_values = parse_obis_xml(xml)
    assert obis_values == sample.obis_values

    meter_data = MeterData(obis_values)
    d = meter_data.to_dict()
    assert d["u1"] == 230.1
    assert d["i1"] == 5.0
    assert d["power_factor"] == 0.98
    assert d["w_con"] == 1500
    assert d["total_con"] == 12345678
