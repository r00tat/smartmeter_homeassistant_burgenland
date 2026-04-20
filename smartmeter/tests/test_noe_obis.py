"""Unit tests for the Netz NÖ OBIS dictionary and XML parser."""

from meter.noe.obis import OBIS_TO_FIELD, parse_obis_xml


def test_obis_dictionary_covers_all_documented_codes() -> None:
    """The T210-D publishes 11 OBIS codes; each must map to a known field name.

    Reference: greenMikeEU/SmartMeterEVN AusleseSkript.py and the
    Netz NÖ Sagemcom-Drehstromzähler customer-interface PDF.
    """
    expected = {
        "0100010800FF": "energy_consumed",
        "0100020800FF": "energy_provided",
        "0100010700FF": "power_consumed",
        "0100020700FF": "power_provided",
        "0100200700FF": "voltage_l1",
        "0100340700FF": "voltage_l2",
        "0100480700FF": "voltage_l3",
        "01001F0700FF": "current_l1",
        "0100330700FF": "current_l2",
        "0100470700FF": "current_l3",
        "01000D0700FF": "power_factor",
    }
    assert expected == OBIS_TO_FIELD


def test_parse_obis_xml_returns_only_known_codes() -> None:
    xml = """
    <root>
      <OctetString Value="0100200700FF"/>
      <UInt32 Value="00000900"/>
      <OctetString Value="0100FFFFFFFF"/>
      <UInt32 Value="00000001"/>
      <OctetString Value="01001F0700FF"/>
      <UInt32 Value="000001F4"/>
    </root>
    """
    result = parse_obis_xml(xml)
    assert result == {
        "voltage_l1": 0x00000900,  # 2304
        "current_l1": 0x000001F4,  # 500
    }


def test_parse_obis_xml_handles_uint_variants() -> None:
    xml = """
    <root>
      <OctetString Value="0100010800FF"/>
      <UInt64 Value="0000000000002710"/>
      <OctetString Value="01000D0700FF"/>
      <UInt16 Value="03E8"/>
    </root>
    """
    result = parse_obis_xml(xml)
    assert result == {
        "energy_consumed": 10000,
        "power_factor": 1000,
    }


def test_parse_obis_xml_empty_input_returns_empty_dict() -> None:
    assert parse_obis_xml("<root/>") == {}
