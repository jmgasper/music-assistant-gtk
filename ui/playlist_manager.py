import threading

from gi.repository import Gtk, GLib

from music_assistant_client.exceptions import (
    CannotConnect,
    InvalidServerVersion,
    MusicAssistantClientException,
)
from music_assistant_models.errors import AuthenticationFailed, AuthenticationRequired
from music_assistant import library
from ui.sidebar import make_sidebar_row
from ui import ui_utils


def refresh_playlists(app) -> None:
    if not app.playlists_list:
        return
    if app.playlists_loading:
        app.playlists_refresh_pending = True
        return
    if not app.server_url:
        app.playlists_refresh_pending = False
        if app.playlists_add_button:
            app.playlists_add_button.set_sensitive(False)
        populate_playlists_list(app, [])
        set_playlists_status(
            app,
            "Connect to your Music Assistant server to load playlists.",
        )
        return

    if app.playlists_add_button:
        app.playlists_add_button.set_sensitive(True)
    app.playlists_loading = True
    set_playlists_status(app, "Loading playlists...")
    thread = threading.Thread(
        target=load_playlists_worker,
        args=(app,),
        daemon=True,
    )
    thread.start()


def load_playlists_worker(app) -> None:
    error = ""
    playlists: list[dict] = []
    try:
        playlists = app.client_session.run(
            app.server_url,
            app.auth_token,
            load_playlists_async,
        )
    except AuthenticationRequired:
        error = "Authentication required. Add an access token in Settings."
    except AuthenticationFailed:
        error = "Authentication failed. Check your access token."
    except CannotConnect as exc:
        error = f"Unable to reach server at {app.server_url}: {exc}"
    except InvalidServerVersion as exc:
        error = str(exc)
    except MusicAssistantClientException as exc:
        error = str(exc)
    except Exception as exc:
        error = str(exc)
    GLib.idle_add(on_playlists_loaded, app, playlists, error)


async def load_playlists_async(client) -> list[dict]:
    return await library.fetch_playlists(client)


def on_playlists_loaded(app, playlists: list[dict], error: str) -> None:
    app.playlists_loading = False
    pending_refresh = app.playlists_refresh_pending
    app.playlists_refresh_pending = False
    if error:
        set_playlists_status(
            app,
            f"Unable to load playlists: {error}",
            is_error=True,
        )
        return
    populate_playlists_list(app, playlists)
    if not playlists:
        set_playlists_status(app, "No playlists yet. Click + to create one.")
    else:
        set_playlists_status(app, "")
    if pending_refresh:
        refresh_playlists(app)


def set_playlists_status(app, message: str, is_error: bool = False) -> None:
    if not app.playlists_status_label:
        return
    if is_error:
        app.playlists_status_label.add_css_class("error")
    else:
        app.playlists_status_label.remove_css_class("error")
    app.playlists_status_label.set_label(message)
    app.playlists_status_label.set_visible(bool(message))


def populate_playlists_list(app, playlists: list) -> None:
    if not app.playlists_list:
        return
    ui_utils.clear_container(app.playlists_list)
    playlists = playlists or []
    app.playlists = playlists
    for playlist in playlists:
        if isinstance(playlist, dict):
            name = playlist.get("name") or "Untitled Playlist"
        else:
            name = getattr(playlist, "name", None) or str(playlist)
        row = make_sidebar_row(name)
        row.playlist_data = playlist
        app.playlists_list.append(row)


def on_playlist_selected(
    app,
    _listbox: Gtk.ListBox,
    row: Gtk.ListBoxRow | None,
) -> None:
    if not row or not app.main_stack:
        return
    playlist = getattr(row, "playlist_data", None)
    if not playlist:
        return
    app.show_playlist_detail(playlist)
    app.main_stack.set_visible_child_name("playlist-detail")
    if app.home_nav_list:
        app.home_nav_list.unselect_all()
    if app.library_list:
        app.library_list.unselect_all()


def on_playlist_add_clicked(app, _button: Gtk.Button) -> None:
    if not app.server_url:
        set_playlists_status(
            app,
            "Connect to your Music Assistant server to create playlists.",
            is_error=True,
        )
        return
    show_create_playlist_dialog(app)


def show_create_playlist_dialog(app) -> None:
    if not app.window:
        return
    dialog = Gtk.Window(application=app, transient_for=app.window, modal=True)
    dialog.set_title("New Playlist")
    dialog.set_default_size(360, -1)
    dialog.set_resizable(False)

    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    content.set_margin_top(16)
    content.set_margin_bottom(16)
    content.set_margin_start(16)
    content.set_margin_end(16)

    name_label = Gtk.Label(label="Playlist name", xalign=0)
    name_entry = Gtk.Entry()
    name_entry.set_placeholder_text("New playlist")
    name_entry.set_hexpand(True)

    actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    actions.set_halign(Gtk.Align.END)
    cancel_button = Gtk.Button(label="Cancel")
    create_button = Gtk.Button(label="Create")
    create_button.add_css_class("suggested-action")
    create_button.set_sensitive(False)
    actions.append(cancel_button)
    actions.append(create_button)

    content.append(name_label)
    content.append(name_entry)
    content.append(actions)
    dialog.set_child(content)

    def update_create_state(*_args: object) -> None:
        create_button.set_sensitive(bool(name_entry.get_text().strip()))

    def close_dialog(*_args: object) -> None:
        dialog.close()

    def submit_dialog(*_args: object) -> None:
        name = name_entry.get_text().strip()
        if not name:
            return
        dialog.close()
        create_playlist(app, name)

    name_entry.connect("changed", update_create_state)
    name_entry.connect("activate", submit_dialog)
    cancel_button.connect("clicked", close_dialog)
    create_button.connect("clicked", submit_dialog)

    update_create_state()
    dialog.present()
    name_entry.grab_focus()


def create_playlist(app, name: str) -> None:
    cleaned = name.strip()
    if not cleaned:
        return
    if not app.server_url:
        set_playlists_status(
            app,
            "Connect to your Music Assistant server to create playlists.",
            is_error=True,
        )
        return
    set_playlists_status(app, "Creating playlist...")
    thread = threading.Thread(
        target=create_playlist_worker,
        args=(app, cleaned),
        daemon=True,
    )
    thread.start()


def create_playlist_worker(app, name: str) -> None:
    error = ""
    playlist = None
    try:
        playlist = app.client_session.run(
            app.server_url,
            app.auth_token,
            library.create_playlist,
            name,
        )
    except AuthenticationRequired:
        error = "Authentication required. Add an access token in Settings."
    except AuthenticationFailed:
        error = "Authentication failed. Check your access token."
    except CannotConnect as exc:
        error = f"Unable to reach server at {app.server_url}: {exc}"
    except InvalidServerVersion as exc:
        error = str(exc)
    except MusicAssistantClientException as exc:
        error = str(exc)
    except Exception as exc:
        error = str(exc)
    GLib.idle_add(on_playlist_created, app, playlist, error)


def on_playlist_created(app, _playlist: object, error: str) -> None:
    if error:
        set_playlists_status(
            app,
            f"Unable to create playlist: {error}",
            is_error=True,
        )
        return
    refresh_playlists(app)


def show_add_to_playlist_dialog(app, track) -> None:
    if not app.window:
        return
    if not app.server_url:
        set_playlists_status(
            app,
            "Connect to your Music Assistant server to edit playlists.",
            is_error=True,
        )
        return
    if not track:
        return
    track_uri = _get_track_uri(track)
    if not track_uri:
        set_playlists_status(
            app,
            "Unable to add track: missing track URI.",
            is_error=True,
        )
        return
    playlists = [
        playlist
        for playlist in (app.playlists or [])
        if _is_editable_playlist(playlist)
    ]
    if not playlists:
        set_playlists_status(
            app,
            "No editable playlists available. Create one first.",
            is_error=True,
        )
        return

    dialog = Gtk.Window(application=app, transient_for=app.window, modal=True)
    dialog.set_title("Add to Playlist")
    dialog.set_default_size(360, -1)
    dialog.set_resizable(False)

    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    content.set_margin_top(16)
    content.set_margin_bottom(16)
    content.set_margin_start(16)
    content.set_margin_end(16)

    playlist_label = Gtk.Label(label="Select playlist", xalign=0)
    names = [_get_playlist_name(item) for item in playlists]
    playlist_list = Gtk.StringList.new(names)
    playlist_picker = Gtk.DropDown.new(playlist_list, None)
    playlist_picker.set_hexpand(True)

    actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    actions.set_halign(Gtk.Align.END)
    cancel_button = Gtk.Button(label="Cancel")
    add_button = Gtk.Button(label="Add")
    add_button.add_css_class("suggested-action")
    actions.append(cancel_button)
    actions.append(add_button)

    content.append(playlist_label)
    content.append(playlist_picker)
    content.append(actions)
    dialog.set_child(content)

    def close_dialog(*_args: object) -> None:
        dialog.close()

    def submit_dialog(*_args: object) -> None:
        index = playlist_picker.get_selected()
        if index < 0 or index >= len(playlists):
            return
        dialog.close()
        add_track_to_playlist(app, track, playlists[index])

    cancel_button.connect("clicked", close_dialog)
    add_button.connect("clicked", submit_dialog)

    dialog.present()


def add_track_to_playlist(app, track, playlist: dict) -> None:
    if not app.server_url:
        set_playlists_status(
            app,
            "Connect to your Music Assistant server to edit playlists.",
            is_error=True,
        )
        return
    track_uri = _get_track_uri(track)
    if not track_uri:
        set_playlists_status(
            app,
            "Unable to add track: missing track URI.",
            is_error=True,
        )
        return
    playlist_id = _get_playlist_id(playlist)
    if not playlist_id:
        set_playlists_status(
            app,
            "Unable to add track: missing playlist ID.",
            is_error=True,
        )
        return
    playlist_name = _get_playlist_name(playlist)
    set_playlists_status(app, f"Adding to {playlist_name}...")
    thread = threading.Thread(
        target=add_track_to_playlist_worker,
        args=(app, playlist_id, playlist_name, track_uri),
        daemon=True,
    )
    thread.start()


def add_track_to_playlist_worker(
    app,
    playlist_id: str | int,
    playlist_name: str,
    track_uri: str,
) -> None:
    error = ""
    try:
        app.client_session.run(
            app.server_url,
            app.auth_token,
            _add_track_to_playlist_async,
            playlist_id,
            track_uri,
        )
    except AuthenticationRequired:
        error = "Authentication required. Add an access token in Settings."
    except AuthenticationFailed:
        error = "Authentication failed. Check your access token."
    except CannotConnect as exc:
        error = f"Unable to reach server at {app.server_url}: {exc}"
    except InvalidServerVersion as exc:
        error = str(exc)
    except MusicAssistantClientException as exc:
        error = str(exc)
    except Exception as exc:
        error = str(exc)
    GLib.idle_add(
        on_track_added_to_playlist,
        app,
        playlist_id,
        playlist_name,
        error,
    )


async def _add_track_to_playlist_async(
    client, playlist_id: str | int, track_uri: str
) -> None:
    await client.music.add_playlist_tracks(playlist_id, [track_uri])


def on_track_added_to_playlist(
    app, playlist_id: str | int, playlist_name: str, error: str
) -> None:
    if error:
        set_playlists_status(
            app,
            f"Unable to add track: {error}",
            is_error=True,
        )
        return
    set_playlists_status(app, f"Added to {playlist_name}.")
    current = app.current_playlist
    if current and _playlist_id_matches(current, playlist_id):
        app.load_playlist_tracks(current)


def _get_track_uri(track) -> str | None:
    source = getattr(track, "source", None)
    return getattr(source, "uri", None) if source else None


def _get_playlist_name(playlist: object) -> str:
    if isinstance(playlist, dict):
        return playlist.get("name") or "Untitled Playlist"
    return getattr(playlist, "name", None) or "Untitled Playlist"


def _get_playlist_id(playlist: object) -> str | int | None:
    if isinstance(playlist, dict):
        return playlist.get("item_id") or playlist.get("id")
    return getattr(playlist, "item_id", None)


def _playlist_id_matches(playlist: object, playlist_id: str | int) -> bool:
    current_id = _get_playlist_id(playlist)
    if current_id is None:
        return False
    return str(current_id) == str(playlist_id)


def _is_editable_playlist(playlist: object) -> bool:
    if isinstance(playlist, dict):
        return bool(playlist.get("is_editable", False))
    return bool(getattr(playlist, "is_editable", False))
