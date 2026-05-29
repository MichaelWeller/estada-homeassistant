# HA Doctor Commands

Dieses Dokument beschreibt die Nutzung von ha_doctor.

## Script

Pfad:
- ./scripts/ha_doctor.sh

## Befehle

1. Stop laufender Home Assistant Instanzen

```bash
./scripts/ha_doctor.sh stop
```

2. Healthcheck ausführen

```bash
./scripts/ha_doctor.sh health
```

3. Erst stoppen, dann Healthcheck

```bash
./scripts/ha_doctor.sh stop-and-health
```

4. Hilfe anzeigen

```bash
./scripts/ha_doctor.sh --help
```

## Optionale Umgebungsvariablen

1. HA_CORE_DIR
- Standard: /workspaces/core

2. HA_CONFIG_DIR
- Standard: /workspaces/core/config

3. HA_PORT
- Standard: 8123

Beispiel mit eigenem Port:

```bash
HA_PORT=8123 ./scripts/ha_doctor.sh health
```

## Typischer Ablauf bei Startproblemen

1. Laufende Instanzen beenden

```bash
./scripts/ha_doctor.sh stop
```

2. Home Assistant starten

```bash
cd /workspaces/core
/home/vscode/.local/ha-venv/bin/python -m homeassistant --debug -c config
```

3. Healthcheck prüfen

```bash
cd /workspaces/core/estada-ha
./scripts/ha_doctor.sh health
```

## Was der Healthcheck prüft

1. Ob ein HA Prozess läuft
2. Ob Port 8123 lauscht (oder HA_PORT)
3. Ob HTTP antwortet
4. Ob die Logdatei vorhanden ist
5. Letzte relevante Fehlerzeilen aus dem Log
6. Letzte Logzeilen als Kurzüberblick
