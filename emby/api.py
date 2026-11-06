import threading
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from contextlib import ExitStack
from helper import utils, queue, cache, copy, paging
from database import dbio
from . import httpcache, metadata

EmbyFields = {
    "musicartist": ["Genres", "SortName", "ProductionYear", "DateCreated", "ProviderIds", "Overview", "Path", "PresentationUniqueKey", "UserDataPlayCount", "UserDataLastPlayedDate"],
    "musicalbum": ["Genres", "SortName", "ProductionYear", "DateCreated", "ProviderIds", "Overview", "Path", "Studios", "PremiereDate", "UserDataPlayCount", "UserDataLastPlayedDate", "CommunityRating"],
    "audio": ["Genres", "SortName", "ProductionYear", "DateCreated", "MediaStreams", "ProviderIds", "Overview", "Path", "PremiereDate", "UserDataPlayCount", "UserDataLastPlayedDate", "CommunityRating", "ParentId", "MediaSources"],
    "movie": ["Path", "Genres", "SortName", "Studios", "Writer", "Taglines", "Video3DFormat", "OfficialRating", "PremiereDate", "ProductionYear", "DateCreated", "People", "Overview", "CommunityRating", "ShortOverview", "ProductionLocations", "ProviderIds", "ParentId", "MediaSources", "PresentationUniqueKey", "OriginalTitle", "AlternateMediaSources", "PartCount", "Chapters", "Tags", "UserDataPlayCount", "UserDataLastPlayedDate"],
    "boxset": ["Overview", "SortName", "DateCreated", "UserDataPlayCount", "UserDataLastPlayedDate"],
    "series": ["Path", "Genres", "SortName", "Studios", "Writer", "Taglines", "OfficialRating", "PremiereDate", "ProductionYear", "DateCreated", "People", "Overview", "CommunityRating", "ShortOverview", "ProviderIds", "ParentId", "Status", "PresentationUniqueKey", "OriginalTitle", "Tags", "UserDataPlayCount", "UserDataLastPlayedDate"],
    "season": ["PresentationUniqueKey", "SortName", "Tags", "DateCreated", "UserDataPlayCount", "UserDataLastPlayedDate", "Overview"],
    "episode": ["SpecialEpisodeNumbers", "ParentId", "Path", "Genres", "SortName", "Studios", "Writer", "Taglines", "Video3DFormat", "OfficialRating", "PremiereDate", "ProductionYear", "DateCreated", "People", "Overview", "CommunityRating", "ShortOverview", "Tags", "ProviderIds", "MediaSources", "PresentationUniqueKey", "OriginalTitle", "AlternateMediaSources", "PartCount", "Chapters", "UserDataPlayCount", "UserDataLastPlayedDate"],
    "musicvideo": ["Path", "Genres", "SortName", "Studios", "Writer", "Taglines", "Video3DFormat", "OfficialRating", "PremiereDate", "ProductionYear", "DateCreated", "People", "Overview", "CommunityRating", "ShortOverview", "Tags", "ProviderIds", "ParentId", "MediaSources", "PresentationUniqueKey", "OriginalTitle", "AlternateMediaSources", "PartCount", "Chapters", "UserDataPlayCount", "UserDataLastPlayedDate"],
    "video": ["Path", "Genres", "SortName", "Studios", "Writer", "Taglines", "Video3DFormat", "OfficialRating", "PremiereDate", "ProductionYear", "DateCreated", "People", "Overview", "CommunityRating", "ShortOverview", "ProductionLocations", "ProviderIds", "ParentId", "MediaSources", "PresentationUniqueKey", "OriginalTitle", "AlternateMediaSources", "Chapters", "Tags", "UserDataPlayCount", "UserDataLastPlayedDate"],
    "folder": ["Path",],
    "playlist": ["SortName", "Overview", "Path"],
    "genre": [],
    "musicgenre": [],
    "person": [],
    "tag": [],
    "collectionfolder": [],
    "studio": [],
    "all": ["Path", "Genres", "SortName", "Studios", "Writer", "Taglines", "Video3DFormat", "OfficialRating", "PremiereDate", "ProductionYear", "DateCreated", "People", "Overview", "CommunityRating", "ShortOverview", "ProductionLocations", "ProviderIds", "ParentId", "MediaSources", "PresentationUniqueKey", "OriginalTitle", "AlternateMediaSources", "Chapters", "Tags", "UserDataPlayCount", "UserDataLastPlayedDate"]
}


class ItemQueryError(RuntimeError):
    """A sync query failed; its pending work must be retained."""


class _ChangeItems:
    """Keep only startup sync inputs, not complete response objects."""
    def __init__(self, MediaType, Abort):
        self.MediaType = MediaType.lower()
        self.Abort = Abort
        self.Items = []

    def put(self, Data):
        if utils.SystemShutdown or self.Abort.is_set():
            raise InterruptedError("Change discovery cancelled")

        if Data == "QUIT":
            return

        for Item in Data:
            if Item['Type'].lower() == self.MediaType:
                Change = {'Id': Item['Id'], 'Type': Item['Type']}

                if Item['Type'] in utils.FavoriteTypes:
                    Change['UserData'] = Item.get('UserData') or {}

                self.Items.append(Change)

class API:
    def __init__(self, ServerData, ViewItems, LibrarySyncedNames, LibrarySyncedContent, LibrarySyncedKodiDBs, EmbySession, http):
        self.ServerData = ServerData
        self.ViewItems = ViewItems
        self.LibrarySyncedNames = LibrarySyncedNames
        self.LibrarySyncedContent = LibrarySyncedContent
        self.LibrarySyncedKodiDBs = LibrarySyncedKodiDBs
        self.EmbySession = EmbySession
        self.http = http
        self.ProcessProgress = {}
        self.ProcessProgressCondition = threading.Condition(threading.Lock())

    def update_Progress(self, WorkerName, Value):
        self.ProcessProgress[WorkerName] = Value

        with utils.SafeLock(self.ProcessProgressCondition):
            self.ProcessProgressCondition.notify_all()


    def get_Items_Ids(self, Ids, MediaTypes, Dynamic, Basic, ProcessProgressId, LibraryId, Extra, BusyFunction, UserData, Strict=False):
        if utils.SystemShutdown:
            if Strict:
                raise ItemQueryError("Item query cancelled")
            return
        RequestedIds = Ids.copy()
        Found = {}
        # Merge cached and fetched items in request order, including repeated IDs.
        if Dynamic:
            for Id in dict.fromkeys(Ids):
                ItemCache = cache.get_ItemByEmbyId(Id, self.ServerData['ServerId'])
                if ItemCache:
                    Found[Id] = ItemCache
            Ids = list(dict.fromkeys(Id for Id in Ids if Id not in Found))

        ItemsQueue = queue.Queue()

        for MediaType in MediaTypes:
            if not Ids: # Ids are removed in async_get_Items_Ids thread
                break

            PendingIds = Counter(Ids) if Strict else None
            utils.start_thread(self.produce_Items_Ids, (ItemsQueue, Ids.copy(), Dynamic, Basic, ProcessProgressId, LibraryId, MediaType, Extra, BusyFunction, UserData, Strict))

            while True:
                Items = ItemsQueue.getall(lambda: utils.SystemShutdown)

                if utils.SystemShutdown:
                    if Strict:
                        raise ItemQueryError("Item query cancelled")
                    return

                if not Items:
                    break

                Finished = False
                for Item in Items:
                    if isinstance(Item, ItemQueryError):
                        raise Item
                    if Item == "QUIT":
                        Finished = True
                        break
                    if Strict and PendingIds[Item['Id']]:
                        PendingIds[Item['Id']] -= 1
                    if Dynamic:
                        Found[Item['Id']] = Item
                    else:
                        yield Item
                if Finished:
                    break
            if Strict:
                Remaining = []
                for Id in Ids:
                    if PendingIds[Id]:
                        Remaining.append(Id)
                        PendingIds[Id] -= 1
                Ids[:] = Remaining
            elif Dynamic:
                Ids = [Id for Id in Ids if Id not in Found]

        if Dynamic:
            for Id in RequestedIds:
                if Id in Found:
                    yield Found[Id]

    def produce_Items_Ids(self, ItemsQueue, *Args):
        try:
            self.async_get_Items_Ids(ItemsQueue, *Args)
        except Exception as Error:
            # Deliver failure to the consumer instead of leaving it waiting on a dead producer.
            ItemsQueue.put(ItemQueryError(str(Error)))

    def request_items(self, Request, Params, BusyFunction, Strict=False, ConnectionId=""):
        Status, _, Payload = self.http.request("GET", Request, Params, {}, False, "", BusyFunction, ConnectionId)
        if Strict:
            if Status == 204:
                return {"Items": []}
            if Status != 200 or not isinstance(Payload, dict) or not isinstance(Payload.get("Items"), list):
                raise ItemQueryError(f"Item query failed: {Status}")
            if any(not isinstance(Item, dict) or not isinstance(Item.get('Id'), str) or not Item['Id'] or not isinstance(Item.get('Type'), str) or not Item['Type'] for Item in Payload['Items']):
                raise ItemQueryError("Invalid item query response")
        return Payload

    def async_get_Items_Ids(self, ItemsQueue, Ids, Dynamic, Basic, ProcessProgressId, LibraryId, MediaType, Extra, BusyFunction, UserData, Strict=False):
        CounterFound = 0
        ItemsSorted = {}
        IdsBackup = Ids.copy()
        RequestedIds = set(Ids)
        LibrarySyncedIds = ()

        if MediaType == "All":
            Params = {'EnableTotalRecordCount': False, 'Recursive': True, 'Fields': self.get_Fields(MediaType, Basic, Dynamic, UserData)} # Workaround: Emby server doesn not respect IncludeItemTypes=Video when it's a "special"
        else:
            Params = {'EnableTotalRecordCount': False, 'Recursive': True, 'Fields': self.get_Fields(MediaType, Basic, Dynamic, UserData), 'IncludeItemTypes': MediaType}

        SubContent = bool(MediaType in ("BoxSet", "MusicArtist", "MusicAlbum", "Genre", "MusicGenre", "Tag", "Person", "Studio", "Playlist"))

        if UserData:
            Request = f"Users/{self.ServerData['UserId']}/Items"
        else:
            Request = "Items"

        if Extra:
            Params.update(Extra)

        if 'SortBy' not in Params:
            Params['SortBy'] = "None"

        for _ in range(2):
            Payload = {}
            Params['Ids'] = ",".join(Ids)

            # Query content
            if not Dynamic:
                if LibraryId == "OneShot": # Items may exist
                    Payload = self.request_items(Request, Params, BusyFunction, Strict)

                    if 'Items' in Payload:
                        for Item in Payload['Items']:
                            ItemsQueue.put(Item)
                            CounterFound += 1

                    Ids = []
                elif LibraryId == "SingleId": # Items must exists
                    Payload = self.request_items(Request, Params, BusyFunction, Strict)

                    if 'Items' in Payload:
                        for Item in Payload['Items']:

                            if Item['Id'] in Ids:
                                del Ids[Ids.index(Item['Id'])]

                            ItemsQueue.put(Item)
                            CounterFound += 1
                elif LibraryId and LibraryId.lower() != "unknown": # Kodi start updates, Items must exists
                    Payload = self.request_items(Request, Params, BusyFunction, Strict)

                    if 'Items' in Payload:
                        ReceivedIds = {}

                        try:
                            for Item in Payload['Items']:
                                Item['LibraryId'] = LibraryId
                                ItemId = Item['Id']

                                # Request IDs are strings; other JSON types never match them.
                                if isinstance(ItemId, str):
                                    ReceivedIds[ItemId] = ReceivedIds.get(ItemId, 0) + 1

                                ItemsQueue.put(Item)
                                CounterFound += 1
                        finally:
                            if ReceivedIds:
                                RemainingIds = []

                                for ItemId in Ids:
                                    if ReceivedIds.get(ItemId, 0):
                                        ReceivedIds[ItemId] -= 1
                                    else:
                                        RemainingIds.append(ItemId)

                                # Only this API thread owns the copy; retain its order and identity.
                                Ids[:] = RemainingIds
                                del RemainingIds

                            del ReceivedIds
                else: # realtime updates via websocket
                    if SubContent: # Workaround: Subcontent does not always respect ParentId queries
                        if not LibrarySyncedIds:
                            embydb = dbio.DBOpenRO(self.ServerData['ServerId'], "Realtimesync_Subcontent")
                            LibrarySyncedIds = embydb.get_LibraryIds_by_EmbyIds(Ids)
                            dbio.DBCloseRO(self.ServerData['ServerId'], "Realtimesync_Subcontent")

                        Payload = self.request_items(Request, Params, BusyFunction, Strict)

                        if 'Items' in Payload:
                            for Item in Payload['Items']: # Check if content is an synced content update
                                if Item['Type'] == MediaType:
                                    if Item['Id'] in LibrarySyncedIds:
                                        for LibrarySyncedId in LibrarySyncedIds[Item['Id']]:
                                            if MediaType in self.LibrarySyncedContent[LibrarySyncedId[0]]:
                                                if Item['Id'] in Ids:
                                                    del Ids[Ids.index(Item['Id'])]

                                                Item['LibraryId'] = LibrarySyncedId[0]
                                                ItemsQueue.put(Item)
                                                CounterFound += 1
                    else:
                        for LibrarySyncedId in self.LibrarySyncedNames:
                            if str(LibrarySyncedId) not in ("999999999",):
                                Params.update({'ParentId': LibrarySyncedId})
                            else:
                                if MediaType != "Person":
                                    continue

                            Payload = self.request_items(Request, Params, BusyFunction, Strict)

                            if 'Items' in Payload:
                                for Item in Payload['Items']:
                                    if Item['Type'] == MediaType:
                                        Item['LibraryId'] = LibrarySyncedId

                                        if Item['Id'] in Ids:
                                            del Ids[Ids.index(Item['Id'])]

                                        ItemsQueue.put(Item)
                                        CounterFound += 1

                            if not Ids or utils.SystemShutdown: # Stop only after every requested ID has been resolved.
                                break
            else: # Resolve requested items for remote playback or generated ListItems
                Payload = self.request_items(Request, Params, BusyFunction, Strict)

                # Emby server bug, MusicArtist, MusicAlbum, Audio queries on mixed content libraries are not accepted, wen userdate are request. Try workaround
                if 'Items' in Payload and not Payload['Items']:
                    if Request != "Items" and MediaType in ("MusicArtist", "MusicAlbum", "Audio"):
                        Request = "Items"

                        if "Fields" in Params:
                            Params["Fields"] = ",".join(Field for Field in Params["Fields"].split(",") if Field not in ("UserDataLastPlayedDate", "UserDataPlayCount", "PlayedDate"))

                        Payload = self.request_items(Request, Params, BusyFunction, Strict)

                if 'Items' in Payload and Payload['Items']:
                    for Item in Payload['Items']:
                        if MediaType in ('All', Item['Type']) and Item['Id'] in RequestedIds:
                            ItemsSorted[Item['Id']] = Item

                    Ids[:] = [Id for Id in Ids if Id not in ItemsSorted]

                    CounterFound += len(Payload['Items'])

            del Payload  # release memory

            if not Ids:
                break

            if utils.SystemShutdown or not self.async_throttle_queries(CounterFound, ProcessProgressId): # all requested items received
                break

            if Ids and MediaType in ("MusicArtist", "Folder", "MusicGenre", "MusicAlbum", "Audio") and (Request.startswith("Users/") or "UserId" in Params) and 'IncludeItemTypes' in Params:
                del Params['IncludeItemTypes']
            else:
                break

        # Sorted items -> Emby sorts by ascending Ids
        if ItemsSorted:
            ItemsQueue.put([ItemsSorted[Id] for Id in IdsBackup if Id in ItemsSorted])
            del ItemsSorted

        ItemsQueue.put("QUIT")

    def async_throttle_queries(self, Index, ProcessProgressId):
        if ProcessProgressId and ProcessProgressId in self.ProcessProgress:

            with utils.SafeLock(self.ProcessProgressCondition):
                while Index > self.ProcessProgress[ProcessProgressId]:
                    if utils.SystemShutdown or self.ProcessProgress[ProcessProgressId] == -1: # Cancel
                        return False

                    self.ProcessProgressCondition.wait(timeout=0.1)

        return True

    def get_Items(self, ParentId, MediaTypes, Basic, Extra, ProcessProgressId, BusyFunction, UserData):
        if Extra and Extra.get("PlaylistItems"):
            # The playlist endpoint returns entries in playlist order, including repeats.
            Params = {'UserId': self.ServerData['UserId'], 'Fields': self.get_Fields("All", Basic, False, UserData),
                      'EnableUserData': UserData, 'Limit': Extra.get("Limit", paging.get_limit("Playlist")), 'StartIndex': 0}
            while not utils.SystemShutdown:
                Items = self.request_items(f"Playlists/{ParentId}/Items", Params, BusyFunction, True)['Items']
                yield from (Item for Item in Items if Item['Type'] in MediaTypes)
                if len(Items) < Params['Limit']:
                    return
                Params['StartIndex'] += len(Items)
            raise ItemQueryError("Playlist query cancelled")

        ItemsQueue = queue.Queue()

        for MediaType in MediaTypes:

            # People are created from selected work credits; only query their metadata deltas.
            if MediaType == "Person" and not Basic:
                continue

            RequestLocal, Params = self.get_Items_Request(ParentId, MediaType, Basic, Extra, UserData)
            CustomLimit = bool(Extra and "Limit" in Extra)

            utils.start_thread(self.produce_Items, (RequestLocal, ItemsQueue, Params, ProcessProgressId, CustomLimit, BusyFunction))
            ExitLoop = False

            while True:
                Items = ItemsQueue.getall(lambda: utils.SystemShutdown)

                if utils.SystemShutdown:
                    raise ItemQueryError("Item query cancelled")

                if not Items:
                    break

                # Bugs in Emby server might send wrong data (e.g. playlists libraries, MusicGenre metadata wrong)
                for Item in Items:
                    if isinstance(Item, ItemQueryError):
                        raise Item
                    if Item == "QUIT":
                        ExitLoop = True
                        break

                    if Item['Type'].lower() == MediaType.lower():
                        if MediaType == "Studio":
                            Item['StudioForSeries'] = True
                        yield Item

                del Items  # release memory

                if ExitLoop:
                    break


    def produce_Items(self, Request, ItemsQueue, *Args):
        try:
            self.async_get_Items(Request, ItemsQueue, *Args)
        except Exception as Error:
            ItemsQueue.put(ItemQueryError(str(Error)))

    def get_Items_Request(self, ParentId, MediaType, Basic, Extra, UserData):
        Request = f"Users/{self.ServerData['UserId']}/Items" if UserData else "Items"
        Params = {'EnableTotalRecordCount': False, 'Recursive': True, 'Limit': paging.get_limit(MediaType),
                  'IncludeItemTypes': MediaType, 'Fields': self.get_Fields(MediaType, Basic, False, UserData)}

        if MediaType == "Studio":
            Request = "Studios"
            Params.update({'IncludeItemTypes': "Series", 'UserId': self.ServerData['UserId'], 'EnableUserData': UserData})

        if ParentId and str(ParentId) != "999999999":
            Params['ParentId'] = ParentId

        Params.update(Extra or {})
        Params.setdefault('SortBy', "None")
        return Request, Params

    def get_ItemChanges(self, Query, ConnectionId, Abort):
        ParentId, MediaType, Extra = Query
        Request, Params = self.get_Items_Request(ParentId, MediaType, True, Extra, True)
        Items = _ChangeItems(MediaType, Abort)
        # Run pagination in the pool worker itself; no producer thread per query.
        self.async_get_Items(Request, Items, Params, "", bool(Extra and "Limit" in Extra), None, ConnectionId)

        if utils.SystemShutdown or Abort.is_set():
            raise InterruptedError("Change discovery cancelled")

        return Items.Items

    def get_Changes(self, Queries):
        """Fetch bounded independent queries and yield in their original order."""
        Queries = iter(Queries)
        Abort = threading.Event()

        with ExitStack() as Connections:
            Pool = ThreadPoolExecutor(max_workers=paging.CHANGE_QUERY_WORKERS, thread_name_prefix="EmbyChanges")
            Pending = deque()
            ConnectionIds = []

            try:
                for _ in range(paging.CHANGE_QUERY_WORKERS):
                    Query = next(Queries, None)

                    if Query is None:
                        break

                    ConnectionId = Connections.enter_context(self.http.HTTP.query_connection(Abort.is_set))
                    ConnectionIds.append(ConnectionId)
                    Pending.append((Query, ConnectionId, Pool.submit(self.get_ItemChanges, Query, ConnectionId, Abort)))

                while Pending:
                    Query, ConnectionId, Future = Pending.popleft()

                    while True:
                        if utils.SystemShutdown:
                            raise InterruptedError("Change discovery cancelled")

                        try:
                            Items = Future.result(timeout=0.1)
                            break
                        except FutureTimeout:
                            if Future.done():
                                Items = Future.result()  # Propagate a worker's own TimeoutError.
                                break

                    yield Query, Items
                    Query = next(Queries, None)

                    if Query is not None:
                        Pending.append((Query, ConnectionId, Pool.submit(self.get_ItemChanges, Query, ConnectionId, Abort)))
            finally:
                Abort.set()

                # Wake blocked I/O before joining; retries see the abort event.
                for ConnectionId in ConnectionIds:
                    self.http.HTTP.Common.socket_close(ConnectionId, False)

                for _, _, Future in Pending:
                    Future.cancel()

                Pool.shutdown(wait=True)

    def async_get_Items(self, Request, ItemsQueue, Params, ProcessProgressId, CustomLimit, BusyFunction, ConnectionId=""):
        Index = 0
        ItemCounter = 0
        Limit = Params['Limit']

        # Workaround for not respected ParentIds Item query
        if Params.get('IncludeItemTypes', "") == "MusicGenre":
            Request = "MusicGenres"
            Params['ParentId'] = str(Params['ParentId'])

            if Params['ParentId'] in self.ViewItems:
                if self.ViewItems[Params['ParentId']][1] == "musicvideos":
                    Params['IncludeItemTypes'] = "MusicVideo"
                elif self.ViewItems[Params['ParentId']][1] in ("music", "audiobooks"):
                    Params['IncludeItemTypes'] = "Audio"
                else: # mixed, playlist
                    Params['IncludeItemTypes'] = "MusicVideo,Audio"

            Params['UserId'] = self.ServerData['UserId']

        while True:
            Params['StartIndex'] = Index
            ContentSupported = ""
            StartsWith = ""

            if "SpecialFilter" in Params:
                if Params["SpecialFilter"][0] == "StartsWith":
                    StartsWith = Params["SpecialFilter"][1].lower()

                del Params["SpecialFilter"]

            if "ContentSupported" in Params:
                ContentSupported = Params["ContentSupported"]
                del Params["ContentSupported"]

            Payload = self.request_items(Request, Params, BusyFunction, True, ConnectionId)

            # Emby server bug, MusicArtist, MusicAlbum, Audio queries on mixed content libraries are not accepted, when userdata are requested. Try workaround
            if 'Items' in Payload and not Payload['Items'] and not "MinDateLastSavedForUser" in Params:
                if Request != "Items" and 'IncludeItemTypes' in Params and Params['IncludeItemTypes'] in ("MusicArtist", "MusicAlbum", "Audio"):
                    Request = "Items"

                    if "Fields" in Params:
                        Params["Fields"] = ",".join(Field for Field in Params["Fields"].split(",") if Field not in ("UserDataLastPlayedDate", "UserDataPlayCount", "PlayedDate"))

                    Payload = self.request_items(Request, Params, BusyFunction, True, ConnectionId)

            # Special filters -> Emby's NameLessThan and NameStartsWith filter are too slow, do it manually
            if StartsWith:
                Items = copy.Object(Payload['Items'])
                del Payload
                Payload = {'Items': []}

                for Item in Items:
                    if 'Name' in Item and Item['Name']:
                        CompareChar = Item['Name'][0].lower()

                        if StartsWith != "specialcharacter":
                            if CompareChar.startswith(StartsWith):
                                Payload['Items'].append(Item)
                        else:
                            if CompareChar < "a" or CompareChar > "z":
                                Payload['Items'].append(Item)

            ParentId = int(Params.get("ParentId", 0) or 0)
            ParentIdStr = str(ParentId)
            isMixed = False

            if ParentIdStr in self.ViewItems:
                isMixed = self.ViewItems[ParentIdStr][1] == "mixed"

            # MusicArtist is not unique for MusicVideo and Audio; verify subcontent in mixed libraries
            if 'Items' in Payload and Payload['Items'] and ContentSupported and (ParentId < 1 or isMixed):
                VerifyContent = False
                ParamsCheck = {}

                if Params['IncludeItemTypes'] == "MusicArtist":
                    if ContentSupported == "video":
                        ParamsCheck = {"Recursive": True, "IncludeItemTypes": "MusicVideo", "Limit": 1}
                    else:
                        ParamsCheck = {"Recursive": True, "IncludeItemTypes": "Audio", "Limit": 1}

                    VerifyContent = True
                elif Params['IncludeItemTypes'] == "BoxSet":
                    if ContentSupported == "video":
                        ParamsCheck = {"Recursive": True, "IncludeItemTypes": "MusicVideo,Movie,Episode,Video", "Limit": 1}
                    else:
                        ParamsCheck = {"Recursive": True, "IncludeItemTypes": "Audio", "Limit": 1}

                    VerifyContent = True

                if VerifyContent:
                    Items = copy.Object(Payload['Items'])
                    del Payload
                    Payload = {'Items': []}

                    for Item in Items:
                        ParamsCheck["ParentId"] = Item['Id']
                        PayloadCheck = self.request_items("Items", ParamsCheck, BusyFunction, True, ConnectionId)

                        if 'Items' in PayloadCheck and PayloadCheck['Items']:
                            Payload['Items'].append(Item)

            DirectItems = Request.lower().find("latest") != -1

            if DirectItems:
                if utils.SystemShutdown or not Payload:
                    ItemsQueue.put("QUIT")
                    del Payload  # release memory
                    return

                ItemsQueue.put(Payload)
                ReceivedItems = len(Payload)
                ItemCounter += ReceivedItems
            else:
                if utils.SystemShutdown or 'Items' not in Payload or not Payload['Items']:
                    ItemsQueue.put("QUIT")
                    del Payload  # release memory
                    return

                ItemsQueue.put(Payload['Items'])
                ReceivedItems = len(Payload['Items'])
                ItemCounter += ReceivedItems

            del Payload  # release memory

            if ReceivedItems < Limit:
                ItemsQueue.put("QUIT")
                return

            if CustomLimit:
                ItemsQueue.put("QUIT")
                return

            if not self.async_throttle_queries(Index, ProcessProgressId):
                ItemsQueue.put("QUIT")
                return

            Index += Limit

    def get_Item(self, Id, MediaTypes, Dynamic, Basic, UserData, Strict=False):
        # Load Item from cache
        if Dynamic:
            ItemCache = cache.get_ItemByEmbyId(Id, self.ServerData['ServerId'])

            if ItemCache:
                return ItemCache

        ItemsQueue = queue.Queue()

        for MediaType in MediaTypes:
            self.async_get_Items_Ids(ItemsQueue, [str(Id)], Dynamic, Basic, "", "SingleId", MediaType, {}, None, UserData, Strict)
            Item = ItemsQueue.get()

            if Item != "QUIT":
                del ItemsQueue
                return Item

        return {}


    def get_similar(self, Id, EmbyType, Limit, Cancelled):
        """Return raw identities for the local Similar API; never create dynamic items."""
        with self.http.HTTP.query_connection(Cancelled, "SIMILAR") as ConnectionId:
            Status, _, Payload = self.http.request("GET", f"Items/{Id}/Similar", {
                'UserId': self.ServerData['UserId'], 'IncludeItemTypes': EmbyType, 'Limit': Limit,
                'EnableTotalRecordCount': False, 'EnableImages': False, 'EnableUserData': False
            }, {}, False, "", None, ConnectionId)
        if Status != 200 or not isinstance(Payload, dict) or not isinstance(Payload.get('Items'), list):
            return None
        return Payload['Items']

    def get_users(self):
        _, _, Payload = self.http.request("GET", "Users", {'IsDisabled': False, 'IsHidden': False}, {}, False, "", None, "")
        return Payload

    def get_public_users(self):
        _, _, Payload = self.http.request("GET", "Users/Public", {}, {}, False, "", None, "")
        return Payload


    def get_views(self):
        _, _, Payload = self.http.request("GET", f"Users/{self.ServerData['UserId']}/Views", {}, {}, False, "", None, "")
        return Payload


    def get_device(self):
        _, _, Payload = self.http.request("GET", "Sessions", {'DeviceId': self.ServerData['DeviceId']}, {}, False, "", None, "")
        return Payload


    def get_additional_parts(self, Id):
        _, _, Payload = self.http.request("GET", f"Videos/{Id}/AdditionalParts", {'Fields': "Path,MediaSources"}, {}, False, "", None, "")
        return Payload


    def get_sync_queue(self, date):
        Status, _, Payload = self.http.request("GET", f"Emby.Kodi.SyncQueue/{self.ServerData['UserId']}/GetItems", {'LastUpdateDT': date}, {}, False, "", None, "")
        if Status == 404:  # The Kodi Companion server plugin is optional.
            return {"ItemsRemoved": []}
        if Status != 200 or not isinstance(Payload, dict) or not isinstance(Payload.get("ItemsRemoved"), list):
            raise ItemQueryError(f"Deletion queue query failed: {Status}")
        return Payload

    def set_progress(self, Id, Progress, PlayCount):
        self.http.Queues["ASYNC"].put((("POST", f"Users/{self.ServerData['UserId']}/Items/{Id}/UserData", {"PlaybackPositionTicks": Progress, "PlayCount": PlayCount, "Played": bool(PlayCount)}, False),))


    def set_played(self, Id, PlayCount):
        if PlayCount:
            self.http.Queues["ASYNC"].put((("POST", f"Users/{self.ServerData['UserId']}/PlayedItems/{Id}", {}, False),))
        else:
            self.http.Queues["ASYNC"].put((("DELETE", f"Users/{self.ServerData['UserId']}/PlayedItems/{Id}", {}, False),))

    def refresh_item(self, Id):
        self.http.Queues["ASYNC"].put((("POST", f"Items/{Id}/Refresh", {'Recursive': True, 'ImageRefreshMode': "FullRefresh", 'MetadataRefreshMode': "FullRefresh", 'ReplaceAllImages': False, 'ReplaceAllMetadata': True}, False),))

    def favorite(self, Id, Add):
        if Add:
            self.http.Queues["ASYNC"].put((("POST", f"Users/{self.ServerData['UserId']}/FavoriteItems/{Id}", {}, False),))
        else:
            self.http.Queues["ASYNC"].put((("DELETE", f"Users/{self.ServerData['UserId']}/FavoriteItems/{Id}", {}, False),))

    def post_capabilities(self):
        self.http.request("POST", "Sessions/Capabilities/Full", {'Id': self.EmbySession[0]['Id'], 'SupportsRemoteControl': True, "QueueableMediaTypes": ["Audio", "Video"], 'PlayableMediaTypes': ["Audio", "Video"], 'SupportsMediaControl': True, 'SupportsSync': True, 'SupportedCommands': ["MoveUp", "MoveDown", "MoveLeft", "MoveRight", "Select", "Back", "ToggleContextMenu", "ToggleFullscreen", "ToggleOsdMenu", "GoHome", "PageUp", "NextLetter", "GoToSearch", "GoToSettings", "PageDown", "PreviousLetter", "TakeScreenshot", "VolumeUp", "VolumeDown", "ToggleMute", "SendString", "DisplayMessage", "SetAudioStreamIndex", "SetSubtitleStreamIndex", "SetRepeatMode", "SetShuffle", "SetPlaybackRate", "Mute", "Unmute", "SetVolume", "MovePlaylistItem", "RemoveFromPlaylist", "SetCurrentPlaylistItem", "ToggleStats", "Pause", "Unpause", "Play", "Playstate", "PlayNext", "PlayMediaSource", "DisplayContent"], 'IconUrl': "https://raw.githubusercontent.com/MediaBrowser/plugin.video.emby/master/kodi_icon.png"}, {}, False, "", None, "")

    def session_add_user(self, session_id, user_id, option):
        if option:
            self.http.Queues["ASYNC"].put((("POST", f"Sessions/{session_id}/Users/{user_id}", {}, False),))
        else:
            self.http.Queues["ASYNC"].put((("DELETE", f"Sessions/{session_id}/Users/{user_id}", {}, False),))

    def session_playing(self, EmbySessionInfo, PlaylistKodi, PlaylistEmby, PlaylistPosition):
        EmbySessionInfoLocal, PlaylistEmby = update_sessioninfo(EmbySessionInfo, "", PlaylistKodi, PlaylistEmby, PlaylistPosition)
        self.http.Queues["ASYNC"].put((("POST", "Sessions/Playing", EmbySessionInfoLocal, True),))
        return PlaylistEmby

    def session_progress(self, EmbySessionInfo, EventName, PlaylistKodi, PlaylistEmby, PlaylistPosition):
        EmbySessionInfoLocal, PlaylistEmby = update_sessioninfo(EmbySessionInfo, EventName, PlaylistKodi, PlaylistEmby, PlaylistPosition)
        self.http.Queues["ASYNC"].put((("POST", "Sessions/Playing/Progress", EmbySessionInfoLocal, False),))
        return PlaylistEmby

    def session_stop(self, EmbySessionInfo):
        httpcache.delete(EmbySessionInfo["PlaySessionId"])
        self.http.Queues["ASYNC"].put((("POST", "Sessions/Playing/Stopped", EmbySessionInfo, True),))

    def session_logout(self):
        self.http.request("POST", "Sessions/Logout", {}, {}, False, "", None, "")


    def get_publicinfo(self):
        _, _, Payload = self.http.request("GET", "system/info/public", {}, {}, False, "", None, "")
        return Payload


    def get_authbyname(self, Username, Password):
        _, _, Payload = self.http.request("POST", "Users/AuthenticateByName", {'username': Username, 'pw': Password or ""}, {}, False, "", None, "")
        return Payload

    def get_Subtitle_Binary(self, Id, MediaSourceId, SubtitleIndex, SubtitleFormat):
        _, _, Payload = self.http.request("GET", f"videos/{Id}/{MediaSourceId}/Subtitles/{SubtitleIndex}/stream.{SubtitleFormat}", {}, {}, True, "", None, "")
        return Payload

    def get_embyconnect_authenticate(self, Username, Password):
        _, _, Payload = self.http.request("POST", "service/user/authenticate", {'nameOrEmail': Username, 'rawpw': Password}, {'X-Application': f"{utils.addon_name}/{utils.addon_version}"}, False, "https://connect.emby.media:443", None, "")
        return Payload

    def get_embyconnect_servers(self):
        _, _, Payload = self.http.request("GET", f"service/servers?userId={self.ServerData['EmbyConnectUserId']}", {}, {'X-Connect-UserToken': self.ServerData['EmbyConnectAccessToken'], 'X-Application': f"{utils.addon_name}/{utils.addon_version}"}, False, "https://connect.emby.media:443", None, "")
        return Payload

    def get_Fields(self, MediaType, Basic, Dynamic, UserData):
        if not Basic:
            Fields = EmbyFields[MediaType.lower()].copy()

            if not Dynamic:
                if MediaType.lower() != "series" and "Studios" in Fields:
                    Fields.remove("Studios")

            # Playback metadata used by remote playback and generated ListItems
            if Dynamic:
                if MediaType in ("Series", "Season"):
                    Fields += ["RecursiveItemCount", "ChildCount"]

            if not UserData:
                if "UserDataPlayCount" in Fields:
                    del Fields[Fields.index("UserDataPlayCount")]

                if "UserDataLastPlayedDate" in Fields:
                    del Fields[Fields.index("UserDataLastPlayedDate")]

            Fields = ",".join(list(dict.fromkeys(Fields))) # remove duplicates and join into string
        else:
            Fields = None

        return Fields

def update_sessioninfo(EmbySessionInfo, EventName, PlaylistKodi, PlaylistEmby, PlaylistPosition):
    # Build PlayingQueue
    PlaylistKodiLen = len(PlaylistKodi)
    PlaylistEmbyLen = len(PlaylistEmby)

    if EventName and PlaylistKodiLen > PlaylistEmbyLen:
        EventName = "PlaylistItemAdd"

    if PlaylistKodiLen != PlaylistEmbyLen:
        PlaylistEmby = PlaylistKodiLen * [{}] # allocate memory
        EmbyDBs = {}

        for PlaylistIndex, PlaylistKodiItem in enumerate(PlaylistKodi):
            # known content
            if "KodiId" in PlaylistKodiItem:
                EmbyId, ServerId = utils.get_EmbyId_ServerId_by_Fake_KodiId(PlaylistKodiItem["KodiId"])

                if not EmbyId:
                    for ServerId in utils.EmbyServers:
                        if ServerId not in EmbyDBs:
                            EmbyDBs[ServerId] = dbio.DBOpenRO(ServerId, "Playlist_Add")

                        EmbyId = EmbyDBs[ServerId].get_EmbyId_by_KodiId_KodiType(PlaylistKodiItem["KodiId"], PlaylistKodiItem["KodiType"])

                        if EmbyId:
                            break
                    else: # EmbyId not found
                        continue

                PlaylistEmby[PlaylistIndex] = {"Id": int(EmbyId), "PlaylistItemId": str(PlaylistIndex)}

            else:
                URL = utils.image_url_decode(PlaylistKodiItem["KodiFile"], False)
                URL = URL.replace("http://127.0.0.1:57342", "").replace("dav://127.0.0.1:57342", "")
                MetaData = metadata.load_MetaData(URL, True, False)
                PlaylistEmby[PlaylistIndex] = {"Id": int(MetaData["EmbyId"]), "PlaylistItemId": str(PlaylistIndex)}

        for EmbyDB in EmbyDBs:
            dbio.DBCloseRO(EmbyDB, "Playlist_Add")

    # Update info
    EmbySessionInfoLocal = copy.Object(EmbySessionInfo)

    try:
        EmbySessionInfoLocal.update({"PlaylistLength": len(PlaylistEmby), "NowPlayingQueue": PlaylistEmby, "PlaylistIndex": PlaylistPosition, "PlaylistItemId": PlaylistEmby[PlaylistPosition]['Id']})
    except:
        EmbySessionInfoLocal.update({"PlaylistLength": len(PlaylistEmby), "NowPlayingQueue": PlaylistEmby})

    if EventName:
        EmbySessionInfoLocal["EventName"] = EventName

    if 'MediaSourceId' in EmbySessionInfoLocal and not EmbySessionInfoLocal['MediaSourceId']:
        del EmbySessionInfoLocal['MediaSourceId']

    if 'PlaylistPosition' in EmbySessionInfoLocal and EmbySessionInfoLocal['PlaylistPosition'] == -1:
        del EmbySessionInfoLocal['PlaylistPosition']

    return EmbySessionInfoLocal, PlaylistEmby
