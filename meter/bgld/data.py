import binascii
from gurux_dlms import GXReplyData

class MeterData():
    """
    Smart meter reply data parsed
    
    Values provided
    - Momentanspannung L1
    - Momentanspannung L2
    - Momentanspannung L3
    - Momentanstrom L1
    - Momentanstrom L2
    - Momentanstrom L3
    - Wirkleistung +P
    - Wirkleistung -P
    - Wirkenergietotal +A
    - Wirkenergietotal -A
    - Zähleridentifikationsnummern des Netzbetreibers
    """
    def __init__(self, dlms_data: GXReplyData):
        self.dlms_data = dlms_data
        
        self.voltage_l1 = 0
        self.voltage_l2 = 0
        self.voltage_l3 = 0
        
        self.current_l1 = 0
        self.current_l2 = 0
        self.current_l3 = 0
        
        self.power_consumed = 0
        self.power_provided = 0
        
        self.total_consumed = 0
        self.total_provided = 0
        
        self.meter_id = None
        
        self.parse()
        
        
    def parse(self):
        """"parse dlms data"""
        if not self.dlms_data:
            return
        
        (
            self.voltage_l1, self.voltage_l2, self.voltage_l3,
            self.current_l1, self.current_l2, self.current_l3,
            self.power_consumed, self.power_provided,
            self.total_consumed, self.total_provided,
            self.meter_id,
            *rest
        ) = self.dlms_data.value

    def __str__(self) -> str:
        return f"MeterData[V({self.voltage_l1},{self.voltage_l2},{self.voltage_l3}),I({self.current_l1},{self.current_l2},{self.current_l3}),P({self.power_consumed},-{self.power_provided}),W({self.total_consumed},-{self.total_provided}),id({self.meter_id})]"
        
        
    