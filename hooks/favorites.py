import sqlite3
import threading
from urllib.parse import parse_qs, urlsplit
import xbmc
import xbmcvfs
from helper import utils
from core import movies, videos, musicvideo, boxsets, musicartist, musicalbum, audio, playlist, series, season, episode, common
from database import dbio

KodiFavFile = "special://profile/favourites.xml"
FavoriteUpdatedByEmby = False
FavoriteUpdateLock = threading.Lock()


def monitor_Favorites():
    global FavoriteUpdatedByEmby
    FavoriteUpdatedByEmby = False
    FavoritesCached = get_Favorites()
    FavoriteTimestamp = 0
    FavFileExits = False

    while True:
        if utils.sleep(0.5):
            return

        if not FavFileExits and xbmcvfs.exists(KodiFavFile):
            FavFileExits = True

        if FavFileExits:
            Stats = xbmcvfs.Stat(KodiFavFile)
            TimestampReadOut = Stats.st_mtime()
        else:
            continue

        # Skip favorite update
        with utils.SafeLock(FavoriteUpdateLock):
            if FavoriteUpdatedByEmby:
                FavoriteUpdatedByEmby = False
                FavoritesCached = get_Favorites()
                continue

        # Check if favorite.xml file has changed (by timestamp)
        if FavoriteTimestamp < TimestampReadOut:
            Trigger = bool(FavoriteTimestamp)
            FavoriteTimestamp = TimestampReadOut
            FavoritesCurrent = get_Favorites()

            if Trigger:
                FavoritesRemoved = []
                FavoritesAdded = []

                # detect removed favorites
                for FavoriteCached in FavoritesCached["Favorites"]:
                    if FavoriteCached not in FavoritesCurrent["Favorites"]:
                        FavoritesRemoved.append(FavoriteCached)

                # detect added favorites
                for FavoriteCurrent in FavoritesCurrent["Favorites"]:
                    if FavoriteCurrent not in FavoritesCached["Favorites"]:
                        FavoritesAdded.append(FavoriteCurrent)

                for Index, FavoritesChanged in enumerate((FavoritesRemoved, FavoritesAdded)):
                    isAdded = bool(Index)

                    for FavoriteChanged in FavoritesChanged:
                        EmbyType = ""
                        ContentType = ""
                        EmbyId = ""
                        ServerId = ""
                        ImageUrlFromDB = ""
                        KodiItemId = -1
                        KodiItemIdFromDB = ""
                        Path, isPath = get_path(FavoriteChanged)

                        if not Path:
                            continue

                        # get metadata
                        if Path.startswith("videodb://tvshows/titles/"):
                            Temp = Path.split("/")

                            if Temp[5] and Temp[5] != "-1":
                                videodb = dbio.DBOpenRO("video", "Favorites")
                                KodiItemId = videodb.get_seasonid_by_showid_number(Temp[4], Temp[5]) # Temp[4] = KodiTVShowId, Temp[5] = SeasonNumber
                                dbio.DBCloseRO("video", "Favorites")
                                EmbyType = "Season"
                                ContentType = "video"
                            else:
                                KodiItemId = Temp[4]
                                EmbyType = "Series"
                                ContentType = "video"
                        elif Path.startswith("videodb://movies/sets/"):
                            Temp = Path.split("/")
                            KodiItemId = Temp[4]
                            EmbyType = "BoxSet"
                            ContentType = "video"
                        elif Path.startswith("videodb://movies/genres/") or Path.startswith("videodb://tvshows/genres/"):
                            continue
                        elif Path.startswith("videodb://movies/actors/") or Path.startswith("videodb://tvshows/actors/") or Path.startswith("videodb://musicvideos/actors/"):
                            continue
                        elif Path.startswith("videodb://movies/tags/") or Path.startswith("videodb://tvshows/tags/") or Path.startswith("videodb://musicvideos/tags/"):
                            continue
                        elif Path.startswith("videodb://movies/studios/") or Path.startswith("videodb://tvshows/studios/") or Path.startswith("videodb://musicvideos/studios/"):
                            continue
                        elif Path.startswith("special://profile/playlists/video/"):
                            Temp = Path.split("/")
                            KodiItemId = Temp[5][:-4]
                            EmbyType = "Playlist"
                            ContentType = "video"
                        elif Path.startswith("special://profile/playlists/music/"):
                            Temp = Path.split("/")
                            KodiItemId = Temp[5][:-4]
                            EmbyType = "Playlist"
                            ContentType = "music"
                        elif Path.startswith(("plugin://plugin.video.emby-next-gen/?mode=playlist&mediatype=video", "plugin://plugin.service.emby-next-gen/?mode=playlist&mediatype=video")):
                            Params = parse_qs(urlsplit(Path).query)
                            KodiItemId = Params.get("id", [""])[0]
                            EmbyType = "Playlist"
                            ContentType = "video"
                            EmbyId = Params.get("playlistid", [""])[0]
                            if EmbyId:
                                ServerId = Params.get("server", [""])[0]
                                if not EmbyId.isdecimal() or ServerId not in utils.EmbyServers:
                                    continue
                        elif Path.startswith(("plugin://plugin.audio.emby-next-gen/?mode=playlist&mediatype=audio", "plugin://plugin.service.emby-next-gen/?mode=playlist&mediatype=audio")):
                            KodiItemId = parse_qs(urlsplit(Path).query).get("id", [""])[0]
                            EmbyType = "Playlist"
                            ContentType = "music"
                        elif Path.startswith("musicdb://genres/"):
                            continue
                        elif Path.startswith("videodb://musicvideos/genres/"):
                            continue
                        elif Path.startswith("videodb://musicvideos/artists/"):
                            Temp = Path.split("/")
                            KodiItemId = Temp[4]
                            EmbyType = "MusicArtist"
                            ContentType = "video"
                        elif Path.startswith("musicdb://artists/"):
                            Temp = Path.split("/")
                            KodiItemId = Temp[3]
                            EmbyType = "MusicArtist"
                            ContentType = "music"
                        elif Path.startswith("musicdb://albums/"):
                            Temp = Path.split("/")
                            KodiItemId = Temp[3]
                            EmbyType = "MusicAlbum"
                            ContentType = "music"
                        elif Path.startswith("library://music/emby_playlistsaudio_Playlists/"):
                            EmbyType = "Playlist"
                            ContentType = "music"
                            Temp = Path.replace("library://music/emby_playlistsaudio_Playlists/", "").replace(".xml", "").replace("/", "").split("_")
                            ServerId = Temp[0]
                            EmbyId = Temp[1]
                        elif Path.startswith("library://video/emby_playlistsvideo_Playlists/"):
                            EmbyType = "Playlist"
                            ContentType = "video"
                            Temp = Path.replace("library://video/emby_playlistsvideo_Playlists/", "").replace(".xml", "").replace("/", "").split("_")
                            ServerId = Temp[0]
                            EmbyId = Temp[1]

                        ValidImage = ""

                        # get ServerId by thumbnail's metadata
                        if not ServerId and FavoriteChanged.get("thumbnail", "").startswith("http://127.0.0.1:57342/"):
                            ValidImage = FavoriteChanged["thumbnail"]
                            FolderIds = ValidImage.split("/")

                            if len(FolderIds) >= 4:
                                ServerId = FolderIds[4]
                        elif not ServerId and FavoriteChanged.get("thumbnail", "").startswith(("image://emby@dav%3A%2F%2F127.0.0.1%3A57342", "image://epg@dav%3A%2F%2F127.0.0.1%3A57342")):
                            ValidImage = utils.image_url_decode(FavoriteChanged["thumbnail"])
                            FolderIds = ValidImage.split("/")

                            if len(FolderIds) >= 4:
                                ServerId = FolderIds[4]

                        # get additional metadata
                        if not EmbyId or not EmbyType:
                            if KodiItemId == -1:
                                if ValidImage:
                                    MetaIds = ValidImage.split("-")

                                    if len(MetaIds) >= 2:
                                        EmbyId = MetaIds[1] # get EmbyId by thumbnail's metadata

                                        embydb = dbio.DBOpenRO(ServerId, "Favorites change artwork (content)")
                                        EmbyType = embydb.get_contenttype_by_id(EmbyId)
                                        dbio.DBCloseRO(ServerId, "Favorites change artwork (content)")
                            else:
                                if ServerId in utils.EmbyServers:
                                    embydb = dbio.DBOpenRO(ServerId, "Favorites subcontent metadata 1")
                                    EmbyId, KodiItemIdFromDB, ImageUrlFromDB, LibraryIds = embydb.get_EmbyId_KodiId_ImageUrl_by_KodiId_EmbyType(KodiItemId, EmbyType, ContentType)
                                    dbio.DBCloseRO(ServerId, "Favorites subcontent metadata 1")
                                else:
                                    for ServerId in utils.EmbyServers:
                                        embydb = dbio.DBOpenRO(ServerId, "Favorites subcontent metadata 2")
                                        EmbyId, KodiItemIdFromDB, ImageUrlFromDB, LibraryIds = embydb.get_EmbyId_KodiId_ImageUrl_by_KodiId_EmbyType(KodiItemId, EmbyType, ContentType)
                                        dbio.DBCloseRO(ServerId, "Favorites subcontent metadata 2")

                                        if EmbyId:
                                            break
                        else:
                            embydb = dbio.DBOpenRO(ServerId, "Favorites subcontent metadata 3")
                            KodiItemIdFromDB, ImageUrlFromDB = embydb.get_KodiId_ImageUrl_by_EmbyId_EmbyType(EmbyId, EmbyType)
                            dbio.DBCloseRO(ServerId, "Favorites subcontent metadata 3")

                        if not EmbyId:
                            continue

                        if EmbyType not in utils.FavoriteTypes:
                            continue

                        if isAdded:
                            if not isPath and EmbyType == "MusicArtist":
                                ImageUrlUpdated = ImageUrlFromDB or FavoriteChanged["thumbnail"]
                                LibraryIds = common.get_Ids_MultiContent(LibraryIds)
                                KodiItemIds = common.get_Ids_MultiContent(KodiItemIdFromDB)

                                if KodiItemIds[0]:
                                    for Index, KodiItemIdAudio in enumerate(KodiItemIds[0]):
                                        if str(KodiItemId) != KodiItemIdAudio and LibraryIds[0][Index] in utils.EmbyServers[ServerId].library.LibrarySyncedContent and "Playlist" not in utils.EmbyServers[ServerId].library.LibrarySyncedContent[LibraryIds[0][Index]]: # Skip playlist subcontent, and KodiId is self
                                            utils.FavoriteQueue.put((((ImageUrlUpdated or ""), True, f"musicdb://artists/{KodiItemIdAudio}/", FavoriteChanged["title"], "window", 10502),))

                                if KodiItemIds[1]:
                                    for Index, KodiItemIdVideo in enumerate(KodiItemIds[1]):
                                        if str(KodiItemId) != KodiItemIdVideo and LibraryIds[1][Index] in utils.EmbyServers[ServerId].library.LibrarySyncedContent and "Playlist" not in utils.EmbyServers[ServerId].library.LibrarySyncedContent[LibraryIds[1][Index]]: # Skip playlist subcontent
                                            utils.FavoriteQueue.put((((ImageUrlUpdated or ""), True, f"videodb://musicvideos/artists/{KodiItemIdVideo}/", FavoriteChanged["title"], "window", 10025),))

                        else: # favorite removed
                            if not isPath:
                                # remove additional existing favorite records for linked sub-content
                                if EmbyType == "MusicArtist":
                                    KodiItemIds = KodiItemIdFromDB.split(";")

                                    if KodiItemIds[0]:
                                        KodiItemIdsAudio = KodiItemIds[0].split(",")

                                        for KodiItemIdAudio in KodiItemIdsAudio:
                                            delete_favorite(None, FavoritesCurrent, f"musicdb://artists/{KodiItemIdAudio}/")

                                    if KodiItemIds[1]:
                                        KodiItemIdsVideo = KodiItemIds[1].split(",")

                                        for KodiItemIdVideo in KodiItemIdsVideo:
                                            delete_favorite(None, FavoritesCurrent, f"videodb://musicvideos/artists/{KodiItemIdVideo}/")

                        # Update Emby favorites
                        if EmbyId:
                            utils.ItemSkipUpdate.append(str(EmbyId))
                            utils.EmbyServers[ServerId].API.favorite(EmbyId, isAdded)

            FavoritesCached = get_Favorites()

def get_Favorites():
    Result = utils.SendJson("Favourites.GetFavourites", '{"properties":["windowparameter", "path", "thumbnail", "window"]}', False).get("result", {})

    if Result:
        Favorites = Result.get("favourites", [])

        if Favorites: # Favorites can be "None"
            FavoriteData = {"Favorites": Favorites, "Path": len(Favorites) * [""], "Filtered": len(Favorites) * [""], "Title": len(Favorites) * [""], "ImageUrl": len(Favorites) * [""]}

            for Index, Favorite in enumerate(Favorites):
                if 'path' in Favorite:
                    FavoriteData["Path"][Index] = Favorite['path']
                    FavoriteData["Filtered"][Index] = filter_path(Favorite['path'])
                elif 'windowparameter' in Favorite:
                    FavoriteData["Path"][Index] = Favorite['windowparameter']
                    FavoriteData["Filtered"][Index] = filter_path(Favorite['windowparameter'])

                FavoriteData["Title"][Index] = Favorite.get('title', "")
                FavoriteData["ImageUrl"][Index] = Favorite.get('thumbnail', "")

            return FavoriteData

    return {"Favorites": [], "Path": [], "Filtered": [], "Title": [], "ImageUrl": []}

def filter_path(Path):
    PathPos = Path.find("?")

    if PathPos != -1:
        Path = Path[:PathPos]

    return Path

def get_path(Favorite):
    if Favorite:
        if "windowparameter" in Favorite:
            return Favorite["windowparameter"], False

        if "path" in Favorite:
            return Favorite["path"], True

    return "", False

def delete_favorite(Favorite, Favorites, PathCheck):
    _, _, FoundIndex, isValid = get_existing_favorite(Favorite, Favorites, PathCheck)

    if isValid and FoundIndex != -1:
        send_favorite(Favorites["Favorites"][FoundIndex])
        del Favorites["Favorites"][FoundIndex]
        del Favorites["Path"][FoundIndex]
        del Favorites["Filtered"][FoundIndex]
        del Favorites["Title"][FoundIndex]
        del Favorites["ImageUrl"][FoundIndex]

def get_existing_favorite(Favorite, Favorites, PathCheck):
    FoundInPath = False
    FoundInPathFiltered = False
    PathIndex = -1

    if PathCheck:
        Path = PathCheck
    else:
        Path, _ = get_path(Favorite)

    if Path:
        PathFiltered = filter_path(Path)

        if Path in Favorites["Path"]:
            FoundInPath = True
            PathIndex = Favorites["Path"].index(Path)
        elif "?mode=playlist&" not in Path and PathFiltered in Favorites["Filtered"]:
            FoundInPathFiltered = True
            PathIndex = Favorites["Filtered"].index(PathFiltered)

    return FoundInPath, FoundInPathFiltered, PathIndex, bool(Path)

def send_favorite(Favorite, DuringReset=False):
    global FavoriteUpdatedByEmby

    with utils.SafeLock(FavoriteUpdateLock):
        if utils.SystemShutdown and not DuringReset:
            return

        FavoriteUpdatedByEmby = True
        FavoriteTitle = Favorite["title"].replace('"', '\\"')

        if 'path' in Favorite:
            utils.SendJson("Favourites.AddFavourite", f'{{"type":"{Favorite["type"]}", "title":"{FavoriteTitle}", "thumbnail":"{Favorite["thumbnail"]}", "path":"{Favorite["path"]}"}}', False)
        else:
            utils.SendJson("Favourites.AddFavourite", f'{{"type":"{Favorite["type"]}", "title":"{FavoriteTitle}", "thumbnail":"{Favorite["thumbnail"]}", "windowparameter":"{Favorite["windowparameter"]}", "window":"{Favorite["window"]}"}}', False)

def emby_change_Favorite(): # Threaded / queued

    while True:
        utils.sleep(0.5)
        Favorites = utils.FavoriteQueue.getall()

        if "QUIT" in Favorites:
            return

        if not utils.SyncFavorites:
            continue

        FavoritesCurrent = get_Favorites()

        # Filter doubles
        seen = set()
        filtered = [None] * len(Favorites)
        idx = 0

        for fav in reversed(Favorites):
            if fav[2] not in seen:
                seen.add(fav[2])
                filtered[idx] = fav
                idx += 1

        Favorites = filtered[:idx]

        # Updated favorites
        for Favorite in Favorites: # Favorite = (ImageUrl, IsFavorite, FullPath, Title, "media", WindowId)
            FoundInPath, FoundInPathFiltered, FoundIndex, isValid = get_existing_favorite(None, FavoritesCurrent, Favorite[2])

            if not isValid:
                continue

            if Favorite[1]:
                if not FoundInPath and not FoundInPathFiltered: # is favorite and doesn't exist
                    if Favorite[4] == "media":
                        FavoriteNew = {"type": Favorite[4], "title": Favorite[3] , "thumbnail": Favorite[0], "path": Favorite[2]}
                    else:
                        FavoriteNew = {"type": Favorite[4], "title": Favorite[3] , "thumbnail": Favorite[0], "windowparameter": Favorite[2], "window": Favorite[5]}

                    send_favorite(FavoriteNew)
                else: # if favorite exists but title or artwork has changed
                    if FavoritesCurrent["Favorites"][FoundIndex]["title"] != Favorite[3] or FavoritesCurrent["Favorites"][FoundIndex]["thumbnail"] != Favorite[0]:
                        send_favorite(FavoritesCurrent["Favorites"][FoundIndex]) # remove existing favorite record

                        if Favorite[4] == "media":
                            FavoriteNew = {"type": FavoritesCurrent["Favorites"][FoundIndex]['type'], "title": Favorite[3] , "thumbnail": Favorite[0], "path": FavoritesCurrent["Favorites"][FoundIndex]['path']}
                        else:
                            FavoriteNew = {"type": FavoritesCurrent["Favorites"][FoundIndex]['type'], "title": Favorite[3] , "thumbnail": Favorite[0], "windowparameter": FavoritesCurrent["Favorites"][FoundIndex]['windowparameter'], "window": FavoritesCurrent["Favorites"][FoundIndex]['window']}

                        send_favorite(FavoriteNew)
            else:
                if FoundInPath or FoundInPathFiltered: # is not favorite and exist
                    send_favorite(FavoritesCurrent["Favorites"][FoundIndex]) # remove existing favorite record

def clear_reset_favorites(ServerIds):
    Favorites = get_Favorites()
    Mapped = {}
    NativePaths = (
        ("videodb://tvshows/titles/", "Series", "video"),
        ("videodb://movies/sets/", "BoxSet", "video"),
        ("videodb://musicvideos/artists/", "MusicArtist", "video"),
        ("musicdb://artists/", "MusicArtist", "music"),
        ("musicdb://albums/", "MusicAlbum", "music"),
    )

    for Favorite, Path, Image in zip(Favorites["Favorites"], Favorites["Path"], Favorites["ImageUrl"]):
        Path = filter_path(Path)
        if (Path.startswith((utils.AddonModePath, "stack://" + utils.AddonModePath, "plugin://plugin.service.emby-next-gen/", "library://video/emby_", "library://music/emby_"))
                or Image.startswith((utils.AddonModePath, "image://emby@dav%3A%2F%2F127.0.0.1%3A57342", "image://epg@dav%3A%2F%2F127.0.0.1%3A57342"))
                or (Path.startswith((utils.PlaylistPathMusic, utils.PlaylistPathVideo)) and utils.is_emby_playlist(Path.rsplit("/", 1)[-1]))):
            send_favorite({**Favorite, "thumbnail": Image}, DuringReset=True)
            continue

        for Prefix, EmbyType, ContentType in NativePaths:
            if Path.startswith(Prefix):
                KodiId = Path[len(Prefix):].split("/", 1)[0]
                if KodiId.isdecimal():
                    Mapped[Path] = (KodiId, EmbyType, ContentType, {**Favorite, "thumbnail": Image})
                break

    # Native Kodi URLs for Gen albums, artists, series and sets can lack an Emby thumbnail.
    for ServerId in ServerIds:
        if not Mapped:
            break

        try:
            EmbyDB = dbio.DBOpenRO(ServerId, "reset_favorites")
            try:
                for Path, (KodiId, EmbyType, ContentType, Favorite) in list(Mapped.items()):
                    if EmbyDB.get_EmbyId_KodiId_ImageUrl_by_KodiId_EmbyType(KodiId, EmbyType, ContentType)[0]:
                        send_favorite(Favorite, DuringReset=True)
                        del Mapped[Path]
            finally:
                dbio.DBCloseRO(ServerId, "reset_favorites")
        except sqlite3.DatabaseError as Error:
            xbmc.log(f"EMBY.hooks.favorites: Cannot identify native favorites from {ServerId}: {Error}", xbmc.LOGWARNING)


def set_Favorites(Enabled):
    if not Enabled:
        FavoritesCurrent = get_Favorites()

        for Index, ImageUrl in enumerate(FavoritesCurrent["ImageUrl"]):
            if ImageUrl.startswith("http://127.0.0.1:57342/") or ImageUrl.startswith("dav://127.0.0.1:57342/") or ImageUrl.startswith("image://emby@dav%3A%2F%2F127.0.0.1%3A57342") or ImageUrl.startswith("image://epg@dav%3A%2F%2F127.0.0.1%3A57342"):
                send_favorite(FavoritesCurrent["Favorites"][Index])
    else:
        for EmbyServer in list(utils.EmbyServers.values()):
            update_Audio(EmbyServer.library)
            update_MusicAlbum(EmbyServer.library)
            update_Video(EmbyServer.library)
            update_MusicVideo(EmbyServer.library)
            update_Movie(EmbyServer.library)
            update_Episode(EmbyServer.library)
            update_Series(EmbyServer.library)
            update_Season(EmbyServer.library)
            update_Playlist(EmbyServer.library)
            update_BoxSet(EmbyServer.library)
            update_MusicArtist(EmbyServer.library)

def update_Audio(Library):
    embydb = dbio.DBOpenRO(Library.ServerData['ServerId'], "update_Audio")
    AudioInfos = embydb.get_FavoriteInfos("Audio") # EmbyFavourite, KodiId, EmbyId
    dbio.DBCloseRO(Library.ServerData['ServerId'], "update_Audio")
    SQLs = {"music": dbio.DBOpenRO("music", "update_Audio")}
    utils.create_ProgressBar("update_Audio", utils.Translate(33199), utils.Translate(33844))
    AudioObject = audio.Audio(Library, SQLs)
    RecordsPercent = len(AudioInfos) / 100

    for Index, AudioInfo in enumerate(AudioInfos, 1):
        if AudioInfo[0]:
            AudioObject.set_favorite(AudioInfo[0], {"KodiItemId": AudioInfo[1], "Id": AudioInfo[2], "LibraryIds": AudioInfo[3]})

        utils.update_ProgressBar("update_Audio", Index / RecordsPercent, utils.Translate(33844), str(AudioInfo[1]))

    del AudioObject
    dbio.DBCloseRO("music", "update_Audio")
    utils.close_ProgressBar("update_Audio")

def update_MusicAlbum(Library):
    embydb = dbio.DBOpenRO(Library.ServerData['ServerId'], "update_MusicAlbum")
    MusicAlbumInfos = embydb.get_FavoriteInfos("MusicAlbum") # EmbyFavourite, KodiId, EmbyId
    dbio.DBCloseRO(Library.ServerData['ServerId'], "update_MusicAlbum")
    SQLs = {"music": dbio.DBOpenRO("music", "update_MusicAlbum")}
    utils.create_ProgressBar("update_MusicAlbum", utils.Translate(33199), utils.Translate(33845))
    MusicAlbumObject = musicalbum.MusicAlbum(Library, SQLs)
    RecordsPercent = len(MusicAlbumInfos) / 100

    for Index, MusicAlbumInfo in enumerate(MusicAlbumInfos, 1):
        if MusicAlbumInfo[0]:
            MusicAlbumObject.set_favorite(MusicAlbumInfo[0], {"KodiItemId": MusicAlbumInfo[1], "Id": MusicAlbumInfo[2], "LibraryIds": MusicAlbumInfo[3]})

        utils.update_ProgressBar("update_MusicAlbum", Index / RecordsPercent, utils.Translate(33845), str(MusicAlbumInfo[1]))

    del MusicAlbumObject
    dbio.DBCloseRO("music", "update_MusicAlbum")
    utils.close_ProgressBar("update_MusicAlbum")

def update_Video(Library):
    embydb = dbio.DBOpenRO(Library.ServerData['ServerId'], "update_Video")
    VideoInfos = embydb.get_FavoriteInfos("Video") # EmbyFavourite, KodiFileId, KodiId, EmbyId
    dbio.DBCloseRO(Library.ServerData['ServerId'], "update_Video")
    SQLs = {"video": dbio.DBOpenRO("video", "update_Video")}
    utils.create_ProgressBar("update_Video", utils.Translate(33199), utils.Translate(33846))
    VideoObject = videos.Videos(Library, SQLs)
    RecordsPercent = len(VideoInfos) / 100

    for Index, VideoInfo in enumerate(VideoInfos, 1):
        if VideoInfo[0]:
            VideoObject.set_favorite(VideoInfo[0], {"KodiItemId": VideoInfo[2], "Id": VideoInfo[3], "KodiFileId": VideoInfo[1]})

        utils.update_ProgressBar("update_Video", Index / RecordsPercent, utils.Translate(33846), str(VideoInfo[1]))

    del VideoObject
    dbio.DBCloseRO("video", "update_Video")
    utils.close_ProgressBar("update_Video")

def update_MusicVideo(Library):
    embydb = dbio.DBOpenRO(Library.ServerData['ServerId'], "update_MusicVideo")
    MusicVideoInfos = embydb.get_FavoriteInfos("MusicVideo") # EmbyFavourite, KodiFileId, KodiId, EmbyId
    dbio.DBCloseRO(Library.ServerData['ServerId'], "update_MusicVideo")
    SQLs = {"video": dbio.DBOpenRO("video", "update_MusicVideo")}

    utils.create_ProgressBar("update_MusicVideo", utils.Translate(33199), utils.Translate(33847))
    MusicVideoObject = musicvideo.MusicVideo(Library, SQLs)
    RecordsPercent = len(MusicVideoInfos) / 100

    for Index, MusicVideoInfo in enumerate(MusicVideoInfos, 1):
        if MusicVideoInfo[0]:
            MusicVideoObject.set_favorite(MusicVideoInfo[0], {"KodiItemId": MusicVideoInfo[2], "Id": MusicVideoInfo[3], "KodiFileId": MusicVideoInfo[1], "LibraryIds": MusicVideoInfo[4]})

        utils.update_ProgressBar("update_MusicVideo", Index / RecordsPercent, utils.Translate(33847), str(MusicVideoInfo[1]))

    del MusicVideoObject
    dbio.DBCloseRO("video", "update_MusicVideo")
    utils.close_ProgressBar("update_MusicVideo")

def update_BoxSet(Library):
    embydb = dbio.DBOpenRO(Library.ServerData['ServerId'], "update_BoxSet")
    BoxSetInfos = embydb.get_FavoriteInfos("BoxSet") # EmbyFavourite, KodiId, EmbyId
    dbio.DBCloseRO(Library.ServerData['ServerId'], "update_BoxSet")
    SQLs = {"video": dbio.DBOpenRO("video", "update_BoxSet")}
    utils.create_ProgressBar("update_BoxSet", utils.Translate(33199), utils.Translate(33848))
    BoxSetObject = boxsets.BoxSets(Library, SQLs)
    RecordsPercent = len(BoxSetInfos) / 100

    for Index, BoxSetInfo in enumerate(BoxSetInfos, 1):
        if BoxSetInfo[0]:
            BoxSetObject.set_favorite(BoxSetInfo[0], {"KodiItemId": BoxSetInfo[1], "Id": BoxSetInfo[2]})

        utils.update_ProgressBar("update_BoxSet", Index / RecordsPercent, utils.Translate(33848), str(BoxSetInfo[1]))

    del BoxSetObject
    dbio.DBCloseRO("video", "update_BoxSet")
    utils.close_ProgressBar("update_BoxSet")

def update_Series(Library):
    embydb = dbio.DBOpenRO(Library.ServerData['ServerId'], "update_Series")
    SeriesInfos = embydb.get_FavoriteInfos("Series") # EmbyFavourite, KodiId, EmbyId
    dbio.DBCloseRO(Library.ServerData['ServerId'], "update_Series")
    SQLs = {"video": dbio.DBOpenRO("video", "update_Series")}
    utils.create_ProgressBar("update_Series", utils.Translate(33199), utils.Translate(33849))
    SeriesObject = series.Series(Library, SQLs)
    RecordsPercent = len(SeriesInfos) / 100

    for Index, SeriesInfo in enumerate(SeriesInfos, 1):
        if SeriesInfo[0]:
            SeriesObject.set_favorite(SeriesInfo[0], {"KodiItemId": SeriesInfo[1], "Id": SeriesInfo[2]})

        utils.update_ProgressBar("update_Series", Index / RecordsPercent, utils.Translate(33849), str(SeriesInfo[1]))

    del SeriesObject
    dbio.DBCloseRO("video", "update_Series")
    utils.close_ProgressBar("update_Series")

def update_Season(Library):
    embydb = dbio.DBOpenRO(Library.ServerData['ServerId'], "update_Season")
    SeasonInfos = embydb.get_FavoriteInfos("Season") # EmbyFavourite, KodiId, KodiParentId, EmbyId
    dbio.DBCloseRO(Library.ServerData['ServerId'], "update_Season")
    SQLs = {"video": dbio.DBOpenRO("video", "update_Season")}
    utils.create_ProgressBar("update_Season", utils.Translate(33199), utils.Translate(33850))
    SeasonObject = season.Season(Library, SQLs)
    RecordsPercent = len(SeasonInfos) / 100

    for Index, SeasonInfo in enumerate(SeasonInfos, 1):
        if SeasonInfo[0]:
            SeasonObject.set_favorite(SeasonInfo[0], {"KodiItemId": SeasonInfo[1], "Id": SeasonInfo[3], "KodiParentId": SeasonInfo[2]})

        utils.update_ProgressBar("update_Season", Index / RecordsPercent, utils.Translate(33850), str(SeasonInfo[1]))

    del SeasonObject
    dbio.DBCloseRO("video", "update_Season")
    utils.close_ProgressBar("update_Season")

def update_Playlist(Library):
    embydb = dbio.DBOpenRO(Library.ServerData['ServerId'], "update_Playlist")
    Playlists = embydb.get_Records_by_EmbyType("Playlist")
    dbio.DBCloseRO(Library.ServerData['ServerId'], "update_Playlist")
    utils.create_ProgressBar("update_Playlist", utils.Translate(33199), utils.Translate(33851))
    PlaylistObject = playlist.Playlist(Library, {})
    RecordsPercent = len(Playlists) / 100

    for Index, (ItemId, KodiId, IsFavorite, Artwork, LinkedIds, Name) in enumerate(Playlists, 1):
        if IsFavorite:
            PlaylistObject.set_favorite(True, {"Id": ItemId, "KodiItemId": KodiId, "EmbyLinkedId": LinkedIds,
                                               "Name": Name, "KodiArtwork": {"favourite": Artwork or ""}})

        utils.update_ProgressBar("update_Playlist", Index / RecordsPercent, utils.Translate(33851), str(KodiId))

    del PlaylistObject
    utils.close_ProgressBar("update_Playlist")

def update_Episode(Library):
    embydb = dbio.DBOpenRO(Library.ServerData['ServerId'], "update_Episode")
    EpisodeInfos = embydb.get_FavoriteInfos("Episode") # EmbyFavourite, KodiFileId, KodiId, EmbyId
    dbio.DBCloseRO(Library.ServerData['ServerId'], "update_Episode")
    SQLs = {"video": dbio.DBOpenRO("video", "update_Episode")}
    utils.create_ProgressBar("update_Episode", utils.Translate(33199), utils.Translate(33852))
    EpisodeObject = episode.Episode(Library, SQLs)
    RecordsPercent = len(EpisodeInfos) / 100

    for Index, EpisodeInfo in enumerate(EpisodeInfos, 1):
        if EpisodeInfo[0]:
            EpisodeObject.set_favorite(EpisodeInfo[0], {"KodiItemId": EpisodeInfo[1], "Id": EpisodeInfo[3], "KodiFileId": EpisodeInfo[2]})

        utils.update_ProgressBar("update_Episode", Index / RecordsPercent, utils.Translate(33852), str(EpisodeInfo[1]))

    del EpisodeObject
    dbio.DBCloseRO("video", "update_Episode")
    utils.close_ProgressBar("update_Episode")

def update_Movie(Library):
    embydb = dbio.DBOpenRO(Library.ServerData['ServerId'], "update_Movie")
    MoviesInfos = embydb.get_FavoriteInfos("Movie") # EmbyFavourite, KodiFileId, KodiId, EmbyId
    dbio.DBCloseRO(Library.ServerData['ServerId'], "update_Movie")
    SQLs = {"video": dbio.DBOpenRO("video", "update_Movie")}
    utils.create_ProgressBar("update_Movie", utils.Translate(33199), utils.Translate(33853))
    MovieObject = movies.Movies(Library, SQLs)
    RecordsPercent = len(MoviesInfos) / 100

    for Index, MovieInfo in enumerate(MoviesInfos, 1):
        if MovieInfo[0]:
            MovieObject.set_favorite(MovieInfo[0], {"KodiItemId": MovieInfo[1], "Id": MovieInfo[3], "KodiFileId": MovieInfo[2]})

        utils.update_ProgressBar("update_Movie", Index / RecordsPercent, utils.Translate(33853), str(MovieInfo[1]))

    del MovieObject
    dbio.DBCloseRO("video", "update_Movie")
    utils.close_ProgressBar("update_Movie")


def update_MusicArtist(Library):
    embydb = dbio.DBOpenRO(Library.ServerData['ServerId'], "update_MusicArtist")
    MusicArtistInfos = embydb.get_FavoriteInfos("MusicArtist") # EmbyFavourite, KodiId, EmbyId
    dbio.DBCloseRO(Library.ServerData['ServerId'], "update_MusicArtist")
    SQLs = {"music": dbio.DBOpenRO("music", "update_MusicArtist"), "video": dbio.DBOpenRO("video", "update_MusicArtist")}
    utils.create_ProgressBar("update_MusicArtist", utils.Translate(33199), utils.Translate(33859))
    MusicArtistObject = musicartist.MusicArtist(Library, SQLs)
    RecordsPercent = len(MusicArtistInfos) / 100

    for Index, MusicArtistInfo in enumerate(MusicArtistInfos, 1):
        if MusicArtistInfo[0]:
            MusicArtistObject.set_favorite(MusicArtistInfo[0], {"KodiItemId": MusicArtistInfo[1], "Id": MusicArtistInfo[2], "LibraryIds": MusicArtistInfo[3]})

        utils.update_ProgressBar("update_MusicArtist", Index / RecordsPercent, utils.Translate(33859), str(MusicArtistInfo[1]))

    dbio.DBCloseRO("music", "update_MusicArtist")
    dbio.DBCloseRO("video", "update_MusicArtist")
    del MusicArtistObject
    utils.close_ProgressBar("update_MusicArtist")
