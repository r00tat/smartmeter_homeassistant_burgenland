import logging
from gurux_dlms import (
    GXByteBuffer,
    GXReplyData,
    GXDLMSTranslator,
    TranslatorOutputType,
    GXDLMSTranslatorMessage,
)
from gurux_dlms.enums import InterfaceType, Security
from gurux_common import GXCommon
from gurux_dlms.secure import GXDLMSSecureClient
from bs4 import BeautifulSoup

log = logging.getLogger("meter.dlms.read")


def parse_dlms_data(data: bytes, key: str):
    """Parse DLMS data."""
    bb = GXByteBuffer(data)
    cl = GXDLMSSecureClient()
    data = GXReplyData()
    notify = GXReplyData()
    # cl.interfaceType = InterfaceType.PDU
    cl.interfaceType = InterfaceType.HDLC
    cl.ciphering.security = Security.ENCRYPTION
    # key as hex str
    cl.ciphering.blockCipherKey = GXCommon.hexToBytes(key)
    # plaintext = cl.getData(bb, data, notify)
    cl.getData(bb, data, notify)
    # notify.value is an instance of type GXStructure, which is a list
    # log.info("notify.value: %s", notify.value)
    # notify.data are the decryted hex values of the body
    # log.info("notify data: %s", notify.data)
    # log.info("plain: %s", plaintext)

    # or plaintext?
    return notify


def parse_pyhiscal_dlms_data(data: bytes, key: str):
    """Parse DLMS data from an phyisical interface."""
    tr = GXDLMSTranslator()
    tr.blockCipherKey = GXByteBuffer(key)
    tr.comments = True
    msg = GXDLMSTranslatorMessage()
    msg.message = GXByteBuffer(data)
    xml = ""
    pdu = GXByteBuffer()
    tr.completePdu = True
    while tr.findNextFrame(msg, pdu):
        pdu.clear()
        xml += tr.messageToXml(msg)
    return xml


def convert_to_xml(notify: GXReplyData):
    """Convert parsed data to xml."""
    t = GXDLMSTranslator(TranslatorOutputType.SIMPLE_XML)
    xml = t.dataToXml(notify.data)
    # log.info("xml: %s", xml)
    return xml


def parse_xml(xml: str):
    """Parsing xml response"""
    soup = BeautifulSoup(xml, "xml")
    struct = soup.find("Structure")

    all_values = []

    log.debug("struct: %s", struct)
    for child in struct.findChildren():
        parsed_value = None
        if child.name.startswith("UInt"):
            parsed_value = int(child["Value"], 16)

        if child.name.startswith("OctetString"):
            parsed_value = str(bytearray.fromhex(child["Value"]), encoding="utf-8")

        if parsed_value is not None:
            all_values.append(parsed_value)

    log.debug("all values: %s", all_values)
    return all_values
