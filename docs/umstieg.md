# Umstieg vom Add-on auf die Integration

[English version](en/migration.md) · [Zurück zum README](../README.md)

Die Integration kann die Sensoren des Add-ons übernehmen. Dashboards,
Automationen, Skripte, das Energie-Dashboard, der Verlauf und die
Langzeitstatistik laufen danach unverändert weiter.

## Ablauf

1. Das Add-on stoppen und *Beim Booten starten* ausschalten. Die
   MQTT-Integration und den Broker laufen lassen.
2. Etwa eine Minute warten, dann die Integration hinzufügen, siehe
   [installation.md](installation.md#integration-marketplace).
3. Nach der Verbindungsprüfung findet die Integration das MQTT-Gerät des
   Add-ons und bietet *Sensoren des Add-ons übernehmen* an. Eingeschaltet
   lassen.

Die Integration entfernt dann das Add-on-Gerät und dessen Entitäten (die
MQTT-Integration löscht auch die gespeicherte Discovery-Nachricht) und legt
ihre eigenen Sensoren unter den Entitäts-IDs des Add-ons an. Erhalten bleiben
Namen, Icons, Bereiche, Aliase, Labels, aktiviert/versteckt und die Einheit:
Energie bleibt in Wh, Templates und Karten zeigen also dieselben Zahlen wie
vorher. In den Einstellungen eines Sensors kannst du auf kWh umstellen; die
Statistik wird umgerechnet. Der Sensor *Raw Data* des Add-ons hat kein
Gegenstück und wird entfernt.

## Integration schon ohne Übernahme eingerichtet?

Add-on stoppen, eine Minute warten, bei der Integration *Konfigurieren*
öffnen, *Sensoren des Add-ons übernehmen* einschalten und das Add-on-Gerät
wählen. Die Integration entfernt dann ihre eigenen Sensoren (deren kurzer
Verlauf bleibt unter den entfernten Entitäts-IDs) und übernimmt die
Entitäts-IDs des Add-ons wie oben beschrieben.

## Wenn es nicht klappt

- *Das Add-on liefert noch Werte*: Das Add-on läuft noch oder hat vor weniger
  als einer Minute gesendet. Add-on stoppen und kurz warten.
- Das Add-on danach **nicht wieder starten**: Es würde seine Sensoren unter
  neuen Entitäts-IDs neu anlegen.

## Zurück zum Add-on

Den Eintrag der Integration löschen und das Add-on starten. Es legt seine
Sensoren mit den Standard-Entitäts-IDs neu an; geänderte Entitäts-IDs musst
du wieder setzen.
