import threading
import json
import sqlite3
from contextlib import closing
from collections import Counter
import xbmc
from core import movies, videos, musicvideo, folder, boxsets, genre, musicgenre, musicartist, musicalbum, audio, tag, person, studio, playlist, series, season, episode, common
from helper import utils, cache, artworkcache, copy, xmls
from hooks import favorites
from . import dbio, emby_db
from emby.api import ItemQueryError

LockPause = threading.Lock()
LockPauseBusy = threading.Lock()
LockLowPriorityWorkers = threading.Lock()
LockLibraryOps = threading.Lock()

class Library:
    def __init__(self, ServerData, API, Views, LibrarySynced, LibrarySyncedNames, LibrarySyncedContent, LibrarySyncedKodiDBs):
        self.ServerData = ServerData
        self.API = API
        self.Views = Views
        self.LibrarySynced = LibrarySynced
        self.LibrarySyncedKodiDBs = LibrarySyncedKodiDBs
        self.LibrarySyncedNames = LibrarySyncedNames
        self.LibrarySyncedContent = LibrarySyncedContent
        self.SettingsLoaded = False
        self.FirstSyncPending = False
        self.FirstSyncLock = threading.Lock()
        self.MovieResumeSession = None
        self.LockKodiStartSync = threading.Lock()
        self.LockDBRWOpen = threading.Lock()
        self.DatabaseInitCondition = threading.Condition(threading.Lock())
        self.SettingsLoadedCondition = threading.Condition(threading.Lock())
        self.ServerStartingId = f"{ServerData['ServerId']}_server_starting"
        self.ServerBusyId = f"{ServerData['ServerId']}_server_busy"
        self.ServerDatabaseInitId = f"{ServerData['ServerId']}_database_init"
        self.ServerReconnectingId = f"{ServerData['ServerId']}_server_reconnecting"
        self.ServerStartSyncId = f"{ServerData['ServerId']}_server_startscync"
        self.RemoveId = f"{ServerData['ServerId']}_remove"
        self.LibraryRemoveId = f"{ServerData['ServerId']}_library_remove"
        self.LibraryAddId = f"{ServerData['ServerId']}_library_add"
        self.UserDataId = f"{ServerData['ServerId']}_userdata"
        self.UpdateId = f"{ServerData['ServerId']}_update"
        self.UpdateParentsId = f"{ServerData['ServerId']}_update_parents"
        self.LibraryRemoveCleanId = f"{ServerData['ServerId']}_library_remove_clean"
        self.KodiStartSyncId = f"{ServerData['ServerId']}_kodi_start_sync"
        self.SelectLibrariesId = f"{ServerData['ServerId']}_select_libraries"
        self.JobBusy = False

    # Wait for database init
    def wait_DatabaseInit(self, WorkerId):

        with utils.SafeLock(self.DatabaseInitCondition):
            while utils.SyncPause.get(self.ServerDatabaseInitId, False):
                if utils.SystemShutdown or not self.SettingsLoaded:
                    return False
                self.DatabaseInitCondition.wait(timeout=0.1)

        return self.SettingsLoaded and not utils.SystemShutdown

    def open_Worker(self, WorkerId):
        with utils.SafeLock(utils.SyncPauseCondition):
            while self.Worker_is_paused(WorkerId):
                utils.SyncPauseCondition.wait(timeout=0.1)

                if utils.SystemShutdown or not self.SettingsLoaded:
                    return False

        return self.SettingsLoaded and not utils.SystemShutdown

    def close_Worker(self, WorkerId, RefreshVideo, RefreshAudio, SQLs):
        self.close_EmbyDBRW(WorkerId, SQLs)
        common.CachedItemsMissing = {}
        utils.close_ProgressBar(WorkerId)

        if RefreshVideo or RefreshAudio:
            artworkcache.delete_artworkcache()

        if RefreshVideo:
            utils.refresh_widgets(True)

        if RefreshAudio:
            utils.refresh_widgets(False)

    def open_EmbyDBRW(self, WorkerId, Priority):
        # if worker in progress, interrupt workers database ops (worker has lower priority) compared to all other Emby database (rw) ops
        if Priority and LockLowPriorityWorkers.locked() and self.LockDBRWOpen.locked():
            utils.update_SyncPause('priority', True)

        while not self.LockDBRWOpen.acquire(timeout=0.1):
            if utils.SystemShutdown:
                raise InterruptedError("Database open cancelled")

        SQLs = {}
        try:
            dbio.DBOpenRW(self.ServerData['ServerId'], WorkerId, SQLs)
        except Exception:
            self.LockDBRWOpen.release()
            utils.update_SyncPause('priority', False)
            raise
        return SQLs

    def close_EmbyDBRW(self, WorkerId, SQLs, Commit=True):
        try:
            dbio.DBCloseRW(self.ServerData['ServerId'], WorkerId, SQLs, Commit=Commit)
        finally:
            if self.LockDBRWOpen.locked():
                self.LockDBRWOpen.release()
            utils.update_SyncPause('priority', False)

    def abort_Worker(self, WorkerId, SQLs):
        # SQLs contains only this worker's currently open connections.
        OwnsEmby = bool(SQLs.get("emby"))
        Databases = [self.ServerData['ServerId'] if Key == "emby" else Key for Key, Value in SQLs.items() if Value]
        try:
            if Databases:
                dbio.DBCloseRW(",".join(Databases), WorkerId, SQLs, Commit=False)
        finally:
            if OwnsEmby:
                if self.LockDBRWOpen.locked():
                    self.LockDBRWOpen.release()
                utils.update_SyncPause('priority', False)
            self.API.update_Progress(WorkerId, -1)
            utils.close_ProgressBar(WorkerId)

    def restore_indexes(self):
        SQLs = {}
        try:
            SQLs = self.open_EmbyDBRW(self.LibraryAddId, False)
            for Database in ("video", "music", "texture"):
                dbio.DBOpenRW(Database, self.LibraryAddId, SQLs)
                SQLs[Database].add_Index()
                dbio.DBCloseRW(Database, self.LibraryAddId, SQLs)
            SQLs["emby"].add_Index()
            self.load_LibrarySynced(SQLs)
            self.close_EmbyDBRW(self.LibraryAddId, SQLs)
        except Exception as Error:
            # Startup also repairs these indexes if a disk/permission error persists.
            xbmc.log(f"EMBY.database.library: Index recovery failed: {type(Error).__name__}", xbmc.LOGERROR)
        finally:
            self.abort_Worker(self.LibraryAddId, SQLs)

    def write_EmbyDB(self, WorkerId, Write):
        SQLs = self.open_EmbyDBRW(WorkerId, True)
        try:
            Write(SQLs["emby"])
        except Exception:
            self.abort_Worker(WorkerId, SQLs)
            raise
        self.close_EmbyDBRW(WorkerId, SQLs)

    def set_syncdate(self, TimestampUTC):
        def save(EmbyDB):
            EmbyDB.update_LastIncrementalSync(TimestampUTC)
            EmbyDB.update_LastIncrementalSyncStart(TimestampUTC)

        self.write_EmbyDB("set_syncdate", save)

    def load_LibrarySynced(self, SQLs):
        self.LibrarySynced.clear()
        self.LibrarySyncedKodiDBs.clear()
        self.LibrarySyncedNames.clear()
        self.LibrarySyncedContent.clear()
        self.LibrarySynced.extend(SQLs["emby"].get_LibrarySynced())
        LibrarySyncedMirrows = SQLs["emby"].get_LibrarySyncedMirrow()

        for LibrarySyncedMirrowId, LibrarySyncedMirrowName, LibrarySyncedMirrowEmbyType, LibrarySyncedMirrowKodiDBs in LibrarySyncedMirrows:
            self.LibrarySyncedKodiDBs[f"{LibrarySyncedMirrowId}{LibrarySyncedMirrowEmbyType}"] = LibrarySyncedMirrowKodiDBs
            self.LibrarySyncedNames[LibrarySyncedMirrowId] = LibrarySyncedMirrowName

            if LibrarySyncedMirrowId in self.LibrarySyncedContent:
                self.LibrarySyncedContent[LibrarySyncedMirrowId] += (LibrarySyncedMirrowEmbyType,)
            else:
                self.LibrarySyncedContent[LibrarySyncedMirrowId] = (LibrarySyncedMirrowEmbyType,)

    def load_settings(self):
        self.MovieResumeLimits = xmls.load_video_resume_limits()
        self.ServerStartingId = f"{self.ServerData['ServerId']}_server_starting"
        self.ServerBusyId = f"{self.ServerData['ServerId']}_server_busy"
        self.ServerDatabaseInitId = f"{self.ServerData['ServerId']}_database_init"
        self.ServerReconnectingId = f"{self.ServerData['ServerId']}_server_reconnecting"
        self.ServerStartSyncId = f"{self.ServerData['ServerId']}_server_startscync"
        self.RemoveId = f"{self.ServerData['ServerId']}_remove"
        self.LibraryRemoveId = f"{self.ServerData['ServerId']}_library_remove"
        self.LibraryAddId = f"{self.ServerData['ServerId']}_library_add"
        self.UserDataId = f"{self.ServerData['ServerId']}_userdata"
        self.UpdateId = f"{self.ServerData['ServerId']}_update"
        self.UpdateParentsId = f"{self.ServerData['ServerId']}_update_parents"
        self.LibraryRemoveCleanId = f"{self.ServerData['ServerId']}_library_remove_clean"
        self.KodiStartSyncId = f"{self.ServerData['ServerId']}_kodi_start_sync"
        self.SelectLibrariesId = f"{self.ServerData['ServerId']}_select_libraries"
        utils.update_SyncPause(self.ServerDatabaseInitId, True)

        self.SettingsLoaded = False
        SQLs = {}
        try:
            # Load essential data and prefetching Media tags
            SQLs = self.open_EmbyDBRW("load_settings", True)

            if SQLs["emby"].init_EmbyDB():
                self.migrate_movie_tmdb_ids(SQLs["emby"])
                if not utils.MovieResumeOwnerEnabled:
                    SQLs["emby"].clear_movie_resume_owners()
                self.load_LibrarySynced(SQLs)
            else:
                utils.set_settings('MinimumSetup', "INVALID DATABASE")
                self.close_EmbyDBRW("load_settings", SQLs)
                utils.restart_kodi()
                xbmc.log(f"EMBY.database.library: load settings: database corrupt: ---<[ Emby server {self.ServerData['ServerId']}: load settings ]", xbmc.LOGERROR)
                return False

            self.close_EmbyDBRW("load_settings", SQLs)

            # Init database
            dbio.DBOpenRW("video", "load_settings", SQLs)
            SQLs["video"].add_Index()
            SQLs["video"].get_add_path(f"{utils.AddonModePath}dynamic/{self.ServerData['ServerId']}/", None, None)
            dbio.DBCloseRW("video", "load_settings", SQLs)
            dbio.DBOpenRW("music", "load_settings", SQLs)
            SQLs["music"].add_Index()
            SQLs["music"].disable_rescan(utils.currenttime_kodi_format())
            dbio.DBCloseRW("music", "load_settings", SQLs)
            dbio.DBOpenRW("texture", "load_settings", SQLs)
            SQLs["texture"].add_Index()
            dbio.DBCloseRW("texture", "load_settings", SQLs)
            try:
                self.finish_movie_resume_retirements()
            except sqlite3.Error as Error:
                xbmc.log(f"EMBY.database.library: Movie resume retirement remains pending: {type(Error).__name__}", xbmc.LOGWARNING)
            self.SettingsLoaded = True
        finally:
            try:
                self.abort_Worker("load_settings", SQLs)
            finally:
                utils.update_SyncPause(self.ServerDatabaseInitId, False)
                with utils.SafeLock(self.DatabaseInitCondition):
                    self.DatabaseInitCondition.notify_all()

        with utils.SafeLock(self.SettingsLoadedCondition):
            self.SettingsLoadedCondition.notify_all()

        with utils.SafeLock(utils.EmbyServerOnlineCondition):
            utils.EmbyServerOnlineCondition.notify_all()

    def migrate_movie_tmdb_ids(self, EmbyDB):
        Mappings = EmbyDB.get_movie_tmdb_migration()
        if Mappings is None:
            return

        Updates = []
        if Mappings:
            VideoDB = dbio.DBOpenRO("video", "movie_tmdb_migration")
            try:
                TmdbIds = VideoDB.get_movie_tmdb_ids()
            finally:
                dbio.DBCloseRO("video", "movie_tmdb_migration")
            Updates = [(TmdbIds[KodiId], EmbyId) for EmbyId, KodiId in Mappings if KodiId in TmdbIds]

        EmbyDB.complete_movie_tmdb_migration(Updates)
        xbmc.log(f"EMBY.database.library: Movie TMDB migration: backfilled {len(Updates)} of {len(Mappings)} mappings", xbmc.LOGINFO)

    def on_playback_report(self, Handler, Data, Accepted=False):
        if not utils.MovieResumeOwnerEnabled:
            return

        EmbyId = int(Data.get('ItemId') or 0)
        SessionId = Data.get('PlaySessionId')
        if Handler == "Sessions/Playing":
            if not self.MovieResumeSession or self.MovieResumeSession['Id'] != SessionId:
                self.MovieResumeSession = {'Id': SessionId, 'EmbyId': EmbyId, 'Recorded': False, 'PendingTmdbId': None}
            return

        Position = Data.get('PositionTicks', 0)
        Runtime = Data.get('RunTimeTicks', 0)
        Stopped = Handler == "Sessions/Playing/Stopped"
        Completed = Stopped and 0 < Runtime <= Position
        if Accepted:
            if EmbyId and Completed:
                self.clear_movie_resume_source(EmbyId)
            return

        Session = self.MovieResumeSession
        if not SessionId or not Session or Session['Id'] != SessionId:
            return
        try:
            if not EmbyId or Position <= 0 or Completed:
                return

            AllowSwitch = False
            if Stopped and Runtime > 0:
                IgnoreStartSeconds, IgnoreEndPercent = self.MovieResumeLimits
                Remaining = Runtime - Position
                AllowSwitch = (Position >= IgnoreStartSeconds * 10_000_000
                               and Remaining > 10_000_000
                               and Remaining * 100 >= Runtime * IgnoreEndPercent)

            # Keep the reported source before Emby can echo it, but wait for stop to replace an existing card.
            if not Session['Recorded'] or (Session['PendingTmdbId'] and AllowSwitch):
                self.record_movie_resume_source(EmbyId, Session, AllowSwitch)
                Session['Recorded'] = True
        finally:
            if Stopped:
                self.MovieResumeSession = None

    def clear_movie_resume_source(self, EmbyId):
        TaskId = "movie_resume_owner"
        SQLs = self.open_EmbyDBRW(TaskId, True)
        Commit = False
        try:
            SQLs['emby'].clear_movie_resume_owner(self.ServerData['UserId'], EmbyId)
            Commit = True
        finally:
            self.close_EmbyDBRW(TaskId, SQLs, Commit)

    def record_movie_resume_source(self, EmbyId, Session, AllowSwitch):
        UserId = self.ServerData['UserId']
        TaskId = "movie_resume_owner"
        SQLs = self.open_EmbyDBRW(TaskId, True)
        Commit = False
        Refresh = False
        try:
            Owner = SQLs['emby'].get_movie_resume_owner(UserId, EmbyId)
            if not Owner:
                return

            TmdbId, KodiId, PreviousId, PreviousKodiId, PendingRetirement = Owner
            RetiredEmbyId = PreviousId if PreviousKodiId and PreviousKodiId != KodiId else None
            if RetiredEmbyId and not AllowSwitch:
                Session['PendingTmdbId'] = TmdbId
                return

            if PendingRetirement:
                Refresh = self.retire_movie_resume_sources(SQLs, TaskId)
            if PreviousId != EmbyId:
                SQLs['emby'].set_movie_resume_owner(UserId, TmdbId, EmbyId, RetiredEmbyId)
            Commit = True
        finally:
            self.close_EmbyDBRW(TaskId, SQLs, Commit)

        # Commit the new owner before clearing the old bookmark in the other database.
        # A pending retirement survives interruption and is retried when Gen starts.
        if RetiredEmbyId:
            self.finish_movie_resume_retirements()
        if Refresh:
            utils.refresh_widgets(True)

    def retire_movie_resume_sources(self, SQLs, TaskId):
        UserId = self.ServerData['UserId']
        Pending = SQLs['emby'].get_movie_resume_retirements(UserId)
        if not Pending:
            return False

        Changed = False
        Commit = False
        dbio.DBOpenRW("video", TaskId, SQLs)
        try:
            for (KodiId,) in Pending:
                if KodiId:
                    Changed = SQLs['video'].delete_movie_resume_bookmarks(KodiId) or Changed
            Commit = True
        finally:
            dbio.DBCloseRW("video", TaskId, SQLs, Commit=Commit)

        SQLs['emby'].clear_movie_resume_retirements(UserId)
        return Changed

    def finish_movie_resume_retirements(self):
        if not utils.MovieResumeOwnerEnabled:
            return

        TaskId = "movie_resume_retire"
        SQLs = self.open_EmbyDBRW(TaskId, True)
        Commit = False
        try:
            Refresh = self.retire_movie_resume_sources(SQLs, TaskId)
            Commit = True
        finally:
            self.close_EmbyDBRW(TaskId, SQLs, Commit)
        if Refresh:
            utils.refresh_widgets(True)

    def get_startup_changes(self, LastSyncTime, LastSyncTimeStart):
        Queries = []
        Libraries = []

        for LibraryId, LibraryName, MediaType, _ in tuple(self.LibrarySynced):
            if LibraryId not in self.Views.ViewItems and MediaType != "Person":
                continue

            if MediaType == "Folder":
                Params = {'MinDateLastSaved': LastSyncTimeStart or LastSyncTime}
            else:
                # Older versions let realtime events move LastSyncTime ahead of a completed scan.
                Params = {'MinDateLastSavedForUser': LastSyncTimeStart or LastSyncTime, 'Fields': "UserDataLastPlayedDate"}

            Libraries.append((LibraryId, LibraryName, MediaType))
            Queries.append((LibraryId, MediaType, Params))

        with closing(self.API.get_Changes(Queries)) as Changes:
            for Library, (_, Items) in zip(Libraries, Changes):
                yield (*Library, Items)

    def KodiStartSync(self, Firstrun):  # Threaded by caller -> emby.py

        with utils.SafeLock(self.LockKodiStartSync):
            if not utils.startsyncenabled or utils.SystemShutdown:
                return

            # Verify time sync
            _, UnixTime = utils.currenttime_kodi_format_and_unixtime()

            if UnixTime < 946684800: # 01-01-2000
                utils.Dialog.notification(heading=utils.addon_name, message=utils.Translate(33751), icon=utils.icon, time=60000, sound=True)
                return

            NewSyncData = utils.currenttime()

            with utils.SafeLock(self.SettingsLoadedCondition):
                while not self.SettingsLoaded:
                    self.SettingsLoadedCondition.wait(timeout=0.1)

                    if utils.SystemShutdown:

                        return

            if Firstrun:
                self.select_libraries("AddLibrarySelection")
                with utils.SafeLock(self.FirstSyncLock):
                    self.FirstSyncPending = True

            embydb = dbio.DBOpenRO(self.ServerData['ServerId'], self.KodiStartSyncId)
            LastSyncTime = embydb.get_LastIncrementalSync()
            LastSyncTimeStart = embydb.get_LastIncrementalSyncStart()

            if not LastSyncTimeStart:
                LastSyncTimeStart = LastSyncTime

            dbio.DBCloseRO(self.ServerData['ServerId'], self.KodiStartSyncId)
            UpdateData = [[], []]

            if utils.SystemShutdown:
                return

            # Retrieve changes
            if LastSyncTimeStart:
                utils.update_SyncPause(self.ServerStartSyncId, True)
                xbmc.log(f"EMBY.database.library: Startup sync checkpoints: {LastSyncTime} / {LastSyncTimeStart}", xbmc.LOGDEBUG)
                utils.create_ProgressBar(self.KodiStartSyncId, utils.Translate(33199), utils.Translate(33445))
                ProgressBarTotal = len(self.LibrarySynced) / 100
                ProgressBarIndex = 0

                try:
                    Result = self.API.get_sync_queue(LastSyncTimeStart)
                    if Result.get('ItemsRemoved'):
                        self.removed(Result['ItemsRemoved'], False, False)

                    with closing(self.get_startup_changes(LastSyncTime, LastSyncTimeStart)) as Changes:
                        for LibrarySyncedId, _, LibrarySyncedEmbyType, Items in Changes:
                            if utils.SystemShutdown:
                                return

                            LibraryName = ""
                            ProgressBarIndex += 1

                            if LibrarySyncedId in self.Views.ViewItems:
                                LibraryName = self.Views.ViewItems[LibrarySyncedId][0]

                                utils.update_ProgressBar(self.KodiStartSyncId, ProgressBarIndex / ProgressBarTotal, utils.Translate(33199), f"{LibraryName} / {LibrarySyncedEmbyType}")

                            if not LibraryName and LibrarySyncedEmbyType != "Person":
                                xbmc.log(f"EMBY.database.library: [ {self.KodiStartSyncId} ] remove library {LibrarySyncedId}", xbmc.LOGDEBUG)
                                continue

                            ItemIndex = 0
                            UpdateDataTemp = 10000 * [()] # pre allocate memory
                            UpdateUserDataTemp = 10000 * [()] # pre allocate memory

                            if LibrarySyncedEmbyType == "Person":
                                Items = self.filter_PersonUpdates(Items)

                            for Item in Items:
                                if utils.SystemShutdown:
                                    return

                                if ItemIndex >= 10000:
                                    UpdateData[0] += UpdateDataTemp
                                    UpdateData[1] += UpdateUserDataTemp
                                    UpdateDataTemp = 10000 * [()] # pre allocate memory
                                    UpdateUserDataTemp = 10000 * [()] # pre allocate memory
                                    ItemIndex = 0

                                UpdateDataTemp[ItemIndex] = (Item['Id'], Item['Type'], LibrarySyncedId)

                                UserData = Item.get('UserData')
                                if Item['Type'] in utils.FavoriteTypes and UserData:
                                    UpdateUserDataTemp[ItemIndex] = (Item['Id'], Item['Type'], UserData.get("PlaybackPositionTicks"), UserData.get("PlayCount"), UserData.get("IsFavorite"), UserData.get("Played"), UserData.get("LastPlayedDate"), UserData.get("PlayedPercentage"), UserData.get("UnplayedItemCount"))

                                ItemIndex += 1

                            UpdateData[0] += UpdateDataTemp[:ItemIndex]
                            UpdateData[1] += UpdateUserDataTemp[:ItemIndex]

                    self.updated([Row for Row in dict.fromkeys(UpdateData[0]) if Row], False, False)
                    self.userdata([Row for Row in dict.fromkeys(UpdateData[1]) if Row], False, False)
                except Exception as Error:
                    xbmc.log(f"EMBY.database.library: Startup change discovery failed; checkpoint retained: {Error}", xbmc.LOGERROR)
                    return
                finally:
                    utils.close_ProgressBar(self.KodiStartSyncId)
                    utils.update_SyncPause(self.ServerStartSyncId, False)

                if utils.SystemShutdown:
                    return

            if self.RunJobs(False, True) is False:
                return

            self.set_syncdate(NewSyncData)
            self.finish_first_sync()

    def finish_first_sync(self):
        with utils.SafeLock(self.FirstSyncLock):
            if self.FirstSyncPending and not utils.SystemShutdown:
                xbmc.executebuiltin('ReloadSkin()')
                self.FirstSyncPending = False

    # Userdata change is an high priority task
    def worker_userdata(self, IncrementalSync):
        if not self.wait_DatabaseInit(self.UserDataId):
            return False
        SQLs = {}
        try:
            EmbyDB = dbio.DBOpenRO(self.ServerData['ServerId'], self.UserDataId)
            try:
                if not EmbyDB.has_Userdata():
                    return True
            finally:
                dbio.DBCloseRO(self.ServerData['ServerId'], self.UserDataId)

            # Read and acknowledge the same snapshot so a newer event cannot be deleted.
            SQLs = self.open_EmbyDBRW(self.UserDataId, True)
            UserDataItems = SQLs["emby"].get_Userdata()
            if not UserDataItems:
                return True

            utils.create_ProgressBar(self.UserDataId, utils.Translate(33199), utils.Translate(33178))
            UpdateItems, Others = self.ItemsSort(self.worker_userdata_generator, SQLs, UserDataItems, False, len(UserDataItems) / 100)
            RefreshAudio = False
            RefreshVideo = False
            RefreshWidgets = False

            for KodiDBs, CategoryItems in list(UpdateItems.items()):
                if content_available(CategoryItems):
                    RecordsPercent = len(CategoryItems) / 100
                    dbio.DBOpenRW(KodiDBs, self.UserDataId, SQLs)

                    for Items in CategoryItems:
                        if not Items:
                            continue

                        RefreshVideo, RefreshAudio = get_content_database(KodiDBs, Items, RefreshVideo, RefreshAudio)
                        ClassObject = None
                        ReleaseCounter = 0

                        for index, Item in enumerate(Items, 1):
                            ReleaseCounter += 1

                            if ReleaseCounter % 50 == 0:
                                xbmc.sleep(0) # release GIL

                            Item = json.loads(Item)

                            if not ClassObject:
                                ClassObject = self.load_libraryObject(Item['Type'], SQLs)

                            SQLs["emby"].delete_Userdata(Item["Id"])
                            Continue, Update = self.update_UserData(index / RecordsPercent, index, Item, SQLs, KodiDBs, IncrementalSync, ClassObject, True, self.UserDataId, True)
                            common.set_RunTimeTicks(Item)

                            if Update:
                                RefreshWidgets = True

                            if not Continue:
                                del ClassObject
                                return False

                        del ClassObject

                    dbio.DBCloseRW(KodiDBs, self.UserDataId, SQLs)

            for Other in Others: # Unsynced content
                Other = json.loads(Other)

                if not SQLs["emby"].exist_UpdateItem(Other['Id']): # Do not remove items which are flagged for update
                    SQLs["emby"].delete_Userdata(Other['Id'])
                    common.set_RunTimeTicks(Other)

            if RefreshWidgets:
                self.close_Worker(self.UserDataId, RefreshVideo, RefreshAudio, SQLs)
            else:
                self.close_Worker(self.UserDataId, False, False, SQLs)

                if Others:
                    utils.refresh_library_widgets()
            return True
        except Exception as Error:
            xbmc.log(f"EMBY.database.library: Worker failed; pending work retained: {self.UserDataId} / {type(Error).__name__}", xbmc.LOGERROR)
            return False
        finally:
            if SQLs:
                self.abort_Worker(self.UserDataId, SQLs)

    def filter_PersonUpdates(self, Items):
        WorkerId = f"{self.KodiStartSyncId}_people"
        embydb = dbio.DBOpenRO(self.ServerData['ServerId'], WorkerId)

        try:
            for Item in Items:
                # Skip before enqueueing full detail queries for unselected people.
                if embydb.get_item_exists_by_id(Item['Id'], "Person"):
                    yield Item
        finally:
            dbio.DBCloseRO(self.ServerData['ServerId'], WorkerId)

    def worker_userdata_generator(self, SQLs, UserDataItems, RecordsPercent):
        for index, UserDataItem in enumerate(UserDataItems, 1): # UserDataItem = EmbyId, EmbyType, EmbyPlaybackPositionTicks, EmbyPlayCount, EmbyIsFavorite, EmbyPlayed, EmbyLastPlayedDate
            utils.update_ProgressBar(self.UserDataId, index / RecordsPercent, utils.Translate(33178), str(UserDataItem[0]))
            MetaData = SQLs["emby"].get_UserData_MetaData(UserDataItem[0], UserDataItem[1])
            MetaData.update({"Id": UserDataItem[0], 'PlaybackPositionTicks': UserDataItem[2], 'PlayCount': UserDataItem[3], 'IsFavorite': UserDataItem[4], 'LastPlayedDate': UserDataItem[6], 'Played': UserDataItem[5], 'PlayedPercentage': UserDataItem[7], 'UnplayedItemCount': UserDataItem[8]})

            if MetaData['KodiItemId']:
                yield True, MetaData
            else: # skip if item is not synced
                yield False, MetaData

    def worker_update(self, IncrementalSync):

        while True: # While running update additional updates migth be addded
            with utils.SafeLock(LockLowPriorityWorkers):
                if not self.wait_DatabaseInit(self.UpdateId):
                    return False

                embydb = dbio.DBOpenRO(self.ServerData['ServerId'], self.UpdateId)
                UpdateItems, UpdateItemsCount, KodiDBMappingUpdate = embydb.get_UpdateItem()
                RemoveItems = embydb.empty_RemoveItem()
                dbio.DBCloseRO(self.ServerData['ServerId'], self.UpdateId)
                del embydb

            # Re-run if removed items are added while waiting for updates
            if RemoveItems:
                if self.worker_remove(IncrementalSync) is False:
                    return False

            # Process updates
            with utils.SafeLock(LockLowPriorityWorkers):

                if not UpdateItemsCount: # Job done

                    return True

                if not self.open_Worker(self.UpdateId):
                    return False

                utils.create_ProgressBar(self.UpdateId, utils.Translate(33199), utils.Translate(33178))
                RecordsPercent = UpdateItemsCount / 100
                index = 0
                try:
                    UpdateItems, Others = self.ItemsSort(self.worker_update_generator, {}, UpdateItems, False, RecordsPercent)
                except ItemQueryError as Error:
                    xbmc.log(f"EMBY.database.library: Detail query failed; pending updates retained: {Error}", xbmc.LOGERROR)
                    utils.close_ProgressBar(self.UpdateId)
                    return False
                RefreshAudio = False
                RefreshVideo = False
                SQLs = {}
                try:
                    SQLs = self.open_EmbyDBRW(self.UpdateId, False)

                    for KodiDBs, CategoryItems in list(UpdateItems.items()):
                        if content_available(CategoryItems):
                            dbio.DBOpenRW(KodiDBs, self.UpdateId, SQLs)

                            for Items in CategoryItems:
                                if not Items:
                                    continue

                                RefreshVideo, RefreshAudio = get_content_database(KodiDBs, Items, RefreshVideo, RefreshAudio)
                                ClassObject = None
                                ReleaseCounter = 0

                                for Item in Items:
                                    ReleaseCounter += 1

                                    if ReleaseCounter % 50 == 0:
                                        xbmc.sleep(0) # release GIL

                                    Item = json.loads(Item)


                                    if not ClassObject:
                                        ClassObject = self.load_libraryObject(Item['Type'], SQLs)

                                    SQLs["emby"].delete_UpdateItem(Item['Id'])

                                    index += 1

                                    if Item['Id'] in KodiDBMappingUpdate:
                                        ClassObject.KodiDBMapping = KodiDBMappingUpdate[Item['Id']]

                                    if not self.update_Item(index / RecordsPercent, index, Item, SQLs, KodiDBs, IncrementalSync, ClassObject, self.UpdateId):
                                        del ClassObject
                                        return False

                                del ClassObject

                            dbio.DBCloseRW(KodiDBs, self.UpdateId, SQLs)


                    for Other in Others:
                        Other = json.loads(Other)

                        SQLs["emby"].delete_UpdateItem(Other['Id'])

                    if RefreshVideo or RefreshAudio:
                        self.close_Worker(self.UpdateId, RefreshVideo, RefreshAudio, SQLs)
                    else:
                        self.close_Worker(self.UpdateId, False, False, SQLs)

                        if Others:
                            utils.refresh_library_widgets()
                except Exception as Error:
                    xbmc.log(f"EMBY.database.library: Worker failed; pending work retained: {self.UpdateId} / {type(Error).__name__}", xbmc.LOGERROR)
                    return False
                finally:
                    self.abort_Worker(self.UpdateId, SQLs)

    def worker_update_generator(self, SQLs, UpdateItems, RecordsPercent):
        ProcessedCount = 0

        for LibraryId, UpdateItemsArray in list(UpdateItems.items()):
            for ContentType, UpdateItemsData in list(UpdateItemsArray.items()):
                if not UpdateItemsData:
                    continue


                if LibraryId in self.Views.ViewItems:
                    LibraryName = self.Views.ViewItems[LibraryId][0]
                else:
                    LibraryName = LibraryId

                utils.update_ProgressBar(self.UpdateId, ProcessedCount / RecordsPercent, utils.Translate(33734), f"{LibraryName} / {ContentType}")

                if ContentType == "unknown":
                    ContentType = ["Person", "Studio", "Genre", "Tag", "BoxSet", "Movie", "Video", "Series", "Season", "Episode", "MusicArtist", "MusicGenre", "MusicVideo", "MusicAlbum", "Audio", "Playlist", "Folder"]
                else:
                    ContentType = [ContentType]

                UpdateItemsDataTemp = copy.Object(UpdateItemsData)

                for Item in self.API.get_Items_Ids(UpdateItemsData, ContentType, False, False, "", LibraryId, {}, {"Object": self.pause_workers, "Params": ("Startsync_http", SQLs, None)}, False, Strict=True):
                    ProcessedCount += 1

                    yield True, Item

                # Remove not detected Items
                PendingIds = Counter(UpdateItemsData)
                for UpdateItemsIdTemp in UpdateItemsDataTemp:
                    if PendingIds[UpdateItemsIdTemp]:
                        PendingIds[UpdateItemsIdTemp] -= 1
                        yield False, {'Id': UpdateItemsIdTemp}
                UpdateItemsData.clear()

    def worker_remove(self, IncrementalSync):
        with utils.SafeLock(LockLowPriorityWorkers):
            if not self.wait_DatabaseInit(self.RemoveId):
                return False

            while True: # Removed items can add additional subitems to be removed
                EmbyDB = dbio.DBOpenRO(self.ServerData['ServerId'], self.RemoveId)
                RemoveItems = EmbyDB.get_RemoveItem()
                dbio.DBCloseRO(self.ServerData['ServerId'], self.RemoveId)
                del EmbyDB

                if not RemoveItems:
                    return True

                if not self.open_Worker(self.RemoveId):
                    return False

                RefreshAudio = False
                RefreshVideo = False
                utils.create_ProgressBar(self.RemoveId, utils.Translate(33199), utils.Translate(33261))
                RecordsPercent = len(RemoveItems) / 100
                SQLs = {}
                try:
                    SQLs = self.open_EmbyDBRW(self.RemoveId, False)
                    UpdateItems, Others = self.ItemsSort(self.worker_remove_generator, SQLs, RemoveItems, True, RecordsPercent)

                    if not SQLs['emby']:
                        return False

                    for KodiDBs, CategoryItems in list(UpdateItems.items()):
                        if content_available(CategoryItems):
                            dbio.DBOpenRW(KodiDBs, self.RemoveId, SQLs)

                            for Items in CategoryItems:
                                if not Items:
                                    continue

                                RecordsPercent = len(Items) / 100
                                RefreshVideo, RefreshAudio = get_content_database(KodiDBs, Items, RefreshVideo, RefreshAudio)
                                ClassObject = None
                                ReleaseCounter = 0

                                for index, Item in enumerate(Items, 1):
                                    ReleaseCounter += 1

                                    if ReleaseCounter % 50 == 0:
                                        xbmc.sleep(0) # release GIL

                                    Item = json.loads(Item)

                                    if not ClassObject:
                                        ClassObject = self.load_libraryObject(Item['Type'], SQLs)

                                    SQLs["emby"].delete_RemoveItem(Item['Id'])

                                    if not self.remove_Item(index / RecordsPercent, index, Item, SQLs, KodiDBs, IncrementalSync, ClassObject):
                                        del ClassObject
                                        return False

                                del ClassObject

                            dbio.DBCloseRW(KodiDBs, self.RemoveId, SQLs)

                    for Other in Others:
                        Other = json.loads(Other)
                        SQLs["emby"].delete_RemoveItem(Other['Id'])

                    if RefreshVideo or RefreshAudio:
                        self.close_Worker(self.RemoveId, RefreshVideo, RefreshAudio, SQLs)
                    else:
                        self.close_Worker(self.RemoveId, False, False, SQLs)

                        if Others:
                            utils.refresh_library_widgets()
                except Exception as Error:
                    xbmc.log(f"EMBY.database.library: Worker failed; pending work retained: {self.RemoveId} / {type(Error).__name__}", xbmc.LOGERROR)
                    return False
                finally:
                    self.abort_Worker(self.RemoveId, SQLs)

    def worker_remove_generator(self, SQLs, RemoveItems, RecordsPercent):
        for index, RemoveItem in enumerate(RemoveItems, 1):
            if not self.pause_workers(self.RemoveId, SQLs, None):
                break

            utils.update_ProgressBar(self.RemoveId, index / RecordsPercent, utils.Translate(33261), str(RemoveItem[0]))
            FoundRemoveItems = SQLs["emby"].get_remove_generator_items(RemoveItem[0], RemoveItem[1])

            for FoundRemoveItem in FoundRemoveItems:
                if RemoveItem[1]:
                    FoundRemoveItem['LibraryId'] = str(RemoveItem[1])
                else:
                    FoundRemoveItem['LibraryId'] = ""

                yield True, FoundRemoveItem

            if not FoundRemoveItems:
                yield False, {'Id': RemoveItem[0]}

    def worker_library_remove(self):
        with utils.SafeLock(LockLibraryOps):
            with utils.SafeLock(LockLowPriorityWorkers):
                if not self.wait_DatabaseInit(self.LibraryRemoveId):
                    return False

                embydb = dbio.DBOpenRO(self.ServerData['ServerId'], self.LibraryRemoveId)
                RemovedLibraries = embydb.get_LibraryRemove()
                dbio.DBCloseRO(self.ServerData['ServerId'], self.LibraryRemoveId)
                del embydb

                if not RemovedLibraries:
                    return True

                if not self.open_Worker(self.LibraryRemoveId):
                    return False

                utils.create_ProgressBar(self.LibraryRemoveId, utils.Translate(33199), utils.Translate(33184))
                RemovedLibrariesPercent = len(RemovedLibraries) / 100
                SQLs = {}
                try:
                    SQLs = self.open_EmbyDBRW(self.LibraryRemoveId, False)

                    for RemovedLibraryIndex, RemovedLibrary in enumerate(RemovedLibraries, 1):
                        utils.update_ProgressBar(self.LibraryRemoveId, RemovedLibraryIndex / RemovedLibrariesPercent, utils.Translate(33184), RemovedLibrary[1])
                        SQLs["emby"].add_remove_library_items(RemovedLibrary[0])
                        xbmc.log(f"EMBY.database.library: Removed Emby library {RemovedLibrary[0]}", xbmc.LOGINFO)
                        dbio.DBOpenRW("video", self.LibraryRemoveId, SQLs)
                        SQLs["video"].delete_path(f"{utils.AddonModePath}tvshows/{self.ServerData['ServerId']}/{RemovedLibrary[0]}/")
                        SQLs["video"].delete_path(f"{utils.AddonModePath}movies/{self.ServerData['ServerId']}/{RemovedLibrary[0]}/")
                        SQLs["video"].delete_path(f"{utils.AddonModePath}musicvideos/{self.ServerData['ServerId']}/{RemovedLibrary[0]}/")
                        dbio.DBCloseRW("video", self.LibraryRemoveId, SQLs)
                        dbio.DBOpenRW("music", self.LibraryRemoveId, SQLs)
                        SQLs["music"].delete_path(f"{utils.AddonModePath}audio/{self.ServerData['ServerId']}/{RemovedLibrary[0]}/")
                        dbio.DBCloseRW("music", self.LibraryRemoveId, SQLs)
                        self.Views.delete_node_by_id(RemovedLibrary[0])

                    self.load_LibrarySynced(SQLs)
                    self.close_Worker(self.LibraryRemoveId, True, True, SQLs)
                except Exception as Error:
                    xbmc.log(f"EMBY.database.library: Worker failed; pending work retained: {self.LibraryRemoveId} / {type(Error).__name__}", xbmc.LOGERROR)
                    return False
                finally:
                    self.abort_Worker(self.LibraryRemoveId, SQLs)

        if RemovedLibraries:
            if self.worker_remove(False):
                SQLs = {}
                try:
                    SQLs = self.open_EmbyDBRW(self.LibraryRemoveCleanId, True)
                    for RemovedLibrary in RemovedLibraries:
                        SQLs["emby"].remove_LibrarySyncedMirrow(RemovedLibrary[0])
                        # Keep the durable task until item removal and metadata cleanup succeed.
                        SQLs["emby"].remove_LibraryRemove(RemovedLibrary[0])
                    self.load_LibrarySynced(SQLs)
                    self.close_EmbyDBRW(self.LibraryRemoveCleanId, SQLs)
                except Exception as Error:
                    xbmc.log(f"EMBY.database.library: Library cleanup remains pending: {type(Error).__name__}", xbmc.LOGERROR)
                    return False
                finally:
                    self.abort_Worker(self.LibraryRemoveCleanId, SQLs)
                if self.worker_library_add() is False:
                    return False
            else:
                return False

            self.Views.update_nodes(RemoveEmpty=True)

        return True

    def worker_library_add(self):
        with utils.SafeLock(LockLibraryOps):
            with utils.SafeLock(LockLowPriorityWorkers):
                if not self.wait_DatabaseInit(self.LibraryAddId):
                    return False

                embydb = dbio.DBOpenRO(self.ServerData['ServerId'], self.LibraryAddId)
                AddedLibraries = embydb.get_LibraryAdd()
                dbio.DBCloseRO(self.ServerData['ServerId'], self.LibraryAddId)
                del embydb

                if not AddedLibraries:
                    return True

                if not self.open_Worker(self.LibraryAddId):
                    return False

                utils.create_ProgressBar(self.LibraryAddId, utils.Translate(33199), utils.Translate(33238))
                MusicArtistUpdate = False
                Completed = False
                SQLs = {}
                try:
                    SQLs = self.open_EmbyDBRW(self.LibraryAddId, False)
                    SQLs["emby"].delete_Index()

                    # remove index (for faster inserts)
                    dbio.DBOpenRW('video', self.LibraryAddId, SQLs)
                    SQLs["video"].delete_Index()
                    dbio.DBCloseRW('video', self.LibraryAddId, SQLs)
                    dbio.DBOpenRW('music', self.LibraryAddId, SQLs)
                    SQLs["music"].delete_Index()
                    dbio.DBCloseRW('music', self.LibraryAddId, SQLs)
                    dbio.DBOpenRW('texture', self.LibraryAddId, SQLs)
                    SQLs["texture"].delete_Index()
                    dbio.DBCloseRW('texture', self.LibraryAddId, SQLs)

                    # Add libraries
                    AddedLibrariesPercent = len(AddedLibraries) / 100

                    for AddedLibraryIndex, AddedLibrary in enumerate(AddedLibraries, 1): # AddedLibrary -> LibraryId, LibraryName, EmbyType, KodiDB, KodiDBs
                        AddedLibraryProgress = int(AddedLibraryIndex / AddedLibrariesPercent)

                        if AddedLibrary[2] == "MusicArtist":
                            MusicArtistUpdate = True

                        utils.update_ProgressBar(self.LibraryAddId, AddedLibraryProgress, utils.Translate(33238), AddedLibrary[1])
                        SQLs["emby"].add_LibrarySyncedMirrow(AddedLibrary[0], AddedLibrary[1], AddedLibrary[2], AddedLibrary[3])
                        self.load_LibrarySynced(SQLs)
                        dbio.DBOpenRW(AddedLibrary[3], self.LibraryAddId, SQLs)
                        self.API.update_Progress(self.LibraryAddId, 0)

                        if AddedLibrary[2] in ("Movie", "Video", "MusicVideo", "Series") and "video" in SQLs and SQLs["video"]:
                            TagObject = tag.Tag(self, SQLs)
                            TagObject.change({"LibraryId": AddedLibrary[0], "Type": "Tag", "Id": f"{utils.MappingIds['Tag']}00{AddedLibrary[0]}", "Name": AddedLibrary[1], "Memo": "library"}, False) # add library name as tag

                            if AddedLibrary[2] in ("Movie", "Video"):
                                TagObject.change({"LibraryId": AddedLibrary[0], "Type": "Tag", "Id": f"{utils.MappingIds['Tag']}01{AddedLibrary[0]}", "Name": "Movies (Favorites)", "Memo": "favorite"}, False) # add library favorits as tag
                            elif AddedLibrary[2] == "MusicVideo":
                                TagObject.change({"LibraryId": AddedLibrary[0], "Type": "Tag", "Id": f"{utils.MappingIds['Tag']}02{AddedLibrary[0]}", "Name": "Musicvideos (Favorites)", "Memo": "favorite"}, False) # add library favorits as tag
                            elif AddedLibrary[2] == "Series":
                                TagObject.change({"LibraryId": AddedLibrary[0], "Type": "Tag", "Id": f"{utils.MappingIds['Tag']}03{AddedLibrary[0]}", "Name": "TVShows (Favorites)", "Memo": "favorite"}, False) # add library favorits as tag

                            del TagObject

                        # Add Item
                        ClassObject = self.load_libraryObject(AddedLibrary[2], SQLs)

                        for ItemIndex, Item in enumerate(self.API.get_Items(AddedLibrary[0], (AddedLibrary[2],), False, {}, self.LibraryAddId, {"Object": self.pause_workers, "Params": (self.LibraryAddId, SQLs, ClassObject)}, True), 1):
                            # Add Content
                            Item["LibraryId"] = AddedLibrary[0]
                            self.API.update_Progress(self.LibraryAddId, ItemIndex)

                            if not self.update_Item(AddedLibraryProgress, ItemIndex, Item, SQLs, AddedLibrary[3], False, ClassObject, self.LibraryAddId):
                                del ClassObject
                                self.API.update_Progress(self.LibraryAddId, -1)
                                return False

                            # Add UserData
                            UpdateKodiFavorites = AddedLibrary[2] != "MusicArtist" # skip favorite updates, they must be refreshed last

                            with utils.SafeLock(LockPause):
                                Continue, _ = self.update_UserData(AddedLibraryProgress, ItemIndex, Item, SQLs, AddedLibrary[3], False, ClassObject, UpdateKodiFavorites, self.LibraryAddId, False)

                            if not Continue:
                                del ClassObject
                                self.API.update_Progress(self.LibraryAddId, -1)
                                utils.close_ProgressBar(self.LibraryAddId)
                                return False

                        del ClassObject

                        if not SQLs["emby"]:
                            return False

                        SQLs["emby"].add_LibrarySynced(AddedLibrary[0], AddedLibrary[1], AddedLibrary[2], AddedLibrary[3])
                        SQLs["emby"].remove_LibraryAdd(AddedLibrary[0], AddedLibrary[1], AddedLibrary[2], AddedLibrary[3])
                        self.load_LibrarySynced(SQLs)
                        dbio.DBCloseRW(AddedLibrary[3], self.LibraryAddId, SQLs)

                    # add index
                    dbio.DBOpenRW('video', self.LibraryAddId, SQLs)
                    SQLs["video"].add_Index()
                    dbio.DBCloseRW('video', self.LibraryAddId, SQLs)
                    dbio.DBOpenRW('music', self.LibraryAddId, SQLs)
                    SQLs["music"].add_Index()
                    dbio.DBCloseRW('music', self.LibraryAddId, SQLs)
                    dbio.DBOpenRW("texture", self.LibraryAddId, SQLs)
                    SQLs["texture"].add_Index()
                    dbio.DBCloseRW("texture", self.LibraryAddId, SQLs)
                    SQLs["emby"].add_Index()
                    self.close_Worker(self.LibraryAddId, True, True, SQLs)
                    Completed = True


                    # Update favorites for subitems
                    if MusicArtistUpdate:
                        favorites.update_MusicArtist(self)

                    # refresh
                    self.Views.update_nodes()
                    cache.reset()
                except Exception as Error:
                    xbmc.log(f"EMBY.database.library: Worker failed; pending work retained: {self.LibraryAddId} / {type(Error).__name__}", xbmc.LOGERROR)
                    return False
                finally:
                    self.abort_Worker(self.LibraryAddId, SQLs)
                    if not Completed and not utils.SystemShutdown:
                        self.restore_indexes()

        self.RunJobs(False, False)
        return True

    # Process item operations
    def update_Item(self, ProgressValue, ItemIndex, Item, SQLs, KodiDBs, IncrementalSync, ClassObject, WorkerId):
        # Ignore extras received through generic scans or later server events.
        if Item['Type'] not in emby_db.EmbyTypes or Item.get('ExtraType'):
            return True


        with utils.SafeLock(LockPause):
            ClassObject.change(Item, IncrementalSync)

        if "Name" in Item:
            ProgressMsg = Item.get('Name', "unknown")
        elif "Path" in Item:
            ProgressMsg = Item['Path']
        else:
            ProgressMsg = "unknown"

        utils.update_ProgressBar(WorkerId, ProgressValue, f"{Item['Type']}: {ItemIndex}", ProgressMsg)


        if not self.pause_workers(WorkerId, SQLs, ClassObject):
            return False

        if utils.SystemShutdown:
            dbio.DBCloseRW(KodiDBs, WorkerId, SQLs)
            self.close_Worker(WorkerId, False, False, SQLs)
            return False

        del Item
        return True

    def update_UserData(self, ProgressValue, ItemIndex, Item, SQLs, KodiDBs, IncrementalSync, ClassObject, UpdateFavorite, WorkerId, UpdateProgress):
        if UpdateProgress:
            utils.update_ProgressBar(WorkerId, ProgressValue, f"{Item['Type']}: {ItemIndex}", str(Item['Id']))

        Update = False

        if Item['Type'] in utils.FavoriteTypes:
            Update = ClassObject.userdata(Item, IncrementalSync, UpdateFavorite)

        if utils.SystemShutdown:
            dbio.DBCloseRW(KodiDBs, WorkerId, SQLs)
            self.close_Worker(WorkerId, False, False, SQLs)
            return False, False

        del Item
        return True, Update

    def remove_Item(self, ProgressValue, ItemIndex, Item, SQLs, KodiDBs, IncrementalSync, ClassObject):
        utils.update_ProgressBar(self.RemoveId, ProgressValue, f"{Item['Type']}: {ItemIndex}", str(Item['Id']))

        with utils.SafeLock(LockPause):
            ClassObject.remove(Item, IncrementalSync)

        if not self.pause_workers(self.RemoveId, SQLs, ClassObject):
            return False

        if utils.SystemShutdown:
            dbio.DBCloseRW(KodiDBs, self.RemoveId, SQLs)
            self.close_Worker(self.RemoveId, False, False, SQLs)
            return False

        del Item
        return True

    def pause_workers(self, WorkerId, SQLs, ClassObject):
        with utils.SafeLock(LockPauseBusy):
            if not self.Worker_is_paused(WorkerId):
                return True
            # Persist Kodi changes before acknowledging the corresponding Emby jobs.
            Databases = [Key for Key, Value in SQLs.items() if Value and Key != "emby"]
            if SQLs.get("emby"):
                Databases.append(self.ServerData['ServerId'])
            Databases = ",".join(Databases)
            while not LockPause.acquire(timeout=0.1):
                if utils.SystemShutdown:
                    return False
            try:
                if Databases:
                    OwnsEmby = bool(SQLs.get("emby"))
                    try:
                        dbio.DBCloseRW(Databases, WorkerId, SQLs)
                    finally:
                        if OwnsEmby and self.LockDBRWOpen.locked():
                            self.LockDBRWOpen.release()
                with utils.SafeLock(utils.SyncPauseCondition):
                    while self.Worker_is_paused(WorkerId):
                        if utils.SystemShutdown:
                            utils.close_ProgressBar(WorkerId)
                            return False
                        utils.SyncPauseCondition.wait(timeout=0.1)
                if Databases:
                    while not self.LockDBRWOpen.acquire(timeout=0.1):
                        if utils.SystemShutdown:
                            return False
                    try:
                        dbio.DBOpenRW(Databases, WorkerId, SQLs)
                    except Exception:
                        self.LockDBRWOpen.release()
                        raise
                if ClassObject:
                    ClassObject.update_SQLs(SQLs)
            finally:
                LockPause.release()
        return True

    def load_libraryObject(self, MediaType, SQLs):
        if MediaType == "Movie":
            return movies.Movies(self, SQLs)

        if MediaType == "Video":
            return videos.Videos(self, SQLs)

        if MediaType == "MusicVideo":
            return musicvideo.MusicVideo(self, SQLs)

        if MediaType == "MusicAlbum":
            return musicalbum.MusicAlbum(self, SQLs)

        if MediaType == 'Audio':
            return audio.Audio(self, SQLs)

        if MediaType == "Episode":
            return episode.Episode(self, SQLs)

        if MediaType == "Season":
            return season.Season(self, SQLs)

        if MediaType == "Folder":
            return folder.Folder(SQLs)

        if MediaType == "BoxSet":
            return boxsets.BoxSets(self, SQLs)

        if MediaType == "Genre":
            return genre.Genre(self, SQLs)

        if MediaType == "Series":
            return series.Series(self, SQLs)

        if MediaType == "MusicGenre":
            return musicgenre.MusicGenre(self, SQLs)

        if MediaType == "MusicArtist":
            return musicartist.MusicArtist(self, SQLs)

        if MediaType == "Tag":
            return tag.Tag(self, SQLs)

        if MediaType == "Person":
            return person.Person(self, SQLs)

        if MediaType == "Studio":
            return studio.Studio(self, SQLs)

        if MediaType == "Playlist":
            return playlist.Playlist(self, SQLs)


        return None

    def RunJobs(self, IncrementalSync, DropJobs):
        if utils.SystemShutdown or not self.SettingsLoaded or self.JobBusy:
            return False

        if DropJobs:
            self.JobBusy = True
        try:
            UserDataComplete = self.worker_userdata(IncrementalSync) is not False
            Busy = utils.SyncPause.get(self.ServerBusyId, False)
            Complete = not Busy and self.worker_remove(IncrementalSync) and self.worker_update(IncrementalSync)
            if Busy or Complete:
                if self.worker_library_remove():
                    if self.worker_library_add() is False:
                        Complete = False
                else:
                    Complete = False
            UserDataComplete = self.worker_userdata(IncrementalSync) is not False and UserDataComplete
            Complete = bool(Complete and UserDataComplete and not utils.SystemShutdown)
            # Startup owns its final checkpoint and reload; background retries may finish later.
            if Complete and not self.LockKodiStartSync.locked():
                self.finish_first_sync()
            return Complete
        finally:
            self.JobBusy = False

    # Select from libraries synced. Either update or repair libraries.
    # Send event back to service.py
    def select_libraries(self, mode):
        LibrariesSelected = ()
        LibrariesSelectedIds = ()
        cache.reset()
        embydb = dbio.DBOpenRO(self.ServerData['ServerId'], self.SelectLibrariesId)

        if mode in ('RepairLibrarySelection', 'RemoveLibrarySelection', 'UpdateLibrarySelection'):
            PendingSyncRemoved = embydb.get_LibraryRemove_EmbyLibraryIds()

            for LibrarySyncedId, LibrarySyncedName, _, _ in self.LibrarySynced:
                if LibrarySyncedName != "shared" and LibrarySyncedId not in PendingSyncRemoved:
                    if LibrarySyncedId not in LibrariesSelectedIds:
                        LibrariesSelectedIds += (LibrarySyncedId,)
                        LibrariesSelected += ({'Id': LibrarySyncedId, 'Name': LibrarySyncedName},)
        else: # AddLibrarySelection
            AvailableLibs = copy.Object(self.Views.ViewItems)
            PendingSyncAdded = embydb.get_LibraryAdd_EmbyLibraryIds()

            for AvailableLibId, AvailableLib in list(AvailableLibs.items()):
                if AvailableLib[1] in ("movies", "musicvideos", "tvshows", "music", "audiobooks", "podcasts", "mixed", "homevideos", "playlists") and AvailableLibId not in self.LibrarySyncedNames and AvailableLibId not in PendingSyncAdded:
                    LibrariesSelected += ({'Id': AvailableLibId, 'Name': AvailableLib[0]},)

        SelectionMenu = [x['Name'] for x in LibrariesSelected]
        SelectionMenu.insert(0, utils.Translate(33121))

        if mode == 'RepairLibrarySelection':
            Text = utils.Translate(33432)
        elif mode == 'RemoveLibrarySelection':
            Text = utils.Translate(33434)
        elif mode == 'UpdateLibrarySelection':
            Text = utils.Translate(33433)
        elif mode == 'AddLibrarySelection':
            Text = utils.Translate(33120)
        else:
            dbio.DBCloseRO(self.ServerData['ServerId'], self.SelectLibrariesId)
            return

        Selections = utils.Dialog.multiselect(Text, SelectionMenu)

        if not Selections:
            dbio.DBCloseRO(self.ServerData['ServerId'], self.SelectLibrariesId)
            return

        # "All" selected
        if 0 in Selections:
            Selections = list(range(1, len(LibrariesSelected) + 1))

        utils.close_dialog(10146) # addoninformation
        LibraryIdsRemove = ()
        LibraryRemoveItems = ()
        LibraryIdsAdd = ()

        if mode in ('AddLibrarySelection', 'UpdateLibrarySelection'):
            for x in Selections:
                LibraryIdsAdd += (LibrariesSelected[x - 1]['Id'],)
        elif mode == 'RepairLibrarySelection':
            for x in Selections:
                LibraryRemoveItems += (LibrariesSelected[x - 1],)
                LibraryIdsRemove += (LibrariesSelected[x - 1]['Id'],)
                LibraryIdsAdd += (LibrariesSelected[x - 1]['Id'],)
        elif mode == 'RemoveLibrarySelection':
            for x in Selections:
                LibraryRemoveItems += (LibrariesSelected[x - 1],)
                LibraryIdsRemove += (LibrariesSelected[x - 1]['Id'],)

        dbio.DBCloseRO(self.ServerData['ServerId'], self.SelectLibrariesId)
        SQLs = self.open_EmbyDBRW(self.SelectLibrariesId, True)

        if LibraryRemoveItems:
            # detect shared content type
            removeGlobalVideoContent = True

            for LibrarySyncedId, _, LibrarySyncedEmbyType, _ in self.LibrarySynced:
                if LibrarySyncedId not in LibraryIdsRemove + ('999999999', '999999998') and LibrarySyncedEmbyType in ('Movie', 'Series', 'Video', 'MusicVideo'):
                    removeGlobalVideoContent = False
                    break

            if removeGlobalVideoContent:
                SQLs["emby"].remove_LibrarySynced("999999999")
                SQLs["emby"].add_LibraryRemove("999999999", "Person")
                SQLs["emby"].remove_LibrarySynced("999999998")
                SQLs["emby"].add_LibraryRemove("999999998", "Video")

            # Remove libraries
            for LibraryIdRemove in LibraryRemoveItems:
                SQLs["emby"].remove_LibrarySynced(LibraryIdRemove["Id"])
                SQLs["emby"].add_LibraryRemove(LibraryIdRemove["Id"], LibraryIdRemove["Name"])

            self.load_LibrarySynced(SQLs)

        if LibraryIdsAdd:
            # detect shared content type
            syncGlobalVideoContent = False

            for LibraryIdAdd in LibraryIdsAdd:
                if LibraryIdAdd in self.Views.ViewItems:
                    ViewData = self.Views.ViewItems[LibraryIdAdd]

                    if ViewData[1] in ('movies', 'tvshows', 'mixed', 'musicvideos'):
                        syncGlobalVideoContent = True
                        break

            for LibrarySyncedId, _, LibrarySyncedEmbyType, _ in self.LibrarySynced:
                if LibrarySyncedId == "999999999" and LibrarySyncedEmbyType == "Person":
                    syncGlobalVideoContent = False

            if syncGlobalVideoContent:
                # Keep the shared scope for retained people's deltas, without a global preload.
                SQLs["emby"].add_LibraryAdd("999999999", "shared", "Person", "video")

            # Add libraries
            for LibraryId in LibraryIdsAdd:
                if LibraryId in self.Views.ViewItems:
                    ViewData = self.Views.ViewItems[LibraryId]
                    library_type = ViewData[1]
                    library_name = ViewData[0]

                    # content specific libraries
                    if library_type == 'mixed':
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "MusicGenre", "video,music")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "MusicArtist", "video,music")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Genre", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Tag", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Studio", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Movie", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Video", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Series", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Season", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Episode", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "MusicVideo", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "MusicAlbum", "music")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Audio", "music")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "BoxSet", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Folder", "none")
                    elif library_type == 'movies':
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Genre", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Tag", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Movie", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "BoxSet", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Folder", "none")
                    elif library_type == 'musicvideos':
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "MusicGenre", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "MusicArtist", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Tag", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "MusicVideo", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "BoxSet", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Folder", "none")
                    elif library_type == 'homevideos':
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Genre", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Tag", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Video", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "BoxSet", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Folder", "none")
                    elif library_type == 'tvshows':
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Tag", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Studio", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Genre", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Series", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Season", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Episode", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "BoxSet", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Folder", "none")
                    elif library_type in ('music', 'audiobooks', 'podcasts'):
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "MusicGenre", "music")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "MusicArtist", "music")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "MusicAlbum", "music")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Audio", "music")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Folder", "none")
                    elif library_type == 'playlists':
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Studio", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "MusicGenre", "video,music")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "MusicArtist", "video,music")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "MusicAlbum", "music")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Genre", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Tag", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Series", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Season", "video")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "MusicAlbum", "music")
                        SQLs["emby"].add_LibraryAdd(LibraryId, library_name, "Playlist", "video,music")

                    xbmc.log(f"EMBY.database.library: Queued Emby library {LibraryId} for sync", xbmc.LOGINFO)
                else:
                    xbmc.log(f"EMBY.database.library: Requested Emby library {LibraryId} was not found", xbmc.LOGWARNING)

        self.close_EmbyDBRW(self.SelectLibrariesId, SQLs)

        if LibraryIdsRemove:
            utils.start_thread(self.worker_library_remove, ())

        if LibraryIdsAdd and not LibraryIdsRemove:
            utils.start_thread(self.worker_library_add, ())

    def refresh_boxsets(self):  # threaded by caller
        utils.close_dialog(10146) # addoninformation
        SQLs = self.open_EmbyDBRW("refresh_boxsets", False)

        for LibrarySyncedLibraryId, LibrarySyncedLibraryName, LibrarySyncedEmbyType, _ in self.LibrarySynced:
            if LibrarySyncedEmbyType == "BoxSet":
                items = SQLs["emby"].get_boxsets()

                for item in items:
                    SQLs["emby"].add_RemoveItem(item[0], LibrarySyncedLibraryId)

                SQLs["emby"].add_LibraryAdd(LibrarySyncedLibraryId, LibrarySyncedLibraryName, "BoxSet", "video")

        self.close_EmbyDBRW("refresh_boxsets", SQLs)
        self.worker_remove(False)
        self.worker_library_add()

    # Add item_id to userdata queue
    def userdata(self, Items, IncrementalSync, ProcessUpdates=True):  # threaded by caller -> websocket via monitor

        # WebSocket events omit the type; the worker resolves it from the local mapping.
        Items = tuple(Item for Item in (Items or ()) if Item[1] is None or Item[1] in utils.FavoriteTypes)

        if Items:
            self.write_EmbyDB("userdata", lambda EmbyDB: EmbyDB.add_Userdatas(Items))

            if ProcessUpdates:
                self.worker_userdata(IncrementalSync)

    # Add item_id to updated queue
    def updated(self, Items, IncrementalSync, ProcessUpdates=True):  # threaded by caller

        if Items:
            self.write_EmbyDB("updated", lambda EmbyDB: EmbyDB.add_UpdateItems(Items))

            if ProcessUpdates:
                if not utils.SyncPause.get(self.ServerBusyId, False):
                    self.worker_update(IncrementalSync)

    # Add item_id to removed queue
    def removed(self, Ids, IncrementalSync, ProcessUpdates=True):  # threaded by caller

        if Ids:
            self.write_EmbyDB("removed", lambda EmbyDB: EmbyDB.add_RemoveItems_EmbyId(Ids))

            if ProcessUpdates:
                if not utils.SyncPause.get(self.ServerBusyId, False):
                    self.worker_remove(IncrementalSync)

    # Add item_id to removed queue

    def Worker_is_paused(self, WorkerId):
        for Key, Busy in list(utils.SyncPause.items()):
            if Busy:
                if WorkerId.endswith("remove") and Key == self.ServerBusyId: # Continue removes, even emby server is busy
                    continue

                if Key.endswith("server_busy") and Key != self.ServerBusyId:
                    continue

                if Key.endswith("server_starting") and Key != self.ServerStartingId:
                    continue

                if Key.endswith("database_init") and Key != self.ServerDatabaseInitId:
                    continue

                if Key.endswith("server_reconnecting") and Key != self.ServerReconnectingId:
                    continue


                if Key.endswith("server_startscync") and Key != self.ServerStartSyncId:
                    continue

                return True

        return False


    def ItemsSort(self, GeneratorFunction, SQLs, Items, Reverse, RecordsPercent):
        SortItems = {'Movie': set(), 'Video': set(), 'BoxSet': set(), 'MusicVideo': set(), 'Series': set(), 'Episode': set(), 'MusicAlbum': set(), 'MusicArtist': set(), 'AlbumArtist': set(), 'Season': set(), 'Folder': set(), 'Audio': set(), 'Genre': set(), 'MusicGenre': set(), 'Tag': set(), 'Person': set(), 'Studio': set(), 'Playlist': set()}
        Others = set()
        ReleaseCounter = 0

        for Valid, Item in GeneratorFunction(SQLs, Items, RecordsPercent):
            ReleaseCounter += 1

            if ReleaseCounter % 100 == 0:
                xbmc.sleep(0) # release GIL

            if not Item:
                continue

            if Valid:

                if Item['Type'] in SortItems:
                    SortItems[Item['Type']].add(json.dumps(Item)) # Dict is not hashable (not possible adding "dict" to "set") -> convert to json string necessary
                else: # e.g. PlaceHolder
                    xbmc.log(f"EMBY.database.library: Unsupported item type: {Item['Type']}", xbmc.LOGDEBUG)
                    Others.add(json.dumps(Item))
            else:
                Others.add(json.dumps(Item))
                continue

        if Reverse: # on remove, reverse sort order
            return {"video": [SortItems['Person'], SortItems['Studio'], SortItems['Genre'], SortItems['Tag'], SortItems['BoxSet'], SortItems['Video'], SortItems['Movie'], SortItems['Episode'], SortItems['Season'], SortItems['Series']], "music,video": [SortItems['MusicGenre'], SortItems['Audio'], SortItems['MusicVideo'], SortItems['MusicAlbum'], SortItems['MusicArtist'], SortItems['Playlist']], "none": [SortItems['Folder']]}, Others

        return {"video": [SortItems['Person'], SortItems['Studio'], SortItems['Genre'], SortItems['Tag'], SortItems['Series'], SortItems['Season'], SortItems['Episode'], SortItems['Movie'], SortItems['Video'], SortItems['BoxSet']], "music,video": [SortItems['MusicGenre'], SortItems['MusicArtist'], SortItems['MusicAlbum'], SortItems['MusicVideo'], SortItems['Audio'], SortItems['Playlist']], "none": [SortItems['Folder']]}, Others


def content_available(CategoryItems):
    for CategoryItem in CategoryItems:
        if CategoryItem:
            return True

    return False


def get_content_database(KodiDBs, Items, RefreshVideo, RefreshAudio):
    if Items:
        if KodiDBs.find("music") != -1:
            RefreshAudio = True

        if KodiDBs.find("video") != -1:
            RefreshVideo = True

    return RefreshVideo, RefreshAudio
