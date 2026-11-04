"""On-demand Emby recommendations with existing Kodi IDs and synced library names."""
from database import dbio
from . import utils

API_PATH = "/api/v1/items/"
MEDIA_TYPES = {"movie": "Movie", "tvshow": "Series"}
DEFAULT_LIMIT = 20
MAX_LIMIT = 100
TASK = "similar_api"
DB_TIMEOUT = 0.25


class QueryError(Exception):
    def __init__(self, Status, Code):
        super().__init__(Code)
        self.status = Status
        self.code = Code


def get_items(KodiType, KodiId, Limit, Cancelled):
    EmbyType = MEDIA_TYPES[KodiType]
    if utils.SystemShutdown or "video" not in utils.DatabaseFiles:
        raise QueryError(503, "unavailable")

    if Cancelled():
        raise QueryError(502, "upstream_error")

    if not existing_items(KodiType, [KodiId]):
        raise QueryError(404, "not_synced")

    Unavailable = False
    for ServerId, Server in tuple(utils.EmbyServers.items()):
        if ServerId not in utils.DatabaseFiles or not Server.library.SettingsLoaded:
            Unavailable = True
            continue

        if Cancelled():
            raise QueryError(502, "upstream_error")

        embydb = dbio.DBOpenRO(ServerId, TASK, DB_TIMEOUT)
        try:
            # Exact media type: home videos mapped to Kodi movies are outside this API.
            EmbyId = embydb.get_EmbyId_KodiId_ImageUrl_by_KodiId_EmbyType(KodiId, EmbyType, "video")[0]
        finally:
            dbio.DBCloseRO(ServerId, TASK)

        if EmbyId:
            break
    else:
        raise QueryError(503 if Unavailable else 404, "unavailable" if Unavailable else "not_synced")

    if not Server.Online or not Server.ServerData.get("UserId"):
        raise QueryError(503, "unavailable")

    # Hold no database connections while waiting for the server.
    Recommendations = Server.API.get_similar(EmbyId, EmbyType, Limit, Cancelled)
    if Recommendations is None or Cancelled():
        raise QueryError(502, "upstream_error")

    if utils.SystemShutdown or not Server.library.SettingsLoaded or ServerId not in utils.DatabaseFiles:
        raise QueryError(503, "unavailable")

    KodiItems = []
    Seen = {KodiId}
    embydb = dbio.DBOpenRO(ServerId, TASK, DB_TIMEOUT)
    try:
        for Item in Recommendations[:Limit]:
            if not isinstance(Item, dict) or Item.get("Type") != EmbyType or not Item.get("Id"):
                continue
            Rows = embydb.get_similar_item(Item["Id"], EmbyType)
            if not Rows:
                continue

            ItemId = Rows[0][0]
            if ItemId and ItemId not in Seen:
                Seen.add(ItemId)
                LibraryNames = dict.fromkeys(Name for _, Name in Rows if Name)
                KodiItems.append({"type": KodiType, "dbid": ItemId, "library": " / ".join(LibraryNames)})
    finally:
        dbio.DBCloseRO(ServerId, TASK)

    Existing = existing_items(KodiType, [Item["dbid"] for Item in KodiItems])
    return {"items": [Item for Item in KodiItems if Item["dbid"] in Existing]}


def existing_items(KodiType, KodiIds):
    if not KodiIds:
        return set()
    videodb = dbio.DBOpenRO("video", TASK, DB_TIMEOUT)
    try:
        return videodb.get_existing_similar_ids(KodiType, KodiIds)
    finally:
        dbio.DBCloseRO("video", TASK)
