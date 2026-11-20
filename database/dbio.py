import sqlite3
import threading
import xbmcvfs
import xbmc
from helper import utils
from . import emby_db, video_db, music_db, texture_db

DBConnectionsRW = {}
DBConnectionsRO = {}

def DBVacuum():
    utils.close_dialog(10146) # addoninformation
    utils.create_ProgressBar("DBVacuum", utils.Translate(33199), utils.Translate(33436))
    TotalItems = max(len(utils.DatabaseFiles), 1) / 100
    try:
        for Index, (DBID, DBFile) in enumerate(list(utils.DatabaseFiles.items()), 1):
            utils.update_ProgressBar("DBVacuum", Index / TotalItems, utils.Translate(33436), str(DBID))
            if 'version' in DBID or not xbmcvfs.exists(DBFile):
                continue
            State = DBConnectionsRW.setdefault(DBID, [None, None, threading.Condition(threading.Lock()), False])
            with utils.SafeLock(State[2]):
                while State[3]:
                    if utils.SystemShutdown:
                        return
                    State[2].wait(timeout=0.1)
                if utils.SystemShutdown:
                    return
                State[3] = True
                try:
                    State[0] = sqlite3.connect(DBFile, timeout=5)
                    State[1] = State[0].cursor()
                    if DBID == "music":
                        State[1].execute("DELETE FROM removed_link")
                        State[0].commit()
                    # Keep the existing journal mode even if VACUUM is interrupted.
                    State[0].execute("VACUUM")
                    State[0].execute("ANALYZE")
                    State[0].commit()
                finally:
                    try:
                        if State[1]:
                            State[1].close()
                    finally:
                        try:
                            if State[0]:
                                State[0].close()
                        finally:
                            State[0] = State[1] = None
                            State[3] = False
                            State[2].notify_all()
    finally:
        utils.close_ProgressBar("DBVacuum")


def DBOpenRO(DBID, TaskId, Timeout=999999):
    DBIDThreadID = f"{DBID}{TaskId}{threading.get_ident()}"
    DBConnectionsRO[DBIDThreadID] = [sqlite3.connect(f"file:{utils.DatabaseFiles[DBID]}?mode=ro", uri=True, timeout=Timeout, check_same_thread=False), None]
    DBConnectionsRO[DBIDThreadID][1] = DBConnectionsRO[DBIDThreadID][0].cursor()
    DBConnectionsRO[DBIDThreadID][0].execute("PRAGMA temp_store=MEMORY")

    if DBID == 'video':
        return video_db.VideoDatabase(DBConnectionsRO[DBIDThreadID][1])

    if DBID == 'music':
        return music_db.MusicDatabase(DBConnectionsRO[DBIDThreadID][1])

    if DBID == 'texture':
        return texture_db.TextureDatabase(DBConnectionsRO[DBIDThreadID][1])


    return emby_db.EmbyDatabase(DBConnectionsRO[DBIDThreadID][1])

def DBCloseRO(DBID, TaskId):
    DBIDThreadID = f"{DBID}{TaskId}{threading.get_ident()}"

    if DBIDThreadID in DBConnectionsRO:
        DBConnectionsRO[DBIDThreadID][1].close()
        DBConnectionsRO[DBIDThreadID][0].close()
        DBConnectionsRO[DBIDThreadID] = [None, None]
    else:
        xbmc.log(f"EMBY.database.dbio: DBIDThreadID not found {DBIDThreadID}", xbmc.LOGERROR)

def DBOpenRW(Databases, TaskId, SQLs, *, AllowDuringShutdown=False):
    Opened = []
    try:
        # All callers acquire multiple Kodi databases in the same order.
        for DBID in sorted(set(Databases.split(",")), key=lambda Id: (Id in ('video', 'music', 'texture'), Id)):
            if DBID not in utils.DatabaseFiles:
                continue
            State = DBConnectionsRW.setdefault(DBID, [None, None, threading.Condition(threading.Lock()), False])
            with utils.SafeLock(State[2]):
                while State[3]:
                    if utils.SystemShutdown and not AllowDuringShutdown:
                        raise InterruptedError("Database open cancelled")
                    State[2].wait(timeout=0.1)
                if utils.SystemShutdown and not AllowDuringShutdown:
                    raise InterruptedError("Database open cancelled")
                State[3] = True
                Opened.append(DBID)
                for Attempt in range(50):
                    if utils.SystemShutdown and not AllowDuringShutdown:
                        raise InterruptedError("Database open cancelled")
                    try:
                        State[0] = sqlite3.connect(utils.DatabaseFiles[DBID], timeout=0.1, check_same_thread=False)
                        State[1] = State[0].cursor()
                        State[0].execute("PRAGMA temp_store=MEMORY")
                        State[0].execute("PRAGMA journal_mode=WAL")
                        State[0].execute("PRAGMA synchronous=NORMAL")
                        State[0].execute("PRAGMA secure_delete=OFF")
                        State[1].execute("BEGIN IMMEDIATE TRANSACTION")
                        break
                    except sqlite3.OperationalError as Error:
                        if State[1]:
                            State[1].close()
                        if State[0]:
                            State[0].close()
                        State[0] = State[1] = None
                        Code = getattr(Error, "sqlite_errorcode", 0) & 255
                        Busy = Code in (5, 6) or str(Error).lower() in ("database is locked", "database table is locked")
                        if not Busy or Attempt == 49:
                            raise
                        xbmc.sleep(100)
                if DBID == 'video':
                    SQLs[DBID] = video_db.VideoDatabase(State[1])
                elif DBID == 'music':
                    SQLs[DBID] = music_db.MusicDatabase(State[1])
                elif DBID == 'texture':
                    SQLs[DBID] = texture_db.TextureDatabase(State[1])
                else:
                    SQLs["emby"] = emby_db.EmbyDatabase(State[1])
    except Exception:
        # Only release connections acquired by this call; earlier caller-owned DBs survive.
        DBCloseRW(",".join(Opened), TaskId, SQLs, Commit=False)
        raise


def DBCloseRW(Databases, TaskId, SQLs, Commit=True):
    Error = None
    for DBID in Databases.split(","):
        State = DBConnectionsRW.get(DBID)
        if not State:
            continue
        with utils.SafeLock(State[2]):
            Connection, Cursor = State[:2]
            Database = SQLs.get("emby") if DBID not in ('video', 'music', 'texture') else None
            Files = getattr(Database, "PlaylistFiles", None)
            Committed = False
            try:
                if Connection:
                    if Commit and Error is None:
                        Connection.commit()
                        Committed = True
                        if getattr(Database, "PendingPlaylistDeletes", None):
                            try:
                                Database.delete_pending_playlist_files()
                            except Exception as Failure:
                                # The mapping is durable; failed cleanup may leave an unused file.
                                xbmc.log(f"EMBY.database.dbio: Playlist file cleanup failed: {type(Failure).__name__}", xbmc.LOGWARNING)
                    else:
                        Connection.rollback()
            except Exception as Failure:
                Error = Error or Failure
            finally:
                if Files:
                    try:
                        Files.close(Committed)
                    except Exception as Failure:
                        if not Committed:
                            Error = Error or Failure
                        else:
                            xbmc.log(f"EMBY.database.dbio: Playlist backup cleanup failed: {type(Failure).__name__}", xbmc.LOGWARNING)
                # Closing an uncommitted sqlite connection rolls its transaction back.
                for Resource in (Cursor, Connection):
                    if Resource:
                        try:
                            Resource.close()
                        except Exception as Failure:
                            Error = Error or Failure
                SQLs[DBID if DBID in ('video', 'music', 'texture') else 'emby'] = None
                State[0] = State[1] = None
                State[3] = False
                State[2].notify_all()
    if Error is not None:
        raise Error
