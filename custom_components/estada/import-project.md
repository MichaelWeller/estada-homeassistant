# import-project

Dieses Dokument beschreibt das Kommando `import-project` fuer die aktuelle Home-Assistant-Exportschnittstelle aus Estada.

## Zweck

- Dem Kommando wird die komplette Projekt-Struktur von Estada fuer Home Assistant als JSON uebergeben.
- Momentan senden wir die gesamte Struktur in einer MQTT-Nachricht. Wir unterstellen, dass die Groesse dabei kein Problem darstellt.
- Das Root-Objekt entspricht dem Interface `HA_Project`.

## Response / Errorhandling

- Waehrend des Imports verwalten wir eine Response-Struktur, in die wir zunaechst nur etwaige Fehler eintragen.
- Die Fehler-Response-Struktur ist ein JSON-Array.
- Wenn das gesamte JSON ungueltig ist, geben wir einen Fehler im Response zurueck.
- Wenn eine referenzierte Gruppenadress-id nicht existiert, ignorieren wir den Eintrag und schreiben ihn in die Error-Response.
- Umgang mit Duplikaten, z. B. zwei Gruppenadressen mit gleicher Adresse: ignorieren und Fehler in den Response schreiben.

## JSON-Struktur

```text
{
  groupAddresses: [
    {
      id: string;
      address: string; // z. B. 1
      name: string;
      groupAddresses?: [
        {
          id: string;
          address: string; // z. B. /1/2
          name: string;
          groupAddresses?: [
            {
              id: string;
              address: string; // z. B. /1/2/17
              name: string;
            },
            ...
          ]
        },
        ...
      ]
    },
    ...
  ],

  floors: [
    {
      id: string,
      name: string,
      tag: string,
      rooms: [
        {
          id: string,
          name: string,
          tag: string,
          functions: [
            {
              id: string,
              name: string,
              tag: string,
              type: "light_switch" | "light_dimmer" | "cover_jalousie" | "climate_heating" | "binary_sensor_window_contact",
              datapoints: {
                switch?: {
                  command: string,
                  state?: string
                },
                dimmer?: {
                  switch_command: string,
                  switch_state?: string,
                  brightness_command?: string,
                  brightness_state?: string,
                  dim_relative_command?: string
                },
                cover?: {
                  up_down_command: string,
                  stop_step_command?: string,
                  position_command?: string,
                  position_state?: string,
                  tilt_command?: string,
                  tilt_state?: string
                },
                climate?: {
                  target_temperature_command: string,
                  target_temperature_state?: string,
                  current_temperature_state?: string,
                  hvac_mode_command?: string,
                  hvac_mode_state?: string,
                  on_off_command?: string,
                  on_off_state?: string
                },
                window_contact?: {
                  contact_state: string,
                  tamper_state?: string,
                  battery_low_state?: string
                }
              }
            },
            ...
          ]
        },
        ...
      ]
    },
    ...
  ]
}
```

## Strukturregeln

- `groupAddresses` ist rekursiv aufgebaut; dieselbe Struktur wird auf allen Ebenen wiederverwendet.
- Eine `function` beschreibt direkt genau eine Home-Assistant-Entitaet ueber `type` und `datapoints`.
- Wrapper wie `knxEntities`, `entities`, `entity_id` oder `attributes` sind im aktuellen Schema nicht enthalten.

## Beispiel-Mapping pro Typ

- Leuchte (ein/aus):
  - `type = "light_switch"`
  - `datapoints.switch.command` -> Gruppenadresse fuer `turn_on`/`turn_off`
  - `datapoints.switch.state` -> optionale Status-Gruppenadresse

- Dimmer:
  - `type = "light_dimmer"`
  - Schalten: `datapoints.dimmer.switch_command`
  - Helligkeit setzen: `datapoints.dimmer.brightness_command`
  - Helligkeit Rueckmeldung: `datapoints.dimmer.brightness_state`
  - Optional relatives Dimmen: `datapoints.dimmer.dim_relative_command`

- Jalousie:
  - `type = "cover_jalousie"`
  - Auf/Ab: `datapoints.cover.up_down_command`
  - Stop: `datapoints.cover.stop_step_command`
  - Position setzen: `datapoints.cover.position_command`
  - Position Rueckmeldung: `datapoints.cover.position_state`
  - Optional Lamellenwinkel: `datapoints.cover.tilt_command` / `datapoints.cover.tilt_state`

- Heizen:
  - `type = "climate_heating"`
  - Solltemperatur setzen: `datapoints.climate.target_temperature_command`
  - Solltemperatur Rueckmeldung: `datapoints.climate.target_temperature_state`
  - Isttemperatur: `datapoints.climate.current_temperature_state`
  - Optional Modus: `datapoints.climate.hvac_mode_command` / `datapoints.climate.hvac_mode_state`
  - Optional Ein/Aus: `datapoints.climate.on_off_command` / `datapoints.climate.on_off_state`

- Fensterkontakt:
  - `type = "binary_sensor_window_contact"`
  - Kontaktzustand: `datapoints.window_contact.contact_state`
  - Optional Sabotage: `datapoints.window_contact.tamper_state`
  - Optional Batterie schwach: `datapoints.window_contact.battery_low_state`

## Regeln fuer die Zuordnung

- Jede Referenz ist die `id` eines Eintrags aus dem rekursiven `groupAddresses`-Baum.
- `*_command` wird fuer Service-Aufrufe verwendet, z. B. `light.turn_on` oder `cover.set_cover_position`.
- `*_state` wird fuer Rueckmeldungen und Status verwendet.
- Nicht benoetigte optionale Felder koennen weggelassen werden.

## Implementierung

- Die Implementierung erfolgt im File `import_from_estada.py` im Ordner `/import`.
- Die Implementierung sollte sinnvoll auf mehrere Dateien aufgeteilt werden.

## Updates von Estada

- Es sollen Updates von Estada durchgefuehrt werden koennen, also wiederholte Importe.
- Dabei sollen Aenderungen in HA moeglichst unangetastet bleiben.
- Daher speichern wir die komplette JSON-Struktur als `last-import.json` in einem `estada-ha store`.
- Diese Struktur wird vor dem Speichern mit den HA-IDs der einzelnen erzeugten HA-Objekte ergaenzt.
- So speichern wir persistent die Zuordnung `estada-id ↔ ha-id`.
- Bei einem erneuten Import pruefen wir anhand der estada-ids, ob ein Objekt entfallen ist.
- Bei bestehenden Verbindungen pruefen wir, ob wir `name`, `type` oder Gruppenadressen-Zuordnungen (`datapoints`) anpassen muessen.
- Schema-Aenderungen ignorieren wir bis auf weiteres.
