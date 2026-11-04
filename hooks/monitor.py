import json
import threading
import xbmcvfs
import xbmc
from helper import pluginmenu, utils, xmls, player, queue, cache, artworkcache
from database import dbio
from emby import emby, httpcache
from . import webservice, favorites

FullShutdown = False
utils.FavoriteQueue = queue.Queue()
syncEmbyLock = threading.Lock()
SettingsChangedEvent = threading.Event()
SystemEventsQueue = queue.Queue()
SystemScansQueue = queue.Queue()

class monitor(xbmc.Monitor):
    def onNotification(self, _sender, method, data):
        if method.startswith(("Player.", "Playlist.")):
            try:
                Event = json.loads(data) if data else {}
            except (TypeError, ValueError):
                Event = {}

            if (Event.get('player', {}).get('playerid') == 2
                    or Event.get('playlistid') == 2
                    or Event.get('item', {}).get('type') == 'picture'):
                return

        if method == "Player.OnPlay":
            player.PlayerEventsQueue.put((("play", data),))
        elif method == "Player.OnStop":
            Item = Event.get('item', {})
            if Item.get('type') == 'episode' and Item.get('id'):
                webservice.release_cancelled_episode(Item['id'])
            player.PlayerEventsQueue.put((("stop", data),))
        elif method == 'Player.OnSeek':
            player.PlayerEventsQueue.put((("seek", data),))
        elif method == "Player.OnAVChange":
            player.PlayerEventsQueue.put((("avchange", data),))
        elif method == "Player.OnAVStart":
            player.PlayerEventsQueue.put((("avstart", data),))
        elif method == "Player.OnPause":
            player.PlayerEventsQueue.put((("pause",),))
        elif method == "Player.OnResume":
            player.PlayerEventsQueue.put((("resume",),))
        elif method == "Player.OnPropertyChanged":
            player.PlayerEventsQueue.put((("propertychanged", data),))
        elif method == "Player.OnSpeedChanged":
            player.PlayerEventsQueue.put((("speedchanged", data),))
        elif method == 'Application.OnVolumeChanged':
            player.PlayerEventsQueue.put((("volume", data),))
        elif method == "Playlist.OnAdd":
            player.PlayerEventsQueue.put((("add", data),))
        elif method == "Playlist.OnRemove":
            player.PlayerEventsQueue.put((("remove", data),))
        elif method == "Playlist.OnClear":
            player.PlayerEventsQueue.put((("clear", data),))
        else:
            SystemEventsQueue.put(((method, data),))

    def onScanStarted(self, library):
        SystemScansQueue.put((("scanstart", library),))

    def onScanFinished(self, library):
        SystemScansQueue.put((("scanstop", library),))

    def onCleanStarted(self, library):
        SystemScansQueue.put((("cleanstart", library),))

    def onCleanFinished(self, library):
        SystemScansQueue.put((("cleanfinsihed", library),))

    def onSettingsChanged(self):
        SystemEventsQueue.put((("settingschanged",),))

def SystemScans():

    while True:
        SystemScan = SystemScansQueue.get()

        if SystemScan == "QUIT":
            return

        if SystemScan[0] in ('scanstart', 'cleanstart'):
            utils.update_SyncPause('kodi_rw', True)
            utils.set_SyncLock()
        elif SystemScan[0] in ('scanstop', 'cleanfinsihed'):
            utils.WidgetRefresh[SystemScan[1]] = False

            if not utils.WidgetRefresh['music'] and not utils.WidgetRefresh['video']:
                utils.update_SyncPause('kodi_rw', False)
                utils.unset_SyncLock()

def SystemEvents():

    while True:
        SystemEvent = SystemEventsQueue.get()

        if SystemEvent == "QUIT":
            return

        if SystemEvent[0] == 'System.OnWake':
            webservice.start()

            for EmbyServer in list(utils.EmbyServers.values()):
                EmbyServer.ServerReconnect(False)

            utils.update_SyncPause('kodi_sleep',  False)
        elif SystemEvent[0] == 'System.OnSleep':
            utils.update_SyncPause('kodi_sleep', True)
            wait_PlayerEventsQueue()
            EmbyServer_DisconnectAll()
        elif SystemEvent[0] == 'System.OnQuit':
            ShutDown()
        elif SystemEvent[0] == 'Other.managelibsselection':
            utils.start_thread(pluginmenu.select_managelibs, ())
        elif SystemEvent[0] == 'Other.settings':
            utils.start_thread(opensettings, ())
        elif SystemEvent[0] == 'Other.manageserver':
            utils.start_thread(pluginmenu.manage_servers, (ServerConnect,))
        elif SystemEvent[0] == 'Other.clearimagecache':
            utils.start_thread(pluginmenu.clear_image_cache, ())
        elif SystemEvent[0] == 'Other.nodesreset':
            utils.start_thread(utils.nodesreset, ())
        elif SystemEvent[0] == 'Other.databasevacuummanual':
            utils.start_thread(dbio.DBVacuum, ())
        elif SystemEvent[0] == 'Other.factoryreset':
            utils.start_thread(pluginmenu.factoryreset, ())
        elif SystemEvent[0] == 'VideoLibrary.OnUpdate':  # Buffer updated items -> not overloading threads
            player.ItemsUpdateQueue.put(SystemEvent[1])
        elif SystemEvent[0] == 'settingschanged':
            SettingsChangedEvent.set()

def opensettings():
    utils.close_dialog("all")
    xbmc.executebuiltin('Addon.OpenSettings(plugin.service.emby-next-gen)')

# Remove Items

def poll_Events(XbmcMonitor):
    IsScanningMusicOld = False
    IsScanningVideoOld = False

    while not XbmcMonitor.waitForAbort(0.5):
        # Get scan status
        IsScanningMusic = xbmc.getCondVisibility('Library.IsScanningMusic')
        IsScanningVideo = xbmc.getCondVisibility('Library.IsScanningVideo')

        if IsScanningMusic != IsScanningMusicOld:
            IsScanningMusicOld = IsScanningMusic
            if IsScanningMusic:
                XbmcMonitor.onScanStarted("music")
            else:
                XbmcMonitor.onScanFinished("music")

        if IsScanningVideo != IsScanningVideoOld:
            IsScanningVideoOld = IsScanningVideo

            if IsScanningVideo:
                XbmcMonitor.onScanStarted("video")
            else:
                XbmcMonitor.onScanFinished("video")

# Mark as watched/unwatched updates
def VideoLibrary_OnUpdate():
    # {"id":8418,"type":"episode"} and not played before, is reset progress
    # {"item":{"id":8418,"type":"episode"},"playcount":0} is mark as unwatched
    # {"item":{"id":8418,"type":"episode"},"playcount":1} is mark as watched
    # (video) playback stop send {"item":{"id":8418,"type":"episode"}}, skip it as Emby session progress keeps track
    # (video) playback end sends {"item":{"id":8418,"type":"episode"}} and {"item":{"id":8428,"type":"episode"},"playcount":1}, skip it as Emby session progress keeps track
    EmbyDBs = {}
    KodiDB = None

    while True:
        if player.ItemsUpdateQueue.isEmpty():
            if KodiDB:
                dbio.DBCloseRO("video", "VideoLibrary_OnUpdate")

            for EmbyDB in EmbyDBs:
                dbio.DBCloseRO(EmbyDB, "VideoLibrary_OnUpdate")

            EmbyDBs = {}
            KodiDB = None

        UpdateItem = player.ItemsUpdateQueue.get()

        if UpdateItem == "QUIT":
            return

        EmbyUpdateItem = {}
        data = json.loads(UpdateItem)

        if "DELETE" in data and data["DELETE"] in player.ItemKodiSkipUpdate:
            player.ItemKodiSkipUpdate.remove(data["DELETE"])
            continue

        if 'item' in data:
            KodiItemId = int(data['item']['id'])
            KodiType = data['item']['type']
        elif 'id' in data:
            KodiItemId = int(data['id'])
            KodiType = data['type']
        else:
            continue

        if [KodiItemId, KodiType] in player.ItemKodiSkipUpdate:
            continue

        EmbyId, ServerId = utils.get_EmbyId_ServerId_by_Fake_KodiId(KodiItemId)

        if EmbyId:
            EmbyServer = utils.EmbyServers[ServerId]
        else: # Update synced item
            for ServerId, EmbyServer in list(utils.EmbyServers.items()):
                if ServerId not in EmbyDBs:
                    EmbyDBs[ServerId] = dbio.DBOpenRO(ServerId, "VideoLibrary_OnUpdate")

                EmbyId = EmbyDBs[ServerId].get_EmbyId_by_KodiId_KodiType(KodiItemId, KodiType)

                if EmbyId:
                    break
            else: # EmbyId not found
                continue

        if 'item' in data and 'playcount' in data:
            if KodiType in ("tvshow", "season"):
                continue

            EmbyUpdateItem = {'PlayCount': data['playcount']}
        else:
            if 'item' not in data: # {"id":8418,"type":"episode"}
                EmbyUpdateItem = {'Progress': 0, 'KodiItemId': KodiItemId, 'KodiType': KodiType}

        if EmbyUpdateItem:
            utils.ItemSkipUpdate.append(str(EmbyId))

            if 'Progress' in EmbyUpdateItem:
                if 'PlayCount' in EmbyUpdateItem:
                    EmbyServer.API.set_progress(EmbyId, EmbyUpdateItem['Progress'], EmbyUpdateItem['PlayCount'])
                    cache.update_userdata_Kodi(str(EmbyId), ServerId, None, None, None, None, EmbyUpdateItem['PlayCount'])
                else:
                    if not KodiDB:
                        KodiDB = dbio.DBOpenRO("video", "VideoLibrary_OnUpdate")

                    PlayCount = KodiDB.get_playcount(EmbyUpdateItem['KodiItemId'], EmbyUpdateItem['KodiType'])
                    EmbyServer.API.set_progress(EmbyId, EmbyUpdateItem['Progress'], PlayCount)
                    cache.update_userdata_Kodi(str(EmbyId), ServerId, None, None, None, None, PlayCount)
            else:
                EmbyServer.API.set_played(EmbyId, EmbyUpdateItem['PlayCount'])
                cache.update_userdata_Kodi(str(EmbyId), ServerId, None, None, None, None, EmbyUpdateItem['PlayCount'])


def ServerConnect(ServerSettings):
    emby.EmbyServer(ServerSettings).ServerInitConnection()

def EmbyServer_DisconnectAll():
    for EmbyServer in list(utils.EmbyServers.values()):
        EmbyServer.stop()

def settingschanged():
    while True:
        while not SettingsChangedEvent.wait(timeout=0.1):
            if utils.SystemShutdown:
                break

        if utils.SystemShutdown:
            return

        SettingsChangedEvent.clear()
        utils.close_dialog(10146) # addoninformation
        RestartKodi = False

        curltimeoutsPreviousValue = utils.curltimeouts
        SyncFavoritesPreviousValue = utils.SyncFavorites
        PreviousNodeLimit = utils.maxnodeitems
        utils.InitSettings()

        # Timeout changed, rebuild advanced settings -> restart Kodi
        if curltimeoutsPreviousValue != utils.curltimeouts:
            if xmls.advanced_settings():
                RestartKodi = True


        # Restart Kodi
        if RestartKodi:
            utils.clear_SyncPause()
            webservice.close()
            EmbyServer_DisconnectAll()
            utils.restart_kodi()
            return


        # Toggle Favorites
        if SyncFavoritesPreviousValue != utils.SyncFavorites:
            favorites.set_Favorites(utils.SyncFavorites)

        if PreviousNodeLimit != utils.maxnodeitems:
            for Server in list(utils.EmbyServers.values()):
                Server.Views.update_nodes()

def ServersConnect():

    if utils.startupDelay:
        if utils.sleep(utils.startupDelay):
            utils.clear_SyncPause()
            return

    _, Filenames = xbmcvfs.listdir(utils.FolderAddonUserdata)
    ServersSettings = []

    for Filename in Filenames:
        if Filename.startswith('server'):
            ServersSettings.append(f"{utils.FolderAddonUserdata}{Filename}")

    if not utils.WizardCompleted:  # First run
        utils.set_settings_bool('WizardCompleted', True)
        ServerConnect(None)
    else:
        for ServerSettings in ServersSettings:
            if utils.SystemShutdown:
                return
            ServerConnect(ServerSettings)


def get_digits(Text):
    Temp = ''.join(i for i in Text if i.isdigit())

    if Temp:
        return int(Temp)

    return 0

def setup():
    # Wait for homescreen (Kodi fully loaded)
    Counter = 0

    while not xbmc.getCondVisibility('Window.IsActive(10000)') and Counter < 120: # timeout after 120 Seconds
        utils.sleep(1)
        Counter += 1

    # copy default nodes
    utils.mkDir("special://profile/library/")
    utils.mkDir("special://profile/library/video/")
    utils.mkDir("special://profile/library/music/")
    utils.copytree("special://xbmc/system/library/video/", "special://profile/library/video/", (), True, False)
    utils.copytree("special://xbmc/system/library/music/", "special://profile/library/music/", (), True, False)

    if utils.MinimumSetup == "OPENLIBRARY":
        utils.set_settings('MinimumSetup', utils.MinimumVersion)
        return "OPENLIBRARY"

    if utils.MinimumSetup == utils.MinimumVersion:
        return True

    xbmc.executebuiltin('ReplaceWindow(10000)')

    # Clean installation
    if not utils.MinimumSetup:
        utils.update_mode_settings()
        utils.set_settings('MinimumSetup', utils.MinimumVersion)
        xmls.sources() # verify sources.xml

        if xmls.advanced_settings(): # verify advancedsettings.xml
            return False

        return True

    if utils.sleep(10): # Give Kodi time to load skin
        return "stop"

    pluginmenu.factoryreset(utils.Translate(33222))
    return "stop"

def wait_PlayerEventsQueue():
    if player.EmbyPlaying and player.PlayingItem["EmbyServer"]:
        player.PlayerEventsQueue.put((("stop", '{"end":"quit"}'),))

        with utils.SafeLock(player.PlayerEventsQueue.ThreadCondition):
            while player.PlayerEventsQueue.ItemsQueue:
                player.PlayerEventsQueue.ThreadCondition.wait(timeout=0.1)


def StartUp():
    global FullShutdown
    xbmc.log("EMBY.hooks.monitor: Starting Emby Next Gen", xbmc.LOGINFO)
    utils.start_thread(SystemEvents, ())
    utils.start_thread(SystemScans, ())
    Ret = setup()

    if Ret == "stop":
        webservice.close()
        xbmc.log("EMBY.hooks.monitor: Startup stopped for database compatibility", xbmc.LOGINFO)
    elif not Ret:  # db reset required
        webservice.close()
        utils.restart_kodi()
    else:  # Regular start
        FullShutdown = True
        utils.start_thread(utils.RunSyncJobsAsync, ())
        utils.start_thread(VideoLibrary_OnUpdate, ())
        utils.start_thread(favorites.monitor_Favorites, ())
        utils.start_thread(favorites.emby_change_Favorite, ())
        utils.start_thread(httpcache.clear, ())
        utils.start_thread(settingschanged, ())
        utils.start_thread(artworkcache.delete_artworkcache_watchdog, ())
        XbmcMonitor = monitor()  # Init Monitor
        utils.start_thread(poll_Events, (XbmcMonitor,))

        if Ret == "OPENLIBRARY":
            ServersConnect()
            utils.ActivateWindow("home", "", True)

            for EmbyServer in list(utils.EmbyServers.values()):

                with utils.SafeLock(utils.EmbyServerOnlineCondition):
                    while not EmbyServer.Online:
                        Wait = 30

                        while Wait > 0:
                            if utils.EmbyServerOnlineCondition.wait(timeout=0.1):
                                break

                            Wait -= 1

                        if utils.SystemShutdown:
                            break
                    else:
                        EmbyServer.library.select_libraries("AddLibrarySelection")

        else:
            utils.start_thread(ServersConnect, ())

        utils.NextGenOnline.set()
        utils.start_thread(init_widget_refresh, ())

        while not XbmcMonitor.waitForAbort(0.1):
            pass

    ShutDown()

def init_widget_refresh():
    utils.sleep(1)
    utils.refresh_widgets(True)
    utils.refresh_widgets(False)

def ShutDown():
    global FullShutdown

    if FullShutdown:
        # Shutdown
        FullShutdown = False
        utils.SystemShutdown = True
        utils.FavoriteQueue.put("QUIT")
        player.ItemsUpdateQueue.put("QUIT")
        wait_PlayerEventsQueue()
        EmbyServer_DisconnectAll()

        webservice.close()
        xbmc.log("EMBY.hooks.monitor: Emby Next Gen stopped", xbmc.LOGINFO)

    player.PlayerEventsQueue.put("QUIT")
    utils.SystemShutdown = True
    utils.unset_SyncLock()
    utils.NextGenOnline.set()
    SettingsChangedEvent.set()
    SystemEventsQueue.put("QUIT")
    SystemScansQueue.put("QUIT")
