import logging
from gurux_dlms import GXByteBuffer, GXReplyData, GXDLMSTranslator, TranslatorOutputType
from gurux_dlms.enums import InterfaceType, Security
from gurux_common import GXCommon
from gurux_dlms.secure import GXDLMSSecureClient

log = logging.getLogger("meter.dlms.read")


def parse_dlms_data(data: bytes, key: str):
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


def convert_to_xml(notify: GXReplyData):
    """Convert parsed data to xml
    """
    t = GXDLMSTranslator(TranslatorOutputType.SIMPLE_XML)
    xml = t.dataToXml(notify.data)
    # log.info("xml: %s", xml)
    return xml
