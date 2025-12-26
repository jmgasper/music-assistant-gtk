"""Home section refresh and data loading helpers."""

import threading

from gi.repository import GLib

from constants import HOME_LIST_LIMIT
from music_assistant import library
from music_assistant_client import MusicAssistantClient
from music_assistant_models.enums import MediaType
from ui import home_section


def refresh_home_sections(app) -> None:
    app.refresh_home_recently_played()
    app.refresh_home_recently_added()


def clear_home_recent_lists(app) -> None:
    app.home_recently_played_loading = False
    app.home_recently_added_loading = False
    if app.home_recently_played_refresh_id is not None:
        GLib.source_remove(app.home_recently_played_refresh_id)
        app.home_recently_played_refresh_id = None
    home_section.populate_home_album_list(app, app.home_recently_played_list, [])
    home_section.populate_home_album_list(app, app.home_recently_added_list, [])
    home_section.update_home_status(app.home_recently_played_status, [])
    home_section.update_home_status(app.home_recently_added_status, [])


def schedule_home_recently_played_refresh(app, delay_ms: int = 1200) -> None:
    if app.home_recently_played_refresh_id is not None:
        return
    app.home_recently_played_refresh_id = GLib.timeout_add(
        delay_ms, app._handle_home_recently_played_refresh
    )


def _handle_home_recently_played_refresh(app) -> bool:
    app.home_recently_played_refresh_id = None
    app.refresh_home_recently_played()
    return False


def refresh_home_recently_played(app) -> None:
    if not app.server_url:
        home_section.populate_home_album_list(
            app, app.home_recently_played_list, []
        )
        home_section.set_home_status(
            app.home_recently_played_status,
            "Connect to your Music Assistant server to load recently played.",
        )
        return
    if app.home_recently_played_loading:
        return
    app.home_recently_played_loading = True
    home_section.set_home_status(
        app.home_recently_played_status, "Loading recently played..."
    )
    thread = threading.Thread(
        target=app._load_recently_played_worker,
        daemon=True,
    )
    thread.start()


def refresh_home_recently_added(app) -> None:
    if not app.server_url:
        home_section.populate_home_album_list(
            app, app.home_recently_added_list, []
        )
        home_section.set_home_status(
            app.home_recently_added_status,
            "Connect to your Music Assistant server to load recently added albums.",
        )
        return
    if app.home_recently_added_loading:
        return
    app.home_recently_added_loading = True
    home_section.set_home_status(
        app.home_recently_added_status,
        "Loading recently added albums...",
    )
    thread = threading.Thread(
        target=app._load_recently_added_worker,
        daemon=True,
    )
    thread.start()


def _load_recently_played_worker(app) -> None:
    error = ""
    albums: list[dict] = []
    try:
        albums = app.client_session.run(
            app.server_url,
            app.auth_token,
            app._fetch_recently_played_albums_async,
        )
    except Exception as exc:
        error = str(exc)
    GLib.idle_add(app.on_recently_played_loaded, albums, error)


def _load_recently_added_worker(app) -> None:
    error = ""
    albums: list[dict] = []
    try:
        albums = app.client_session.run(
            app.server_url,
            app.auth_token,
            app._fetch_recently_added_albums_async,
        )
    except Exception as exc:
        error = str(exc)
    GLib.idle_add(app.on_recently_added_loaded, albums, error)


def on_recently_played_loaded(app, albums: list[dict], error: str) -> None:
    app.home_recently_played_loading = False
    if error:
        home_section.populate_home_album_list(
            app, app.home_recently_played_list, []
        )
        home_section.set_home_status(
            app.home_recently_played_status,
            f"Unable to load recently played: {error}",
        )
        return
    home_section.populate_home_album_list(
        app, app.home_recently_played_list, albums
    )
    home_section.update_home_status(app.home_recently_played_status, albums)


def on_recently_added_loaded(app, albums: list[dict], error: str) -> None:
    app.home_recently_added_loading = False
    if error:
        home_section.populate_home_album_list(
            app, app.home_recently_added_list, []
        )
        home_section.set_home_status(
            app.home_recently_added_status,
            f"Unable to load recently added albums: {error}",
        )
        return
    home_section.populate_home_album_list(
        app, app.home_recently_added_list, albums
    )
    home_section.update_home_status(app.home_recently_added_status, albums)


async def _fetch_recently_played_albums_async(
    app, client: MusicAssistantClient
) -> list[dict]:
    items = await client.music.recently_played(
        limit=HOME_LIST_LIMIT,
        media_types=[MediaType.ALBUM],
    )
    albums: list[dict] = []
    for item in items:
        item_id = getattr(item, "item_id", None)
        provider = getattr(item, "provider", None)
        if not item_id or not provider:
            continue
        try:
            album = await client.music.get_album(item_id, provider)
        except Exception:
            continue
        albums.append(library._serialize_album(client, album))
        if len(albums) >= HOME_LIST_LIMIT:
            break
    return albums


async def _fetch_recently_added_albums_async(
    app, client: MusicAssistantClient
) -> list[dict]:
    albums = await client.music.get_library_albums(
        limit=HOME_LIST_LIMIT,
        offset=0,
        order_by="timestamp_added_desc",
    )
    return [library._serialize_album(client, album) for album in albums]


def clear_home_album_selection(app) -> None:
    for flow in (app.home_recently_played_list, app.home_recently_added_list):
        if flow is not None:
            flow.unselect_all()
