# smartmeter-austria

Python library that reads Austrian smart meters from their customer
interface (optical head or M-Bus/P1 port), decrypts the telegrams and
returns the readings. It contains no Home Assistant or MQTT code.

It is the core of two projects in the same repository,
[r00tat/smartmeter_homeassistant_burgenland](https://github.com/r00tat/smartmeter_homeassistant_burgenland):

- the Home Assistant integration **Smartmeter Austria** (`smartmeter_at`, via HACS),
- the Home Assistant add-on / standalone container that publishes the
  readings via MQTT.

## Supported meters

| Profile | Grid operator / meter | Interface |
| --- | --- | --- |
| `burgenland` | Netz Burgenland (Landis+Gyr E450) | IR or wired, DLMS/HDLC |
| `noe_evn` | Netz NÖ / EVN (Sagemcom T210-D) | M-Bus |
| `wien` | Wiener Netze | IR, DLMS/HDLC |
| `steiermark` | Energienetze Steiermark (Landis+Gyr) | M-Bus |
| `steiermark_sagemcom` | Energienetze Steiermark (Sagemcom) | DSMR P1 |
| `salzburg` | Salzburg Netz | M-Bus |
| `tirol` | TINETZ | M-Bus |
| `h1` | Smart Meter 2.0, customer interface H1 | DSMR P1 |

Details per meter: [docs/en/meters.md](https://github.com/r00tat/smartmeter_homeassistant_burgenland/blob/main/docs/en/meters.md).

## Installation

```bash
pip install smartmeter-austria
```

## Usage

```python
import asyncio

from smartmeter_austria.profile import get_profile


def on_reading(data) -> None:
    print(data.meter_id, data.to_dict())


async def main() -> None:
    profile = get_profile("burgenland")
    config = {
        "interface_type": "OPTICAL",
        "dlms": {"port": "/dev/ttyUSB0", "key": "<32 hex characters from your grid operator>"},
    }
    reader = profile.create_reader(config, on_reading)
    await reader.run()  # reads until cancelled


asyncio.run(main())
```

`smartmeter_austria.supervisor.ReaderSupervisor` restarts a failed reader,
throttles the callback and reopens a port that stopped delivering data.

### gurux-dlms on Python 3.15

gurux-dlms 1.0.197 ships a Latin-1 encoded source file that Python 3.15
refuses to import. Run the fix-up once after installing:

```bash
python3 -m smartmeter_austria.fix_source_encoding gurux_dlms gurux_common
```

## Versioning

The library is released together with the integration and the add-on: one
GitHub release publishes all three with the same version number.

## License

GPL-3.0-only
