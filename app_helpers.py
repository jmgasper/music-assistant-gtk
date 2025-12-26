"""Application helper utilities for Music Assistant GTK."""

import json
import logging
import os

from constants import (
    ALBUM_ART_CACHE_DIR,
    FONT_DIR,
    FONT_FILES,
    SAMPLE_ALBUMS,
    SETTINGS_FILE,
)
from music_assistant_models.enums import AlbumType
from ui import ui_utils


def configure_library_logging(app) -> None:
    app.log_albums = bool(os.getenv("MA_LOG_ALBUMS"))
    app.log_artists = bool(os.getenv("MA_LOG_ARTISTS"))
    app.log_albums_path = os.getenv("MA_LOG_ALBUMS_FILE", app.log_albums_path)
    app.log_artists_path = os.getenv("MA_LOG_ARTISTS_FILE", app.log_artists_path)


def get_settings_path(_app=None) -> str:
    return os.path.join(os.path.dirname(__file__), SETTINGS_FILE)


def get_css_path(_app=None) -> str:
    return os.path.join(os.path.dirname(__file__), "ui", "css", "style.css")


def get_cache_dir(_app=None) -> str:
    return os.path.join(os.path.dirname(__file__), ALBUM_ART_CACHE_DIR)


def get_font_paths(_app=None) -> list[str]:
    base_dir = os.path.dirname(__file__)
    return [os.path.join(base_dir, FONT_DIR, font_file) for font_file in FONT_FILES]


def log_gtk_environment(_app=None) -> None:
    logger = logging.getLogger(__name__)
    version, theme_name = ui_utils.get_gtk_environment_info()
    logger.debug("GTK version: %s", version)
    logger.debug("GTK theme: %s", theme_name)


def write_json_log(path: str, payload: list[dict]) -> None:
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(
                payload,
                handle,
                indent=2,
                sort_keys=True,
                ensure_ascii=True,
            )
            handle.write("\n")
    except OSError as exc:
        logging.getLogger(__name__).warning(
            "Failed to write %s: %s",
            path,
            exc,
        )


def build_sample_albums() -> list[dict]:
    return [
        {
            "name": title,
            "artists": [artist],
            "image_url": None,
            "provider_mappings": [],
            "is_sample": True,
            "album_type": AlbumType.ALBUM.value,
        }
        for title, artist in SAMPLE_ALBUMS
    ]


def normalize_album_type(album_type: object) -> str:
    if isinstance(album_type, AlbumType):
        return album_type.value
    if isinstance(album_type, str):
        value = album_type.strip().lower()
        if value:
            return AlbumType(value).value
    return AlbumType.UNKNOWN.value


def pick_album_value(album: object, fields: tuple[str, ...]) -> object | None:
    for field in fields:
        if isinstance(album, dict):
            value = album.get(field)
        else:
            value = getattr(album, field, None)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def get_album_type_value(_app, album: object) -> str:
    if isinstance(album, dict):
        album_type = album.get("album_type") or album.get("type")
    else:
        album_type = getattr(album, "album_type", None)
    return normalize_album_type(album_type)
