from pathlib import Path
import re
import shutil
import threading
import uuid
from urllib.parse import quote, urlencode
import xbmcvfs
import xbmc
import xbmcgui
import xbmcplugin
from database import dbio
from emby import listitem, views
from hooks import favorites
from . import utils, xmls, cache

LibraryMenu = {"LibraryAdd": utils.Translate(33154), "LibraryRemove": utils.Translate(33184), "LibraryUpdate": utils.Translate(33139), "LibraryRepair": utils.Translate(33140), "RefreshBoxsets": utils.Translate(33098)}
ResetLock = threading.Lock()

# Build plugin menu
def listing(Handle, ServerId="", Media=""):
    Handle = int(Handle)
    ItemsListings = [[], []]
    for Id, Server in list(utils.EmbyServers.items()):
        if ServerId:
            if Id == ServerId:
                for Label, Path, Icon in Server.Views.NodesSynced:
                    if not Media or Path.startswith(f"library://{Media}/"):
                        add_ListItem(ItemsListings, Label, Path, Icon, "")
        elif Server.Views.NodesSynced:
            Params = urlencode({"mode": "syncednodes", "server": Id, "media": Media})
            Label = f"{utils.Translate(33386)} ({Server.ServerData['ServerName']})"
            add_ListItem(ItemsListings, Label, views.PLUGIN_PATH + Params, "DefaultHardDisk.png", "")

    xbmcplugin.addDirectoryItems(Handle, ItemsListings[0], len(ItemsListings[0]))
    xbmcplugin.addSortMethod(Handle, xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.endOfDirectory(Handle, cacheToDisc=False, updateListing=False)

# Add or remove users from the default server session
def AddUser(EmbyServer):
    session = EmbyServer.API.get_device()
    AllUsers = EmbyServer.API.get_users()

    if not AllUsers:
        return

    AddUserChoices = []

    for AllUser in AllUsers:
        if AllUser['Id'] != session[0]['UserId']:
            UserExists = False

            for SessionAdditionalUser in session[0]['AdditionalUsers']:
                if SessionAdditionalUser['UserId'] == AllUser['Id']:
                    UserExists = True
                    break

            if not UserExists:
                AddUserChoices.append({'UserName': AllUser['Name'], 'UserId': AllUser['Id']})

    RemoveUserChoices = []

    for SessionAdditionalUser in session[0]['AdditionalUsers']:
        RemoveUserChoices.append({'UserName': SessionAdditionalUser['UserName'], 'UserId': SessionAdditionalUser['UserId']})

    result = utils.Dialog.select(utils.Translate(33061), [utils.Translate(33062), utils.Translate(33063)] if RemoveUserChoices else [utils.Translate(33062)])

    if result < 0:
        return

    if not result:  # Add user
        AddNameArray = []

        for AddUserChoice in AddUserChoices:
            AddNameArray.append(AddUserChoice['UserName'])

        resp = utils.Dialog.select(utils.Translate(33054), AddNameArray)

        if resp < 0:
            return

        UserData = AddUserChoices[resp]
        EmbyServer.add_AdditionalUser(UserData['UserId'], UserData['UserName'])
        utils.Dialog.notification(heading=utils.addon_name, message=f"{utils.Translate(33067)} {UserData['UserName']}", icon=utils.icon, time=utils.displayMessage, sound=False)
    else:  # Remove user
        RemoveNameArray = []

        for RemoveUserChoice in RemoveUserChoices:
            RemoveNameArray.append(RemoveUserChoice['UserName'])

        resp = utils.Dialog.select(utils.Translate(33064), RemoveNameArray)

        if resp < 0:
            return

        UserData = RemoveUserChoices[resp]
        EmbyServer.remove_AdditionalUser(UserData['UserId'])
        utils.Dialog.notification(heading=utils.addon_name, message=f"{utils.Translate(33066)} {UserData['UserName']}", icon=utils.icon, time=utils.displayMessage, sound=False)

def add_ItemsListings(ItemsListings, Item, ServerId):
    Item['CacheId'] = f"{Item.get('Id', str(uuid.uuid4()).replace('-', ''))};{ServerId}" # Generated Kodi folder entries may not carry an Emby ID.
    ItemsListings[0].append((Item['KodiFullPath'], Item['ListItem'], Item['IsFolder']))
    ItemsListings[1].append(Item['CacheId'])

    if ServerId:
        cache.add_Item(Item, ServerId)

# Menu structure nodes
def add_ListItem(ItemsListings, Label, Path, Artwork, HelpText):
    UID = str(uuid.uuid4()).replace("-", "")
    Item = {'Id': UID, 'IsFolder': True, 'KodiFullPath': Path, 'ListItem': xbmcgui.ListItem(Label, HelpText, Path, True)}
    Item['ListItem'].setContentLookup(False)
    Item['ListItem'].setProperties({'IsFolder': 'true', 'IsPlayable': 'false'})
    Item['ListItem'].setArt({"thumb": Artwork, "fanart": "special://home/addons/plugin.service.emby-next-gen/resources/fanart.jpg", "landscape": Artwork or "special://home/addons/plugin.service.emby-next-gen/resources/fanart.jpg", "clearlogo": "special://home/addons/plugin.service.emby-next-gen/resources/clearlogo.png", "icon": Artwork})
    add_ItemsListings(ItemsListings, Item, UID)

def get_EmbyServerList():
    ServerIds = []
    ServerItems = []

    for ServerId, EmbyServer in list(utils.EmbyServers.items()):
        ServerIds.append(ServerId)
        ServerItems.append(EmbyServer.ServerData['ServerName'])

    return len(utils.EmbyServers), ServerIds, ServerItems

def select_managelibs():  # threaded by monitor.py
    EmbyServersCounter, _, ServerItems = get_EmbyServerList()

    if EmbyServersCounter > 1:
        Selection = utils.Dialog.select(utils.Translate(33431), ServerItems)

        if Selection > -1:
            manage_libraries(Selection)
    else:
        if EmbyServersCounter > 0:
            manage_libraries(0)

def manage_servers(ServerConnect):  # threaded by caller
    Selection = utils.Dialog.select(utils.Translate(33648), [utils.Translate(33134), utils.Translate(33141), utils.Translate(33062)]) # Manage libraries

    if Selection == 0:
        ServerConnect(None)
    elif Selection == 1:
        _, ServerIds, ServerItems = get_EmbyServerList()
        Selection = utils.Dialog.select(utils.Translate(33431), ServerItems)

        if Selection > -1:
            utils.EmbyServers[ServerIds[Selection]].ServerData['ServerRemoved'] = True
            utils.close_dialog(10146) # addoninformation
            utils.Dialog.notification(heading=utils.addon_name, message=f"{utils.Translate(33448)}: {utils.EmbyServers[ServerIds[Selection]].ServerData['ServerName']}", icon=utils.icon, time=utils.displayMessage, sound=False)
            SQLs = {}
            dbio.DBOpenRW(ServerIds[Selection], "remove_emby_server", SQLs)

            for LibrarySyncedId in utils.EmbyServers[ServerIds[Selection]].library.LibrarySyncedNames:
                SQLs["emby"].add_remove_library_items(LibrarySyncedId)
                SQLs["emby"].add_RemoveItem("library", LibrarySyncedId)

            SQLs["emby"].add_RemoveItem("library", "999999999")
            SQLs["emby"].add_remove_library_items_person()
            dbio.DBCloseRW(ServerIds[Selection], "remove_emby_server", SQLs)
            utils.update_SyncPause(utils.EmbyServers[ServerIds[Selection]].library.ServerDatabaseInitId, False)
            utils.EmbyServers[ServerIds[Selection]].library.RunJobs(False, False)

            for LibraryId in utils.EmbyServers[ServerIds[Selection]].Views.ViewItems:
                utils.EmbyServers[ServerIds[Selection]].Views.delete_node_by_id(LibraryId)

            utils.EmbyServers[ServerIds[Selection]].Views.delete_root_nodes()
            utils.EmbyServers[ServerIds[Selection]].ServerDisconnect()
    elif Selection == 2:
        _, ServerIds, ServerItems = get_EmbyServerList()
        Selection = utils.Dialog.select(utils.Translate(33431), ServerItems)

        if Selection > -1:
            AddUser(utils.EmbyServers[ServerIds[Selection]])

def manage_libraries(ServerSelection):  # threaded by caller
    ServerIds = list(utils.EmbyServers)
    EmbyServerId = ServerIds[ServerSelection]

    while True:
        SelectionMenu = ([], [])

        for Id, Text in list(LibraryMenu.items()):

            SelectionMenu[0].append(Id)
            SelectionMenu[1].append(Text)

        Selection = utils.Dialog.select(utils.Translate(33194), SelectionMenu[1]) # Manage libraries

        if Selection == -1:
            return

        if SelectionMenu[0][Selection] == "LibraryAdd":
            utils.EmbyServers[EmbyServerId].library.select_libraries("AddLibrarySelection")
        elif SelectionMenu[0][Selection] == "LibraryRemove":
            utils.EmbyServers[EmbyServerId].library.select_libraries("RemoveLibrarySelection")
        elif SelectionMenu[0][Selection] == "LibraryUpdate":
            utils.EmbyServers[EmbyServerId].library.select_libraries("UpdateLibrarySelection")
        elif SelectionMenu[0][Selection] == "LibraryRepair":
            utils.EmbyServers[EmbyServerId].library.select_libraries("RepairLibrarySelection")
        elif SelectionMenu[0][Selection] == "RefreshBoxsets":
            utils.EmbyServers[EmbyServerId].library.refresh_boxsets()

# Special favorite synced node
def favepisodes(Handle):
    Handle = int(Handle)
    ItemsListings = [[], []]
    KodiIdEpisodes = []
    KodiItems = []
    ServerId = ""

    if not wait_Emby(Handle):
        return

    for ServerId in utils.EmbyServers:
        embydb = dbio.DBOpenRO(ServerId, "favepisodes")
        KodiIdEpisodes = embydb.get_episode_fav()
        dbio.DBCloseRO(ServerId, "favepisodes")
        videodb = dbio.DBOpenRO("video", "favepisodes")

        for episode_kodiId in KodiIdEpisodes:
            KodiItems.append(videodb.get_episode_metadata_for_listitem(episode_kodiId[0], None))
            KodiItems[-1]["ServerId"] = ServerId

        dbio.DBCloseRO("video", "favepisodes")

    for ReleaseCounter, KodiItem in enumerate(KodiItems, 1):
        if ReleaseCounter % 50 == 0:
            xbmc.sleep(0)

        if KodiItem:
            listitem.set_ListItem_from_Kodi_database(KodiItem, "")
            add_ItemsListings(ItemsListings, KodiItem, ServerId)

    xbmcplugin.addDirectoryItems(Handle, ItemsListings[0], len(ItemsListings[0]))
    xbmcplugin.addSortMethod(Handle, xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.addSortMethod(Handle, xbmcplugin.SORT_METHOD_TITLE)
    xbmcplugin.setContent(Handle, 'episodes')
    xbmcplugin.endOfDirectory(Handle, cacheToDisc=False, updateListing=False)

def favseasons(Handle):
    Handle = int(Handle)
    ItemsListings = [[], []]
    KodiItems = []
    ServerId = ""

    if not wait_Emby(Handle):
        return

    for ServerId in utils.EmbyServers:
        embydb = dbio.DBOpenRO(ServerId, "favseasons")
        KodiIdSeasons = embydb.get_season_fav()
        dbio.DBCloseRO(ServerId, "favseasons")
        videodb = dbio.DBOpenRO("video", "favseasons")

        for season_kodiId in KodiIdSeasons:
            KodiItems.append(videodb.get_season_metadata_for_listitem(season_kodiId[0]))
            KodiItems[-1]['ServerId'] = ServerId

        dbio.DBCloseRO("video", "favseasons")

    for ReleaseCounter, KodiItem in enumerate(KodiItems, 1):
        if ReleaseCounter % 50 == 0:
            xbmc.sleep(0)

        if KodiItem:
            listitem.set_ListItem_from_Kodi_database(KodiItem, "")
            add_ItemsListings(ItemsListings, KodiItem, ServerId)

    xbmcplugin.addDirectoryItems(Handle, ItemsListings[0], len(ItemsListings[0]))
    xbmcplugin.addSortMethod(Handle, xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.addSortMethod(Handle, xbmcplugin.SORT_METHOD_TITLE)
    xbmcplugin.setContent(Handle, 'tvshows')
    xbmcplugin.endOfDirectory(Handle, cacheToDisc=False, updateListing=False)

# Special collection synced node

# This method will sync all Kodi artwork to textures13.db and cache them locally. This takes diskspace!


def get_next_episodes(Handle, libraryname):
    Handle = int(Handle)
    ItemsListings = [[], []]
    KodiItems = []
    videodb = dbio.DBOpenRO("video", "get_next_episodes")
    NextEpisodeInfos = videodb.get_next_episodesIds(libraryname)

    for ReleaseCounter, NextEpisodeInfo in enumerate(NextEpisodeInfos, 1):
        if ReleaseCounter % 50 == 0:
            xbmc.sleep(0)

        EpisodeId = NextEpisodeInfo.split(";")
        KodiItems.append(videodb.get_episode_metadata_for_listitem(EpisodeId[1], None))

    dbio.DBCloseRO("video", "get_next_episodes")

    for KodiItem in KodiItems:
        if KodiItem:
            listitem.set_ListItem_from_Kodi_database(KodiItem, "")
            add_ItemsListings(ItemsListings, KodiItem, "")

    xbmcplugin.addDirectoryItems(Handle, ItemsListings[0], len(ItemsListings[0]))
    xbmcplugin.addSortMethod(Handle, xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.setContent(Handle, 'episodes')
    xbmcplugin.endOfDirectory(Handle, cacheToDisc=False, updateListing=False)

def get_next_episodes_played(Handle, libraryname):
    Handle = int(Handle)
    ItemsListings = [[], []]
    KodiItems = []
    videodb = dbio.DBOpenRO("video", "get_next_episodes")
    NextEpisodeInfos = videodb.get_last_played_next_episodesIds(libraryname)

    for ReleaseCounter, NextEpisodeInfo in enumerate(NextEpisodeInfos, 1):
        if ReleaseCounter % 50 == 0:
            xbmc.sleep(0)

        EpisodeId = NextEpisodeInfo.split(";")
        KodiItems.append(videodb.get_episode_metadata_for_listitem(EpisodeId[1], None))

    dbio.DBCloseRO("video", "get_next_episodes")

    for KodiItem in KodiItems:
        if KodiItem:
            listitem.set_ListItem_from_Kodi_database(KodiItem, "")
            add_ItemsListings(ItemsListings, KodiItem, "")

    xbmcplugin.addDirectoryItems(Handle, ItemsListings[0], len(ItemsListings[0]))
    xbmcplugin.addSortMethod(Handle, xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.setContent(Handle, 'episodes')
    xbmcplugin.endOfDirectory(Handle, cacheToDisc=False, updateListing=False)

def get_playlist(Handle, ServerId, MediaType, Id, PlaylistId=""):
    Handle = int(Handle)

    if not wait_Emby(Handle):
        return

    if ServerId not in utils.EmbyServers:
        xbmcplugin.endOfDirectory(Handle, succeeded=False, cacheToDisc=False, updateListing=False)
        return

    ItemsListings = [[], []]
    embydb = dbio.DBOpenRO(ServerId, "playlist")

    if PlaylistId:
        Record = embydb.get_item_by_id(PlaylistId, "Playlist") if PlaylistId.isdecimal() and MediaType == "video" else None
        if Record:
            videodb = dbio.DBOpenRO("video", "playlist")
            try:
                add_synced_playlist_videos(ItemsListings, Record[4], embydb, videodb)
            finally:
                dbio.DBCloseRO("video", "playlist")
    elif not Id:
        Playlists = embydb.get_Records_by_EmbyType("Playlist")

        for Playlist in Playlists:
            KodiPlaylistIds = Playlist[1].split(";")
            PlaylistName = ""
            Path = ""

            if MediaType == "audio":
                if KodiPlaylistIds[0] and KodiPlaylistIds[0].endswith("_audio"):
                    Path = views.PLUGIN_PATH + urlencode({"mode": "playlist", "mediatype": MediaType, "server": ServerId, "id": KodiPlaylistIds[0]})
                    PlaylistName = KodiPlaylistIds[0].replace("emby_", "").replace("_audio", "", 1).replace("_", " ")
            else:
                if KodiPlaylistIds[1] and KodiPlaylistIds[1].endswith("_video"):
                    Path = views.PLUGIN_PATH + urlencode({"mode": "playlist", "mediatype": MediaType, "server": ServerId, "id": KodiPlaylistIds[1]})
                    PlaylistName = KodiPlaylistIds[1].replace("emby_", "").replace("_video", "", 1).replace("_", " ")

            if not PlaylistName:
                continue

            add_ListItem(ItemsListings, PlaylistName, Path, Playlist[3], "")
    else:
        if MediaType == "audio":
            PlaylistData = utils.readFileString(f"{utils.PlaylistPathMusic}{Id}.m3u")
            musicdb = dbio.DBOpenRO("music", "playlist")
        else:
            PlaylistData = utils.readFileString(f"{utils.PlaylistPathVideo}{Id}.m3u")
            videodb = dbio.DBOpenRO("video", "playlist")

        # Get EmbyIds from m3u
        KodiItems = ()
        PlaylistRecords = PlaylistData.split("#EXTINF:")

        for ReleaseCounter, PlaylistRecord in enumerate(PlaylistRecords[1:], 1):
            if ReleaseCounter % 50 == 0:
                xbmc.sleep(0) # release GIL

            if PlaylistRecord:
                Data = PlaylistRecord.split("\n")[1].split("/")

                if MediaType == "audio":
                    Data = Data[len(Data) - 1]
                    Data = Data.split("-")
                    EmbyId = Data[1]
                    KodiId = embydb.get_KodiId_by_EmbyId_EmbyType(EmbyId, "Audio")
                    KodiItems += (musicdb.get_song_metadata_for_listitem(KodiId),)
                else:
                    if len(Data) < 8:
                        xbmc.log("EMBY.helper.pluginmenu: Unknown content in an Emby playlist", xbmc.LOGWARNING)
                        continue

                    EmbyId = Data[7]
                    LibraryId = Data[5]
                    Data = Data[len(Data) - 2]
                    Data = Data.split("-")

                    if Data[0] == "M":
                        KodiIds, LibraryIds = embydb.get_KodiId_LibraryId_by_EmbyId_EmbyType(EmbyId, "MusicVideo")
                        KodiIds = KodiIds.split(",")
                        LibraryIds = LibraryIds.split(",")
                        Index = LibraryIds.index(LibraryId)
                        KodiItems += (videodb.get_musicvideos_metadata_for_listitem(KodiIds[Index], ""),)
                    elif Data[0] == "m":
                        KodiId = embydb.get_KodiId_by_EmbyId_EmbyType(EmbyId, "Movie")
                        KodiItems += (videodb.get_movie_metadata_for_listitem(KodiId, ""),)
                    elif Data[0] == "e":
                        KodiId = embydb.get_KodiId_by_EmbyId_EmbyType(EmbyId, "Episode")
                        KodiItems += (videodb.get_episode_metadata_for_listitem(KodiId, ""),)
                    elif Data[0] == "v":
                        KodiId = embydb.get_KodiId_by_EmbyId_EmbyType(EmbyId, "Video")
                        KodiItems += (videodb.get_movie_metadata_for_listitem(KodiId, ""),)

        if MediaType == "audio":
            dbio.DBCloseRO("music", "playlist")
        else:
            dbio.DBCloseRO("video", "playlist")

        for KodiItem in KodiItems:
            if KodiItem:
                listitem.set_ListItem_from_Kodi_database(KodiItem, "")
                add_ItemsListings(ItemsListings, KodiItem, "")

    dbio.DBCloseRO(ServerId, "playlist")

    if ItemsListings:
        xbmcplugin.addDirectoryItems(Handle, ItemsListings[0], len(ItemsListings[0]))

        if Id or PlaylistId:
            xbmcplugin.addSortMethod(Handle, xbmcplugin.SORT_METHOD_UNSORTED)
        else:
            xbmcplugin.addSortMethod(Handle, xbmcplugin.SORT_METHOD_LABEL)

        if MediaType == "audio":
            xbmcplugin.setContent(Handle, 'songs')
        else:
            xbmcplugin.setContent(Handle, 'videos')

    xbmcplugin.endOfDirectory(Handle, cacheToDisc=False, updateListing=False)

def add_synced_playlist_videos(ItemsListings, LinkedIds, EmbyDB, VideoDB):
    VideoTypes = (
        ("Video", VideoDB.get_movie_metadata_for_listitem),
        ("Movie", VideoDB.get_movie_metadata_for_listitem),
        ("Episode", VideoDB.get_episode_metadata_for_listitem),
        ("MusicVideo", VideoDB.get_musicvideos_metadata_for_listitem),
    )
    for (MediaType, GetMetadata), Group in zip(VideoTypes, (LinkedIds or "").split(";")[1:]):
        for EmbyId in filter(None, Group.split(",")):
            KodiId = EmbyDB.get_KodiId_by_EmbyId_EmbyType(EmbyId, MediaType)
            if not KodiId:
                continue
            if MediaType == "MusicVideo":
                KodiId = KodiId.split(",")[0]
            KodiItem = GetMetadata(KodiId, "")
            if KodiItem:
                listitem.set_ListItem_from_Kodi_database(KodiItem, "")
                add_ItemsListings(ItemsListings, KodiItem, "")

def get_recentlyadded_musicvideosalbums(Handle, LibraryName):
    Handle = int(Handle)
    videodb = dbio.DBOpenRO("video", "get_recentlyadded_musicvideosalbums")
    KodiItems = videodb.get_musicvideos_recentlyadded_albums(LibraryName)
    ItemsListings = [[], []]

    for KodiItem in KodiItems:
        Path = f"videodb://musicvideos/titles/?artistid={KodiItem[0]}&xsp=" + quote(f'{{"rules":{{"and":[{{"field":"album","operator":"is","value":["{KodiItem[1]}"]}}]}},"type":"musicvideos"}}')
        Artwork = videodb.common_db.get_artwork(KodiItem[3], "musicvideo", "")
        People = videodb.get_people_artwork(KodiItem[3], "musicvideo")
        MetaData = {'KodiMetadataMediatype': "musicvideo", 'KodiMetadataDBID': KodiItem[3], 'KodiMetadataPathandfilename': Path, 'KodiMetadataTitle': f"{KodiItem[2]} - {KodiItem[1]}", 'KodiMetadataProperties': {'IsFolder': 'true', 'IsPlayable': 'false'}, 'KodiMetadataArtwork': Artwork, 'KodiMetadataPeople': People, 'KodiMetadataAlbum': KodiItem[1], "KodiMetadataAlbumartists": [KodiItem[2]]}
        listitem.set_ListItem_from_Kodi_database(MetaData, "")
        add_ItemsListings(ItemsListings, MetaData, "")

    dbio.DBCloseRO("video", "get_recentlyadded_musicvideosalbums")
    xbmcplugin.addDirectoryItems(Handle, ItemsListings[0], len(ItemsListings[0]))
    xbmcplugin.addSortMethod(Handle, xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.setContent(Handle, 'musicvideos')
    xbmcplugin.endOfDirectory(Handle, cacheToDisc=False, updateListing=False)

def get_inprogress_mixed(Handle):
    Handle = int(Handle)
    ItemsListings = [[], []]
    KodiItems = []
    videodb = dbio.DBOpenRO("video", "get_inprogress_mixed")
    InProgressInfos = videodb.get_inprogress_mixedIds()

    for ReleaseCounter, InProgressInfo in enumerate(InProgressInfos, 1):
        if ReleaseCounter % 50 == 0:
            xbmc.sleep(0)

        KodiItem = InProgressInfo.split(";")

        if len(KodiItem) == 3:
            if KodiItem[2] == "Movie":
                KodiItems.append(videodb.get_movie_metadata_for_listitem(KodiItem[1], None))
            elif KodiItem[2] == "Episode":
                KodiItems.append(videodb.get_episode_metadata_for_listitem(KodiItem[1], None))
            elif KodiItem[2] == "MusicVideo":
                KodiItems.append(videodb.get_musicvideos_metadata_for_listitem(KodiItem[1], None))

    dbio.DBCloseRO("video", "get_inprogress_mixed")

    for KodiItem in KodiItems:
        if KodiItem:
            listitem.set_ListItem_from_Kodi_database(KodiItem, "")
            add_ItemsListings(ItemsListings, KodiItem, "")

    xbmcplugin.addDirectoryItems(Handle, ItemsListings[0], len(ItemsListings[0]))
    xbmcplugin.addSortMethod(Handle, xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.setContent(Handle, 'videos')
    xbmcplugin.endOfDirectory(Handle, cacheToDisc=False, updateListing=False)


def factoryreset(Reason=""):
    with utils.SafeLock(ResetLock):
        if utils.SystemShutdown:
            return

        Message = f"{Reason}\n\n{utils.Translate(33074)}" if Reason else utils.Translate(33074)
        if not utils.Dialog.yesno(heading=utils.addon_name, message=Message):
            return

        try:
            reset_all()
        except Exception as Error:
            xbmc.log(f"EMBY.helper.pluginmenu: Factory reset failed: {Error}", xbmc.LOGERROR)
            utils.Dialog.ok(heading=utils.addon_name, message=utils.Translate(33903))

        if utils.SystemShutdown:
            utils.restart_kodi()


def reset_all():
    Player = xbmc.Player()
    if Player.isPlaying():
        Player.stop()
        for _ in range(50):
            if not Player.isPlaying():
                break
            if utils.sleep(0.1):
                return
        else:
            raise RuntimeError("Playback did not stop")

    utils.close_dialog(10140) # addonsettings
    utils.close_dialog(10146) # addoninformation
    utils.Dialog.notification(heading=utils.addon_name, message=utils.Translate(33223), icon=utils.icon, time=960000, sound=True)
    xmls.reset_configuration()

    Servers = list(utils.EmbyServers.values())
    utils.update_SyncPause("factoryreset", True)
    utils.SystemShutdown = True
    for Server in Servers:
        Server.stop()

    # Wait for sync writes to finish before removing their databases and generated files.
    for Server in Servers:
        with utils.SafeLock(Server.library.LockDBRWOpen):
            pass

    _, Files = xbmcvfs.listdir("special://profile/Database/")
    EmbyDatabases = [Name for Name in Files if re.fullmatch(r"emby_.+\.db(?:-wal|-shm|-journal)?", Name)]
    ServerIds = []
    for Name in EmbyDatabases:
        if Name.endswith(".db"):
            ServerId = Name[5:-3]
            utils.DatabaseFiles[ServerId] = xbmcvfs.translatePath(f"special://profile/Database/{Name}")
            ServerIds.append(ServerId)

    favorites.clear_reset_favorites(ServerIds)
    utils.delete_nodes()
    utils.delete_playlists()
    clear_media_databases()

    for Name in EmbyDatabases:
        DatabasePath = f"special://profile/Database/{Name}"
        if xbmcvfs.exists(DatabasePath) and not xbmcvfs.delete(DatabasePath):
            raise OSError(f"Cannot remove {DatabasePath}")

    delete_thumbnail_cache()
    utils.delFolder(utils.FolderAddonUserdata)
    if xbmcvfs.exists(utils.FolderAddonUserdata):
        raise OSError("Cannot remove the Emby add-on data directory")

    # Kodi reads these settings during startup, before the connection wizard runs.
    xmls.sources()
    xmls.advanced_settings(utils.DEFAULT_CURL_TIMEOUT)


def clear_media_databases():
    SQLs = {}
    for DbId in ("video", "music"):
        dbio.DBOpenRW(DbId, "factoryreset", SQLs)
        try:
            Database = SQLs[DbId].common_db
            with Database.cursor.connection:
                Database.delete_tables(DbId.capitalize())
        finally:
            dbio.DBCloseRW(DbId, "factoryreset", SQLs)


def clear_image_cache():
    with utils.SafeLock(ResetLock):
        if utils.SystemShutdown or not utils.Dialog.yesno(heading=utils.addon_name, message=utils.Translate(33086)):
            return

        utils.close_dialog(10146) # addoninformation
        try:
            delete_thumbnail_cache()
        except Exception as Error:
            xbmc.log(f"EMBY.helper.pluginmenu: Clearing the Kodi image cache failed: {Error}", xbmc.LOGERROR)
            utils.Dialog.ok(heading=utils.addon_name, message=utils.Translate(33903))
        else:
            utils.Dialog.notification(heading=utils.addon_name, message=utils.Translate(33904), icon=utils.icon, time=utils.displayMessage, sound=False)


def delete_thumbnail_cache():
    Directory = Path(xbmcvfs.translatePath("special://thumbnails/"))
    if not Directory.is_absolute() or Directory.is_symlink() or Directory.resolve().name.casefold() != "thumbnails":
        raise ValueError(f"Unexpected thumbnail directory: {Directory}")

    Directory = Directory.resolve()
    utils.create_ProgressBar("ClearImageCache", utils.Translate(33199), utils.Translate(33412))

    try:
        with utils.SafeLock(utils.ArtworkDeleteLock):
            SQLs = {}
            if utils.DatabaseFiles["texture"] and xbmcvfs.exists(utils.DatabaseFiles["texture"]):
                dbio.DBOpenRW("texture", "ClearImageCache", SQLs)

            try:
                if Directory.is_dir():
                    shutil.rmtree(Directory)
                Directory.mkdir(parents=True, exist_ok=True)

                if SQLs:
                    TextureDB = SQLs["texture"]
                    with TextureDB.cursor.connection:
                        TextureDB.clear_cache()

                utils.ArtworkDelete.clear()
            finally:
                if SQLs:
                    dbio.DBCloseRW("texture", "ClearImageCache", SQLs)
    finally:
        utils.close_ProgressBar("ClearImageCache")


# Wait for Emby server
def wait_Emby(Handle):
    while True:
        if utils.SystemShutdown:

            if Handle != -1:
                xbmcplugin.endOfDirectory(Handle, succeeded=False, cacheToDisc=False, updateListing=False)

            return False

        if utils.NextGenOnline.wait(timeout=0.1):
            return True
