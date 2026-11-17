# Fehlerbehebung

[English version](en/troubleshooting.md) · [Zurück zum README](../README.md)

## Fehlermeldungen beim Einrichten der Integration

| Meldung | Ursache |
| --- | --- |
| *Der serielle Port kann nicht geöffnet werden.* | Der Port existiert nicht, oder ein anderes Programm (oft das Add-on) hält ihn. |
| *Kein gültiges Telegramm empfangen.* | Der Port öffnet, aber es kam kein lesbares Telegramm. Sitzt der Lesekopf auf dem IR-Fenster? Ist die Schnittstelle freigeschaltet? Stimmen Zählertyp und Schlüssel? Ein Schlüssel im richtigen Format, aber mit falschem Wert, landet ebenfalls hier. |
| *Der Schlüssel muss genau 32 Hex-Zeichen lang sein.* | Tippfehler im Schlüssel. |
| *Dieser Port wird bereits von einem anderen Smart-Meter-Eintrag verwendet.* | Pro Port ist nur ein Eintrag möglich. |
| *Unerwarteter Fehler* | Details stehen im Protokoll. |

Beim Melden eines Fehlers hilft die Diagnose-Datei von der Geräteseite; der
Schlüssel ist darin geschwärzt.

## Keine oder veraltete Werte

Integration, Add-on und Container erholen sich selbst, eine
Neustart-Automation ist nicht nötig:

- **Port fällt aus** (z.B. USB-Adapter abgesteckt): Die Sensoren werden
  *nicht verfügbar*, der Port wird alle 10 Sekunden neu geöffnet.
- **Zähler schweigt** (z.B. Lesekopf verrutscht): Nach etwa einer Minute ohne
  Telegramm (sechs verpasste Telegramme, mindestens 60 Sekunden) werden die
  Sensoren *nicht verfügbar*, bis das nächste Telegramm kommt.
- **Port offen, aber keine Daten** (z.B. hängender USB-Adapter): Nach
  5 Minuten Stille wird der Port geschlossen und neu geöffnet.
- **MQTT-Broker weg** (Add-on und Container): Neuer Verbindungsversuch alle
  10 Sekunden; danach wird das Gerät neu angemeldet. Werte aus der Zwischenzeit
  werden gepuffert, pro Topic nur der neueste.
- **Add-on oder Container stürzt ab**: Der MQTT Last Will setzt die Sensoren
  auf *nicht verfügbar*.

Bleiben die Werte trotzdem aus, zeigen die [Debug-Logs](#debug-logs), auf
welcher Ebene es hängt. Für Netz NÖ, Steiermark, Salzburg, Tirol und H1
schreibt der Leser zusätzlich alle 30 Sekunden einen Heartbeat ins Log, der
die wahrscheinliche Ursache nennt: keine Bytes (Verkabelung, Port, Baudrate),
Bytes ohne erkennbares Telegramm (Baudrate, Parität, Zählertyp) oder
Telegramme, die sich nicht entschlüsseln lassen (Schlüssel).

## Debug-Logs

**Integration** – in `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.smartmeter_at: debug
    meter: debug
```

**Add-on und Container** – `logging: DEBUG` in der Konfiguration. Die Logs
zeigen dann die rohen seriellen Bytes und jedes Telegramm als Hex.
