"""Regression tests for meter.dlms.read."""

from gurux_dlms import GXByteBuffer, GXDLMSTranslator, GXDLMSTranslatorMessage
from gurux_dlms.enums import InterfaceType

from meter.dlms.read import parse_pyhiscal_dlms_data

# A dummy 128-bit key (hex). The crash happens during frame detection, long
# before any decryption, so the key value is irrelevant here.
DUMMY_KEY = "00112233445566778899AABBCCDDEEFF"

# Buffer whose 2nd byte (0x04 = MBusCommand.SND_NR) makes gurux's
# isWirelessMBusData() return True, while the 1st byte (0x00) is not an
# HDLC/WRAPPER/PLC/wired-MBus start. While scanning a real HDLC stream,
# findNextFrame lands on such misaligned positions. With an unset interface
# type it then enters the wireless M-Bus branch, which calls the removed
# _GXCommon.decryptManufacturer() (gurux-dlms >= 1.0.193) and raises
# AttributeError. See issue #98.
WIRELESS_MBUS_TRIGGER = bytes(
    [0x00, 0x04, 0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70, 0x80, 0x90, 0xA0]
)


def test_parse_physical_does_not_enter_wireless_mbus_branch():
    """parse_pyhiscal_dlms_data must not crash on wireless-M-Bus-looking bytes."""
    # Must not raise AttributeError: '_GXCommon' has no 'decryptManufacturer'.
    result = parse_pyhiscal_dlms_data(WIRELESS_MBUS_TRIGGER, DUMMY_KEY)
    assert isinstance(result, str)


def test_unpinned_interface_type_still_reproduces_the_crash():
    """Guards the assumption behind the fix.

    Leaving interfaceType unset (the pre-fix behaviour) still triggers the gurux
    wireless-M-Bus code path. If a future gurux release fixes the bug this test
    will start failing, signalling that the workaround in
    parse_pyhiscal_dlms_data can be revisited.
    """

    tr = GXDLMSTranslator()
    tr.comments = True
    tr.completePdu = True
    msg = GXDLMSTranslatorMessage()
    msg.message = GXByteBuffer(WIRELESS_MBUS_TRIGGER)
    pdu = GXByteBuffer()

    crashed = False
    try:
        while tr.findNextFrame(msg, pdu):
            pdu.clear()
            tr.messageToXml(msg)
    except AttributeError as exc:
        crashed = "decryptManufacturer" in str(exc)

    # Forcing HDLC avoids exactly this branch.
    msg2 = GXDLMSTranslatorMessage()
    msg2.message = GXByteBuffer(WIRELESS_MBUS_TRIGGER)
    msg2.interfaceType = InterfaceType.HDLC
    pdu2 = GXByteBuffer()
    while tr.findNextFrame(msg2, pdu2):
        pdu2.clear()
        tr.messageToXml(msg2)

    assert crashed, (
        "expected the unpinned interfaceType to hit the wireless M-Bus branch; "
        "if gurux-dlms fixed the bug, the workaround can be removed"
    )
