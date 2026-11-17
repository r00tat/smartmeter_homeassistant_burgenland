"""OBIS-code dictionary and XML parser for the Sagemcom T210-D (Netz NÖ / EVN).

The meter publishes an encrypted DLMS APDU. After decryption, the APDU is
translated to XML via ``gurux_dlms.GXDLMSTranslator`` and the resulting XML
contains alternating ``OctetString`` (OBIS code) and integer value elements.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

OBIS_TO_FIELD: dict[str, str] = {
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

_INT_TAG_PREFIXES = ("UInt", "Int")


def parse_obis_xml(xml: str) -> dict[str, int]:
    """Return ``{field_name: int_value}`` for known OBIS codes in ``xml``.

    Unknown OBIS codes are silently ignored. The XML is assumed to list
    each OBIS OctetString immediately followed by its value element.
    """
    soup = BeautifulSoup(xml, "xml")
    elements = list(soup.find_all(True))

    result: dict[str, int] = {}
    for i, element in enumerate(elements):
        if element.name != "OctetString":
            continue
        code = element.get("Value")
        if code is None or code not in OBIS_TO_FIELD:
            continue
        if i + 1 >= len(elements):
            continue
        next_el = elements[i + 1]
        if not any(next_el.name.startswith(p) for p in _INT_TAG_PREFIXES):
            continue
        raw = next_el.get("Value")
        if raw is None:
            continue
        result[OBIS_TO_FIELD[code]] = int(str(raw), 16)
    return result
