# Funktionsumfang (verfeinert)

1. **Konfiguration**
   - Die Estada-Integration fragt als Konfiguration eine `client_id` ab (über `config_flow`, UI-basiert).
   - Die Konfiguration erfolgt ausschließlich über die Benutzeroberfläche (keine YAML-Konfiguration).

2. **MQTT-Verbindung**
   - Mit der konfigurierten `client_id` (`id1`) verbindet sich die Integration mit dem Estada-MQTT-Server.
   - Das Top-Level-Topic lautet `estada/(id1)/#`.
   - Die Verbindung nutzt nach Möglichkeit die Standard-MQTT-Integration von Home Assistant.

3. **State-Export**
   - Die Integration publiziert State-Änderungen aller Entities nach MQTT unter `estada/(id1)/entities/(entity_id)`.
   - Das JSON-Format orientiert sich an der Home-Assistant-MQTT-Schnittstelle, z. B.:
     ```json
     {
       "state": "on",
       "attributes": {
         "friendly_name": "Licht Wohnzimmer"
       },
       "last_changed": "2026-05-15T12:00:00+00:00",
       "source_tag": "HA"
     }
     ```
   - Es werden sowohl `state` als auch `attributes` übertragen.
   - Optional kann konfiguriert werden, welche Entities exportiert werden (Standard: alle).
   - Leitplanken für den Export (auch bei Standard „alle“):
     - Exporte können per Allowlist (`entity_id` oder Domain) eingeschränkt werden.
     - Exporte können zusätzlich per Exclude-Liste mit Wildcards eingeschränkt werden (`entity_exclude_patterns`).
     - Standardmäßig sind Estada-eigene Status-Entities vom Export ausgeschlossen (Loop-Schutz).
     - Für den Export wird standardmäßig `qos=0` verwendet.
     - `retain` ist standardmäßig `false`.
     - Es werden nur tatsächliche Zustandsänderungen publiziert; unveränderte Updates werden unterdrückt.
     - Zur Vermeidung von Loops bei bidirektionaler Verwendung enthält jede Message optional ein `source_tag`.
     - Home Assistant setzt `source_tag="HA"` bei ausgehenden Nachrichten und ignoriert eingehende Nachrichten mit `source_tag="HA"`.

4. **MQTT-Listener**
   - Die Integration setzt einen Listener auf `estada/(id1)/#`.

   - **Entity-State-Import** über `estada/(id1)/entities/(entity_id)`:
     - Es wird nur `state` verarbeitet; `attributes` werden ignoriert.
     - Es findet **kein direktes Setzen des Home-Assistant-State** statt, sondern ausschließlich Service-Aufrufe.
     - Fehlerhafte oder unzulässige States werden geloggt und ignoriert.
     - Eingehende Nachrichten mit `source_tag="HA"` werden zur Loop-Vermeidung verworfen.

   - **Verfahren zur Identifikation des passenden Home-Assistant-Service**:
     1. `entity_id` aus dem Topic extrahieren und in Home Assistant auflösen. Wenn die Entity nicht existiert: Fehler loggen und an `estada/(id1)/errors` publizieren.

     2. Domain der Entity aus `entity_id` bestimmen (Präfix vor dem Punkt, z. B. `light.kueche` -> `light`).

     3. Prüfen, ob der Payload explizit einen Service vorgibt (`service` oder `action`).
        - Wenn ja: nur verwenden, wenn der Service in der Domain registriert ist.
        - Wenn nein oder ungültig: auf Domain/State-Mapping zurückfallen.

     4. Domain/State-Mapping anwenden (Standardfall):
        - `light`, `switch`, `fan`, `input_boolean`: `on` -> `turn_on`, `off` -> `turn_off`
        - `lock`: `locked` -> `lock`, `unlocked` -> `unlock`
        - `cover`: `open`/`opening` -> `open_cover`, `closed`/`closing` -> `close_cover`, `stop` -> `stop_cover`
        - `media_player`: `on` -> `turn_on`, `off` -> `turn_off`
        - `select`, `input_select`: `select_option` mit `option=<state>`
        - `number`, `input_number`: `set_value` mit `value=<state>` (numerisch)

     5. Service-Daten aufbauen:
        - Immer `entity_id` setzen.
        - Zusätzliche Parameter aus `params` übernehmen, sofern der Zielservice diese unterstützt.

     6. Service-Aufruf ausführen und Ergebnis behandeln:
        - Bei Erfolg optional Bestätigung unter `estada/(id1)/commands/response/state-update` publizieren.
        - Bei Fehlschlag (kein Mapping, Service nicht verfügbar, ungültiger Wert): Fehler loggen und an `estada/(id1)/errors` publizieren.

   - **Command-Handling** über `estada/(id1)/commands/(command_name)`:
     - `command_name` aus dem Topic ist führend; der Payload enthält nur Parameter.
     - Kommandos nutzen folgendes JSON-Format:
       ```json
       {
         "params": {
           "p1": "hallo"
         },
         "commandSequenceId": "abc-123"
       }
       ```
     - Nicht unterstützte Kommandos werden mit einer Fehlermeldung quittiert (MQTT-Response und Log).
     - Die Liste der unterstützten Kommandos ergibt sich aus den registrierten Handlern.
     - Die Liste der Kommandos wird unter `estada/(id1)/commands/list-of-commands` veröffentlicht, z. B.:
       ```json
       {
         "create-knx-entity": {
           "args": {
             "name": {
               "type": "string",
               "required": true
             },
             "commandSequenceId": {
               "type": "string",
               "required": true
             }
           }
         },
         "delete-knx-entity": {
           "args": {
             "name": {
               "type": "string",
               "required": true
             },
             "commandSequenceId": {
               "type": "string",
               "required": true
             }
           }
         },
         "ping": {
           "args": {
             "commandSequenceId": {
               "type": "string",
               "required": true
             }
           }
         }
       }
       ```
     - Für jedes Kommando wird eine eigene Datei unter `./commands` angelegt.
     - Alle Kommandos haben als Pflichtparameter `commandSequenceId`.
     - Startmenge der Kommandos:
       - `create-knx-entity`: erstellt eine KNX-Entity mit HA-typischen Attributen (Pflichtfelder: `name`, `commandSequenceId`).
       - `delete-knx-entity`: löscht eine KNX-Entity anhand von `name`.
       - `ping`: antwortet mit `pong` und aktueller Zeit.
     - Kommandos publizieren Antworten unter `estada/(id1)/commands/response/(command_name)`.

   - **KNX-Telegramm-Monitoring und Export**:
     - Die Integration lauscht zusätzlich auf Home-Assistant-Events vom Typ `knx_event`.
     - Beim Start versucht die Integration primär eine direkte KNX-Telegram-Callback-Anbindung (match-all) zu verwenden, um auch unbekannte Gruppenadressen zu erfassen.
     - Falls die direkte Callback-Anbindung nicht verfügbar ist, registriert die Integration bekannte KNX-Gruppenadressen automatisch über `knx.event_register`.
     - Es werden nur eingehende Telegramme (`direction == "Incoming"`) exportiert.
     - Export-Topic für rohe Gruppenadressenwerte:
       - `estada/(id1)/telegrams/(group_address)`
     - Export-Payload enthält mindestens:
       - `destination` (Gruppenadresse)
       - `source` (physikalische Adresse)
       - `telegramtype`
       - `direction`
       - `data` (roh, z. B. int oder Byte-Array)
       - `value` (dekodiert, falls verfügbar)
       - `timestamp`
       - `source_tag`
     - Filterung mit Wildcards:
       - Include-Liste: `knx_ga_include_patterns` (Standard: `*`)
       - Exclude-Liste: `knx_ga_exclude_patterns` (Standard: leer)
       - Exclude hat Vorrang vor Include.

5. **Fehlerbehandlung und Logging**
   - Fehlerhafte Nachrichten (z. B. ungültiges JSON, unbekannte Entities, nicht unterstützte Kommandos) werden geloggt.
   - Fehler werden zusätzlich als MQTT-Response an ein dediziertes Topic gesendet (`estada/(id1)/errors`).
   - Fehler-Payload ist valides JSON, z. B.:
     ```json
     {
       "error": "unsupported_command",
       "message": "Command 'xyz' is not supported",
       "command": "xyz",
       "timestamp": "2026-05-16T10:15:00+00:00"
     }
     ```

6. **Sonstiges**
   - Die Authentifizierung am Estada-MQTT-Server erfolgt mit `username=id1` und `password=id1`.
   - Da `id1` immer eine GUID (UUID4) ist, wird dies vorerst als ausreichend angesehen.
   - Aktuell gibt es keine besonderen Anforderungen an Latenz oder Zuverlässigkeit.
   - Retained Messages werden derzeit nicht verwendet.

7. **import-project**
   - Es gibt ein spezielles komplexes Kommando `import-project`.
  - Die vollstaendige Spezifikation (JSON-Struktur, Typen, Mappings und Regeln) steht in [import-project.md](./import-project.md).
