"""Read Austrian smart meters from their customer interface.

``smartmeter_austria.profile`` is the entry point: ``get_profile(name)``
returns the profile of a grid operator's meter, ``create_reader`` builds an
asyncio reader for it. The package is shared by the Home Assistant
integration ``smartmeter_at`` and the MQTT add-on of the same repository.

Importing this package does not import gurux-dlms; see
``smartmeter_austria.fix_source_encoding`` for why that matters.
"""
