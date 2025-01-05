"""Data structure definition for burgenland smartmeter"""

import json


class MeterData:
    """Smart meter reply data parsed

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
    - int16 unkown value?
    - int16 unkown value?
    - int16 unkown value?
    - Zähleridentifikationsnummern des Netzbetreibers
    """

    def __init__(self, dlms_data: list[any]):
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

        self.x_1 = 0
        self.x_2 = 0
        self.x_3 = 0

        self.parse()

    def parse(self):
        """Parse dlms data."""
        if not self.dlms_data:
            return

        (
            self.voltage_l1,
            self.voltage_l2,
            self.voltage_l3,
            self.current_l1,
            self.current_l2,
            self.current_l3,
            self.power_consumed,
            self.power_provided,
            self.total_consumed,
            self.total_provided,
            *rest,
        ) = self.dlms_data

        if len(rest) >= 3:
            (self.x_1, self.x_2, self.x_3, *rest2) = rest
        if len(rest) > 3:
            self.meter_id = str(rest[3], "UTF-8")

    def __str__(self) -> str:
        return (
            f"MeterData["
            f"U({self.voltage_l1}V,{self.voltage_l2}V,{self.voltage_l3}V),"
            f"I({self.current_l1}A,{self.current_l2}A,{self.current_l3}A),"
            f"P({self.power_consumed}W,-{self.power_provided}W),"
            f"W({self.total_consumed}Wh,-{self.total_provided}Wh)"
            # f"?({self.x_1},{self.x_2},{self.x_3})"
            # f"id({self.meter_id})"
            f"]"
        )

    def to_dict(self) -> dict:
        """Return item as dict"""
        return {
            "voltage_l1": self.voltage_l1,
            "voltage_l2": self.voltage_l2,
            "voltage_l3": self.voltage_l3,
            "current_l1": self.current_l1,
            "current_l2": self.current_l2,
            "current_l3": self.current_l3,
            "power_consumed": self.power_consumed,
            "power_provided": self.power_provided,
            "total_consumed": self.total_consumed,
            "total_provided": self.total_provided,
            "meter_id": self.meter_id,
        }

    def to_json(self) -> str:
        """Return item as json"""
        return json.dumps(self.to_dict())
