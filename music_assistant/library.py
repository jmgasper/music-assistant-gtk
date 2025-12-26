from __future__ import annotations

from music_assistant_client import MusicAssistantClient
from music_assistant_models.enums import AlbumType

from constants import DEFAULT_PAGE_SIZE


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


def _serialize_album(client: MusicAssistantClient, album: object) -> dict:
    name = getattr(album, "name", None) or "Unknown Album"
    item_id = getattr(album, "item_id", None)
    provider = getattr(album, "provider", None)
    uri = getattr(album, "uri", None)
    album_type = normalize_album_type(getattr(album, "album_type", None))
    provider_mappings = []
    for mapping in getattr(album, "provider_mappings", []) or []:
        provider_mappings.append(
            {
                "item_id": getattr(mapping, "item_id", None),
                "provider_instance": getattr(mapping, "provider_instance", None),
                "provider_domain": getattr(mapping, "provider_domain", None),
                "available": getattr(mapping, "available", True),
            }
        )
    artists = []
    for artist in getattr(album, "artists", []) or []:
        artist_name = getattr(artist, "name", None) or getattr(
            artist, "sort_name", None
        )
        if artist_name:
            artists.append(artist_name)
    image_url = None
    try:
        image_url = client.get_media_item_image_url(album)
    except Exception:
        image_url = None
    added_at = pick_album_value(
        album,
        (
            "added_at",
            "date_added",
            "timestamp_added",
            "time_added",
            "created_at",
            "created",
            "sort_timestamp",
            "timestamp",
        ),
    )
    last_played = pick_album_value(
        album,
        (
            "last_played",
            "last_played_at",
            "timestamp_last_played",
            "last_played_timestamp",
            "played_at",
        ),
    )
    data = {
        "name": name,
        "artists": artists,
        "image_url": image_url,
        "item_id": item_id,
        "provider": provider,
        "uri": uri,
        "album_type": album_type,
        "provider_mappings": provider_mappings,
    }
    if added_at is not None:
        data["added_at"] = added_at
    if last_played is not None:
        data["last_played"] = last_played
    return data


def _serialize_artist(artist: object) -> dict:
    if isinstance(artist, dict):
        name = artist.get("name")
    else:
        name = getattr(artist, "name", None)
    name = name or "Unknown Artist"
    return {"name": name}


def _serialize_playlist(playlist: object) -> dict:
    name = getattr(playlist, "name", None) or "Untitled Playlist"
    item_id = getattr(playlist, "item_id", None)
    provider = getattr(playlist, "provider", None)
    uri = getattr(playlist, "uri", None)
    owner = getattr(playlist, "owner", None)
    is_editable = bool(getattr(playlist, "is_editable", False))
    data = {
        "name": name,
        "item_id": item_id,
        "provider": provider,
        "uri": uri,
        "is_editable": is_editable,
    }
    if owner:
        data["owner"] = owner
    return data


async def fetch_albums(client: MusicAssistantClient) -> list[dict]:
    albums: list[dict] = []
    offset = 0
    while True:
        page = await client.music.get_library_albums(
            limit=DEFAULT_PAGE_SIZE,
            offset=offset,
            order_by="sort_name",
        )
        if not page:
            break
        for album in page:
            albums.append(_serialize_album(client, album))
        if len(page) < DEFAULT_PAGE_SIZE:
            break
        offset += DEFAULT_PAGE_SIZE
    return albums


async def fetch_artists(client: MusicAssistantClient) -> list[dict]:
    artists: list[dict] = []
    offset = 0
    while True:
        page = await client.music.get_library_artists(
            limit=DEFAULT_PAGE_SIZE,
            offset=offset,
            order_by="sort_name",
        )
        if not page:
            break
        for artist in page:
            artists.append(_serialize_artist(artist))
        if len(page) < DEFAULT_PAGE_SIZE:
            break
        offset += DEFAULT_PAGE_SIZE
    return artists


async def fetch_playlists(client: MusicAssistantClient) -> list[dict]:
    playlists: list[dict] = []
    offset = 0
    while True:
        page = await client.music.get_library_playlists(
            limit=DEFAULT_PAGE_SIZE,
            offset=offset,
            order_by="sort_name",
        )
        if not page:
            break
        for playlist in page:
            playlists.append(_serialize_playlist(playlist))
        if len(page) < DEFAULT_PAGE_SIZE:
            break
        offset += DEFAULT_PAGE_SIZE
    return playlists


async def load_library_data(
    client: MusicAssistantClient,
) -> tuple[list[dict], list[dict], list[dict]]:
    albums = await fetch_albums(client)
    artists = await fetch_artists(client)
    playlists = await fetch_playlists(client)
    return albums, artists, playlists


async def create_playlist(client: MusicAssistantClient, name: str) -> object:
    return await client.music.create_playlist(name)


__all__ = [
    "fetch_albums",
    "fetch_artists",
    "fetch_playlists",
    "load_library_data",
    "create_playlist",
    "_serialize_album",
    "_serialize_artist",
    "_serialize_playlist",
]
