from __future__ import annotations

import hashlib
from typing import Callable

from constants import (
    MEDIA_KEY_NAMES,
    MPRIS_BUS_NAME,
    MPRIS_DESKTOP_ENTRY,
    MPRIS_IDENTITY,
    MPRIS_INTROSPECTION_XML,
    MPRIS_NO_TRACK,
    MPRIS_NOT_SUPPORTED_ERROR,
    MPRIS_OBJECT_PATH,
    MPRIS_TRACK_PATH_PREFIX,
)
import gi
gi.require_version('Gdk', '4.0')
gi.require_version('Gtk', '4.0')
from gi.repository import Gdk, Gio, GLib, Gtk
from music_assistant_models.enums import PlaybackState


class MPRISManager:
    def __init__(
        self,
        callbacks: dict[str, Callable[..., object]],
        state_getters: dict[str, Callable[..., object]],
    ) -> None:
        self.callbacks = callbacks
        self.state_getters = state_getters
        self.bus_id: int | None = None
        self.connection: Gio.DBusConnection | None = None
        self.node_info: Gio.DBusNodeInfo | None = None
        self.registration_ids: list[int] = []
        self.volume = 0.0
        self.shuffle = False
        self.loop_status = "None"
        self.rate = 1.0
        self.media_key_controller: Gtk.EventControllerKey | None = None
        self.media_key_action_map = self.build_media_key_action_map()

    def start(self) -> None:
        if self.bus_id is not None:
            return
        self.node_info = Gio.DBusNodeInfo.new_for_xml(MPRIS_INTROSPECTION_XML)
        self.bus_id = Gio.bus_own_name(
            Gio.BusType.SESSION,
            MPRIS_BUS_NAME,
            Gio.BusNameOwnerFlags.NONE,
            self.on_mpris_bus_acquired,
            self.on_mpris_name_acquired,
            self.on_mpris_name_lost,
        )

    def stop(self) -> None:
        if self.connection and self.registration_ids:
            for registration_id in self.registration_ids:
                self.connection.unregister_object(registration_id)
            self.registration_ids.clear()
        self.connection = None
        bus_id = self.bus_id
        self.bus_id = None
        if bus_id is not None:
            Gio.bus_unown_name(bus_id)
        self.node_info = None

    def on_mpris_bus_acquired(
        self, connection: Gio.DBusConnection, _name: str
    ) -> None:
        self.connection = connection
        if not self.node_info:
            return
        for interface in self.node_info.interfaces:
            if interface.name not in (
                "org.mpris.MediaPlayer2",
                "org.mpris.MediaPlayer2.Player",
            ):
                continue
            registration_id = connection.register_object(
                MPRIS_OBJECT_PATH,
                interface,
                self.on_mpris_method_call,
                self.on_mpris_get_property,
                self.on_mpris_set_property,
            )
            if registration_id:
                self.registration_ids.append(registration_id)
        self.emit_mpris_properties_changed(
            "org.mpris.MediaPlayer2",
            self.build_mpris_root_properties(),
        )
        self.emit_mpris_properties_changed(
            "org.mpris.MediaPlayer2.Player",
            self.build_mpris_player_properties(),
        )

    def on_mpris_name_acquired(
        self, _connection: Gio.DBusConnection, _name: str
    ) -> None:
        return

    def on_mpris_name_lost(self, _connection: Gio.DBusConnection, _name: str) -> None:
        self.stop()

    def on_mpris_method_call(
        self,
        _connection: Gio.DBusConnection,
        _sender: str,
        _object_path: str,
        interface_name: str,
        method_name: str,
        _parameters: GLib.Variant,
        invocation: Gio.DBusMethodInvocation,
    ) -> None:
        if interface_name == "org.mpris.MediaPlayer2":
            handled = self.handle_mpris_root_method(method_name)
        elif interface_name == "org.mpris.MediaPlayer2.Player":
            handled = self.handle_mpris_player_method(method_name)
        else:
            handled = False
        if not handled:
            invocation.return_dbus_error(
                MPRIS_NOT_SUPPORTED_ERROR,
                f"Method not supported: {method_name}",
            )
            return
        invocation.return_value(GLib.Variant("()", ()))

    def handle_mpris_root_method(self, method_name: str) -> bool:
        if method_name == "Raise":
            self.callbacks["on_raise"]()
            return True
        if method_name == "Quit":
            self.callbacks["on_quit"]()
            return True
        return False

    def handle_mpris_player_method(self, method_name: str) -> bool:
        playback_state = self.state_getters["get_playback_state"]()
        track_info = self.state_getters["get_track_info"]()
        if method_name == "PlayPause":
            self.callbacks["on_play_pause"]()
            return True
        if method_name == "Play":
            if track_info and playback_state != PlaybackState.PLAYING:
                self.callbacks["on_play_pause"]()
            return True
        if method_name == "Pause":
            if track_info and playback_state == PlaybackState.PLAYING:
                self.callbacks["on_play_pause"]()
            return True
        if method_name == "Stop":
            if track_info and playback_state == PlaybackState.PLAYING:
                self.callbacks["on_play_pause"]()
            return True
        if method_name == "Next":
            self.callbacks["on_next"]()
            return True
        if method_name == "Previous":
            self.callbacks["on_previous"]()
            return True
        return False

    def on_mpris_get_property(
        self,
        _connection: Gio.DBusConnection,
        _sender: str,
        _object_path: str,
        interface_name: str,
        property_name: str,
    ) -> GLib.Variant | None:
        if interface_name == "org.mpris.MediaPlayer2":
            return self.get_mpris_root_property(property_name)
        if interface_name == "org.mpris.MediaPlayer2.Player":
            return self.get_mpris_player_property(property_name)
        return None

    def on_mpris_set_property(
        self,
        _connection: Gio.DBusConnection,
        _sender: str,
        _object_path: str,
        interface_name: str,
        property_name: str,
        value: GLib.Variant,
    ) -> bool:
        if interface_name != "org.mpris.MediaPlayer2.Player":
            return False
        if property_name == "Volume":
            new_value = float(value.unpack())
            new_value = max(0.0, min(1.0, new_value))
            volume_percent = int(round(new_value * 100))
            self.callbacks["on_set_volume"](volume_percent)
            self.callbacks["on_update_volume_slider"](volume_percent)
            return True
        if property_name == "Shuffle":
            self.shuffle = bool(value.unpack())
            self.emit_mpris_properties_changed(
                "org.mpris.MediaPlayer2.Player",
                {"Shuffle": self.get_mpris_player_property("Shuffle")},
            )
            return True
        if property_name == "LoopStatus":
            loop_status = str(value.unpack())
            if loop_status not in ("None", "Track", "Playlist"):
                loop_status = "None"
            self.loop_status = loop_status
            self.emit_mpris_properties_changed(
                "org.mpris.MediaPlayer2.Player",
                {"LoopStatus": self.get_mpris_player_property("LoopStatus")},
            )
            return True
        if property_name == "Rate":
            self.rate = float(value.unpack())
            self.emit_mpris_properties_changed(
                "org.mpris.MediaPlayer2.Player",
                {"Rate": self.get_mpris_player_property("Rate")},
            )
            return True
        return False

    def build_mpris_root_properties(self) -> dict[str, GLib.Variant]:
        return {
            "CanQuit": self.get_mpris_root_property("CanQuit"),
            "CanRaise": self.get_mpris_root_property("CanRaise"),
            "HasTrackList": self.get_mpris_root_property("HasTrackList"),
            "Identity": self.get_mpris_root_property("Identity"),
            "DesktopEntry": self.get_mpris_root_property("DesktopEntry"),
            "SupportedUriSchemes": self.get_mpris_root_property(
                "SupportedUriSchemes"
            ),
            "SupportedMimeTypes": self.get_mpris_root_property(
                "SupportedMimeTypes"
            ),
        }

    def get_mpris_root_property(self, property_name: str) -> GLib.Variant:
        if property_name == "CanQuit":
            return GLib.Variant("b", True)
        if property_name == "CanRaise":
            return GLib.Variant(
                "b", bool(self.state_getters["get_window"]())
            )
        if property_name == "HasTrackList":
            return GLib.Variant("b", False)
        if property_name == "Identity":
            return GLib.Variant("s", MPRIS_IDENTITY)
        if property_name == "DesktopEntry":
            return GLib.Variant("s", MPRIS_DESKTOP_ENTRY)
        if property_name == "SupportedUriSchemes":
            return GLib.Variant("as", [])
        if property_name == "SupportedMimeTypes":
            return GLib.Variant("as", [])
        return GLib.Variant("s", "")

    def build_mpris_player_properties(self) -> dict[str, GLib.Variant]:
        names = (
            "PlaybackStatus",
            "LoopStatus",
            "Rate",
            "Shuffle",
            "Metadata",
            "Volume",
            "Position",
            "MinimumRate",
            "MaximumRate",
            "CanGoNext",
            "CanGoPrevious",
            "CanPlay",
            "CanPause",
            "CanSeek",
            "CanControl",
        )
        return {name: self.get_mpris_player_property(name) for name in names}

    def get_mpris_player_property(self, property_name: str) -> GLib.Variant:
        track_info = self.state_getters["get_track_info"]()
        if property_name == "PlaybackStatus":
            return GLib.Variant("s", self.get_mpris_playback_status())
        if property_name == "LoopStatus":
            return GLib.Variant("s", self.loop_status)
        if property_name == "Rate":
            return GLib.Variant("d", self.rate)
        if property_name == "Shuffle":
            return GLib.Variant("b", self.shuffle)
        if property_name == "Metadata":
            return GLib.Variant("a{sv}", self.build_mpris_metadata())
        if property_name == "Volume":
            return GLib.Variant("d", self.get_mpris_volume())
        if property_name == "Position":
            return GLib.Variant("x", self.get_mpris_position())
        if property_name == "MinimumRate":
            return GLib.Variant("d", 1.0)
        if property_name == "MaximumRate":
            return GLib.Variant("d", 1.0)
        if property_name == "CanGoNext":
            return GLib.Variant("b", self.can_mpris_go_next())
        if property_name == "CanGoPrevious":
            return GLib.Variant("b", self.can_mpris_go_previous())
        if property_name == "CanPlay":
            return GLib.Variant("b", bool(track_info))
        if property_name == "CanPause":
            return GLib.Variant("b", bool(track_info))
        if property_name == "CanSeek":
            return GLib.Variant("b", False)
        if property_name == "CanControl":
            return GLib.Variant("b", True)
        return GLib.Variant("s", "")

    def get_mpris_playback_status(self) -> str:
        playback_state = self.state_getters["get_playback_state"]()
        if playback_state == PlaybackState.PLAYING:
            return "Playing"
        if playback_state == PlaybackState.PAUSED:
            return "Paused"
        return "Stopped"

    def can_mpris_go_next(self) -> bool:
        track_info = self.state_getters["get_track_info"]()
        track_index = self.state_getters["get_track_index"]()
        album_tracks = self.state_getters["get_album_tracks"]()
        if not track_info or track_index is None:
            return False
        return track_index + 1 < len(album_tracks)

    def can_mpris_go_previous(self) -> bool:
        track_info = self.state_getters["get_track_info"]()
        track_index = self.state_getters["get_track_index"]()
        album_tracks = self.state_getters["get_album_tracks"]()
        if not track_info or track_index is None:
            return False
        if track_index < 1:
            return False
        return 0 <= track_index - 1 < len(album_tracks)

    def get_mpris_volume(self) -> float:
        return float(self.volume)

    def get_mpris_position(self) -> int:
        track_info = self.state_getters["get_track_info"]()
        if not track_info:
            return 0
        elapsed = self.state_getters["get_elapsed"]()
        return int(float(elapsed) * 1_000_000)

    def build_mpris_metadata(self) -> dict[str, GLib.Variant]:
        track_info = self.state_getters["get_track_info"]()
        if not track_info:
            return {"mpris:trackid": GLib.Variant("o", MPRIS_NO_TRACK)}
        metadata: dict[str, GLib.Variant] = {
            "mpris:trackid": GLib.Variant(
                "o", self.build_mpris_track_id(track_info)
            )
        }
        title = track_info.get("title") or ""
        if title:
            metadata["xesam:title"] = GLib.Variant("s", title)
        artist = track_info.get("artist") or ""
        if artist:
            metadata["xesam:artist"] = GLib.Variant("as", [artist])
        album = track_info.get("album") or ""
        if album:
            metadata["xesam:album"] = GLib.Variant("s", album)
        length_seconds = track_info.get("length_seconds")
        if length_seconds:
            metadata["mpris:length"] = GLib.Variant(
                "x", int(length_seconds * 1_000_000)
            )
        track_number = track_info.get("track_number")
        if track_number:
            metadata["xesam:trackNumber"] = GLib.Variant("i", int(track_number))
        source_uri = track_info.get("source_uri")
        if source_uri:
            metadata["xesam:url"] = GLib.Variant("s", source_uri)
        return metadata

    def build_mpris_track_id(self, track_info: dict) -> str:
        identity = track_info.get("identity")
        if identity is None:
            identity = track_info.get("source_uri") or track_info.get("title")
        digest = hashlib.sha1(repr(identity).encode("utf-8")).hexdigest()
        return f"{MPRIS_TRACK_PATH_PREFIX}{digest}"

    def emit_mpris_properties_changed(
        self, interface_name: str, changed: dict[str, GLib.Variant]
    ) -> None:
        if not self.connection:
            return
        payload = GLib.Variant("(sa{sv}as)", (interface_name, changed, []))
        self.connection.emit_signal(
            None,
            MPRIS_OBJECT_PATH,
            "org.freedesktop.DBus.Properties",
            "PropertiesChanged",
            payload,
        )

    def emit_mpris_seeked(self, position_us: int) -> None:
        if not self.connection:
            return
        payload = GLib.Variant("(x)", (position_us,))
        self.connection.emit_signal(
            None,
            MPRIS_OBJECT_PATH,
            "org.mpris.MediaPlayer2.Player",
            "Seeked",
            payload,
        )

    def notify_playback_state_changed(self) -> None:
        self.emit_mpris_properties_changed(
            "org.mpris.MediaPlayer2.Player",
            {
                "PlaybackStatus": self.get_mpris_player_property(
                    "PlaybackStatus"
                ),
                "CanPlay": self.get_mpris_player_property("CanPlay"),
                "CanPause": self.get_mpris_player_property("CanPause"),
                "CanGoNext": self.get_mpris_player_property("CanGoNext"),
                "CanGoPrevious": self.get_mpris_player_property("CanGoPrevious"),
            },
        )

    def notify_track_changed(self) -> None:
        self.emit_mpris_properties_changed(
            "org.mpris.MediaPlayer2.Player",
            {
                "Metadata": self.get_mpris_player_property("Metadata"),
                "PlaybackStatus": self.get_mpris_player_property(
                    "PlaybackStatus"
                ),
                "Position": self.get_mpris_player_property("Position"),
                "CanPlay": self.get_mpris_player_property("CanPlay"),
                "CanPause": self.get_mpris_player_property("CanPause"),
                "CanGoNext": self.get_mpris_player_property("CanGoNext"),
                "CanGoPrevious": self.get_mpris_player_property("CanGoPrevious"),
            },
        )

    def notify_volume_changed(self, volume: float) -> None:
        self.volume = max(0.0, min(1.0, float(volume)))
        self.emit_mpris_properties_changed(
            "org.mpris.MediaPlayer2.Player",
            {"Volume": self.get_mpris_player_property("Volume")},
        )

    def build_media_key_action_map(self) -> dict[int, str]:
        action_map: dict[int, str] = {}
        for action, names in MEDIA_KEY_NAMES.items():
            for name in names:
                keyval = Gdk.keyval_from_name(name)
                if keyval:
                    action_map[keyval] = action
        return action_map

    def ensure_media_key_controller(
        self, window: Gtk.ApplicationWindow | None
    ) -> None:
        if window is None or self.media_key_controller is not None:
            return
        controller = Gtk.EventControllerKey()
        controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        controller.connect("key-pressed", self.on_media_key_pressed)
        window.add_controller(controller)
        self.media_key_controller = controller

    def on_media_key_pressed(
        self,
        _controller: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        _state: Gdk.ModifierType,
    ) -> bool:
        action = self.media_key_action_map.get(keyval)
        if not action:
            return False
        if action == "play_pause":
            self.callbacks["on_play_pause"]()
        elif action == "next":
            self.callbacks["on_next"]()
        elif action == "previous":
            self.callbacks["on_previous"]()
        return True

    def setup_media_keys(self, window: Gtk.ApplicationWindow | None) -> None:
        self.ensure_media_key_controller(window)


__all__ = ["MPRISManager"]
