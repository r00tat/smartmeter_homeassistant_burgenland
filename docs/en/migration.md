# Switching from the add-on to the integration

[Deutsche Version](../umstieg.md) · [Back to the README](../../README.en.md)

The integration can take over the add-on's sensors. Dashboards, automations,
scripts, the energy dashboard, history and long-term statistics keep working.

## Steps

1. Stop the add-on and disable *Start on boot*. Leave the MQTT integration
   and the broker running.
2. Wait about a minute, then add the integration, see
   [installation.md](installation.md#integration-marketplace).
3. After the connection check the integration finds the add-on's MQTT device
   and offers *Take over the add-on sensors*. Keep it switched on.

The integration then removes the add-on device and its entities (the MQTT
integration also clears the retained discovery message) and registers its own
sensors under the add-on's entity ids. It keeps names, icons, areas, aliases,
labels, enabled/hidden state and the unit: energy stays in Wh, so templates
and cards show the same numbers as before. You can switch a sensor to kWh in
its settings; the statistics are converted. The add-on's *Raw Data* sensor has
no counterpart and is removed.

## Already added the integration without taking over?

Stop the add-on, wait a minute, open the integration's *Configure*, switch on
*Take over the add-on sensors* and pick the add-on device. The integration
then drops the sensors it had created (their short history stays under the
dropped entity ids) and takes over the add-on's entity ids as described above.

## If it does not work

- *The add-on still reports values*: the add-on is still running or sent a
  value less than a minute ago. Stop it and wait a moment.
- **Do not start the add-on again** afterwards: it would recreate its sensors
  under new entity ids.

## Back to the add-on

Delete the integration entry and start the add-on. It creates its sensors
again with default entity ids; entity ids you had changed have to be set
again.
