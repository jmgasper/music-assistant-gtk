"""UI event handlers for MusicApp."""

import logging

from gi.repository import GLib, Gtk

from music_assistant_models.enums import PlaybackState


def on_track_action_clicked(app, button: Gtk.Button, menu_button, action: str) -> None:
    track = getattr(button, "track_item", None)
    track_name = getattr(track, "title", "Track")
    logging.getLogger(__name__).info(
        "Track action '%s' for %s", action, track_name
    )
    if menu_button:
        menu_button.popdown()
    if action == "Play":
        if track:
            app.start_playback_from_track(track)
        return
    if action == "Remove from this playlist":
        if track:
            from ui import playlist_operations

            playlist_operations.remove_track_from_playlist(app, track)
        return
    if action == "Add to existing playlist":
        from ui import playlist_manager

        playlist_manager.show_add_to_playlist_dialog(app, track)


def on_track_selection_changed(app, selection, _position: int, _n_items: int) -> None:
    if app.suppress_track_selection:
        return
    item = selection.get_selected_item()
    if item is None:
        return
    app.start_playback_from_track(item)


def clear_track_selection(app, selection=None) -> None:
    selection = selection or app.album_tracks_selection
    if not selection:
        return
    previous = app.suppress_track_selection
    app.suppress_track_selection = True
    try:
        invalid_pos = getattr(Gtk, "INVALID_LIST_POSITION", GLib.MAXUINT)
        selection.set_selected(invalid_pos)
    finally:
        app.suppress_track_selection = previous


def on_play_pause_clicked(app, _button) -> None:
    if not app.playback_track_info:
        return
    if app.playback_state == PlaybackState.PLAYING:
        app.set_playback_state(PlaybackState.PAUSED)
        app.send_playback_command("pause")
    else:
        app.set_playback_state(PlaybackState.PLAYING)
        app.send_playback_command("resume")


def on_previous_clicked(app, _button) -> None:
    app.handle_previous_action()


def on_next_clicked(app, _button) -> None:
    app.handle_next_action()


def on_volume_changed(app, scale: Gtk.Scale) -> None:
    if app.suppress_volume_changes:
        return
    volume = int(round(scale.get_value()))
    app.pending_volume_value = volume
    if app.volume_update_id is None:
        app.volume_update_id = GLib.timeout_add(150, app._apply_volume_change)


def _apply_volume_change(app) -> bool:
    app.volume_update_id = None
    volume = app.pending_volume_value
    app.pending_volume_value = None
    if volume is None:
        return False
    app.set_output_volume(volume)
    return False


def on_volume_drag_begin(
    app, _gesture, _n_press: int, _x: float, _y: float
) -> None:
    app.volume_dragging = True


def on_volume_drag_end(
    app, _gesture, _n_press: int, _x: float, _y: float
) -> None:
    app.volume_dragging = False
