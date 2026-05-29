"""Storage layer for Estada project imports and entity mappings."""

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Storage file name for the last import
LAST_IMPORT_FILENAME = "last-import.json"

# Storage file name for entity mappings (estada-id -> ha-id)
MAPPINGS_FILENAME = "estada-mappings.json"


class EstadaImportStore:
    """Manages persistence of Estada project imports and HA entity mappings."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        data_dir: str | Path,
    ) -> None:
        """Initialize the store."""
        self._hass = hass
        self._entry_id = entry_id
        self._data_dir = Path(data_dir)

        # Try to create directory, but don't fail if it can't
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError) as err:
            _LOGGER.warning(
                "Could not create data directory %s: %s", self._data_dir, err
            )

        self._last_import_path = self._data_dir / LAST_IMPORT_FILENAME
        self._mappings_path = self._data_dir / MAPPINGS_FILENAME

    async def load_last_import(self) -> dict[str, Any] | None:
        """Load the last successful import JSON structure."""
        try:
            content = await self._hass.async_add_executor_job(
                self._load_json_file, self._last_import_path
            )
            return content
        except FileNotFoundError:
            return None
        except Exception as err:
            _LOGGER.warning("Failed to load last import: %s", err)
            return None

    async def save_last_import(self, import_json: dict[str, Any]) -> None:
        """Save the import JSON structure."""
        try:
            await self._hass.async_add_executor_job(
                self._save_json_file, self._last_import_path, import_json
            )
        except Exception as err:
            _LOGGER.error("Failed to save last import: %s", err)
            raise

    async def load_mappings(self) -> dict[str, str]:
        """Load estada-id -> ha-id mappings."""
        try:
            content = await self._hass.async_add_executor_job(
                self._load_json_file, self._mappings_path
            )
            if isinstance(content, dict):
                return content
            return {}
        except FileNotFoundError:
            return {}
        except Exception as err:
            _LOGGER.warning("Failed to load mappings: %s", err)
            return {}

    async def save_mappings(self, mappings: dict[str, str]) -> None:
        """Save estada-id -> ha-id mappings."""
        try:
            await self._hass.async_add_executor_job(
                self._save_json_file, self._mappings_path, mappings
            )
        except Exception as err:
            _LOGGER.error("Failed to save mappings: %s", err)
            raise

    @staticmethod
    def _load_json_file(path: Path) -> dict[str, Any]:
        """Synchronously load JSON file."""
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _save_json_file(path: Path, data: dict[str, Any]) -> None:
        """Synchronously save JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
