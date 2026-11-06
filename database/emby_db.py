import xbmc
from helper import utils, versions
from . import common_db

EmbyTypes = ("Movie", "Series", "Season", "Episode", "Audio", "MusicAlbum", "MusicArtist", "Genre", "MusicGenre", "Video", "MusicVideo", "BoxSet", "Tag", "Studio", "Playlist", "Person", "Folder")
EmbyFolderTypes = ("Series", "Season", "MusicAlbum", "MusicArtist", "Genre", "MusicGenre", "BoxSet", "Tag", "Studio", "Playlist", "Person", "Folder")
EmbyTypesWithKodiId = ("Movie", "Series", "Season", "Episode", "Audio", "MusicAlbum", "MusicArtist", "Genre", "MusicGenre", "Video", "MusicVideo", "BoxSet", "Tag", "Studio", "Playlist", "Person")

MovieTmdbMigrationVersion = 1

class EmbyDatabase:
    def __init__(self, cursor):
        self.cursor = cursor
        self.common_db = common_db.CommonDatabase(cursor)
        self.PendingPlaylistDeletes = {}
        self.PlaylistFiles = None
        self.MovieResumeOwnerPresence = {}

    def write_playlist_file(self, Path, Data):
        if self.PlaylistFiles is None:
            self.PlaylistFiles = utils.PlaylistFileTransaction()
        self.PlaylistFiles.write(Path, Data)

    def queue_playlist_file_delete(self, EmbyId, KodiId, Path):
        self.PendingPlaylistDeletes[Path] = (EmbyId, KodiId)

    def delete_pending_playlist_files(self):
        # Called only after this connection's transaction has committed.
        for Path, (EmbyId, KodiId) in self.PendingPlaylistDeletes.items():
            self.cursor.execute("SELECT KodiId FROM Playlist WHERE EmbyId = ?", (EmbyId,))
            Row = self.cursor.fetchone()
            # A later update in the same transaction may have restored this variant.
            if not Row or KodiId not in (Row[0] or "").split(";"):
                utils.delFile(Path)
        self.PendingPlaylistDeletes.clear()

    def init_EmbyDB(self):
        Invalid = False

        # Table
        try:
            self.cursor.execute("CREATE TABLE IF NOT EXISTS Genre (EmbyId INTEGER PRIMARY KEY, KodiId INTEGER, EmbyFavourite BOOL, EmbyArtwork TEXT COLLATE NOCASE) WITHOUT ROWID")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS Studio (EmbyId INTEGER PRIMARY KEY, KodiId INTEGER, EmbyFavourite BOOL, EmbyArtwork TEXT COLLATE NOCASE) WITHOUT ROWID")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS Tag (EmbyId INTEGER PRIMARY KEY, KodiId INTEGER, EmbyFavourite BOOL, Memo TEXT COLLATE NOCASE, EmbyArtwork TEXT COLLATE NOCASE) WITHOUT ROWID")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS Person (EmbyId INTEGER PRIMARY KEY, KodiId INTEGER, EmbyFavourite BOOL) WITHOUT ROWID")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS Folder (EmbyId INTEGER PRIMARY KEY, EmbyFolder TEXT COLLATE NOCASE, EmbyMetaData TEXT COLLATE NOCASE) WITHOUT ROWID")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS Movie (EmbyId INTEGER PRIMARY KEY, KodiId INTEGER, EmbyFavourite BOOL, KodiFileId INTEGER, EmbyPresentationKey TEXT COLLATE NOCASE, EmbyFolder TEXT COLLATE NOCASE, KodiPathId INTEGER, TmdbId TEXT) WITHOUT ROWID")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS ResumeOwner (UserId TEXT, MediaType TEXT, Provider TEXT, ProviderId TEXT, EmbyId INTEGER, RetiredEmbyId INTEGER, PRIMARY KEY(UserId, MediaType, Provider, ProviderId)) WITHOUT ROWID")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS Video (EmbyId INTEGER PRIMARY KEY, KodiId INTEGER, EmbyFavourite BOOL, KodiFileId INTEGER, EmbyPresentationKey TEXT COLLATE NOCASE, EmbyFolder TEXT COLLATE NOCASE, KodiPathId INTEGER, EmbyParentId INTEGER) WITHOUT ROWID")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS BoxSet (EmbyId INTEGER PRIMARY KEY, KodiId INTEGER, EmbyFavourite BOOL, KodiParentId TEXT COLLATE NOCASE) WITHOUT ROWID")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS Series (EmbyId INTEGER PRIMARY KEY, KodiId INTEGER, EmbyFavourite BOOL, EmbyPresentationKey TEXT COLLATE NOCASE, KodiPathId INTEGER) WITHOUT ROWID")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS Season (EmbyId INTEGER PRIMARY KEY, KodiId INTEGER, EmbyFavourite BOOL, KodiParentId INTEGER, EmbyPresentationKey TEXT COLLATE NOCASE) WITHOUT ROWID")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS Episode (EmbyId INTEGER PRIMARY KEY, KodiId INTEGER, EmbyFavourite BOOL, KodiFileId INTEGER, KodiParentId INTEGER, EmbyPresentationKey TEXT COLLATE NOCASE, EmbyFolder TEXT COLLATE NOCASE, KodiPathId INTEGER) WITHOUT ROWID")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS MusicArtist (EmbyId INTEGER PRIMARY KEY, KodiId TEXT COLLATE NOCASE, EmbyFavourite BOOL, LibraryIds TEXT COLLATE NOCASE) WITHOUT ROWID")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS MusicGenre (EmbyId INTEGER PRIMARY KEY, KodiId TEXT COLLATE NOCASE, EmbyFavourite BOOL, LibraryIds TEXT COLLATE NOCASE, EmbyArtwork TEXT COLLATE NOCASE) WITHOUT ROWID")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS MusicVideo (EmbyId INTEGER PRIMARY KEY, KodiId TEXT COLLATE NOCASE, EmbyFavourite BOOL, KodiFileId TEXT COLLATE NOCASE, EmbyPresentationKey TEXT COLLATE NOCASE, EmbyFolder TEXT COLLATE NOCASE, KodiPathId TEXT COLLATE NOCASE, LibraryIds TEXT COLLATE NOCASE) WITHOUT ROWID")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS MusicAlbum (EmbyId INTEGER PRIMARY KEY, KodiId TEXT COLLATE NOCASE, EmbyFavourite BOOL, LibraryIds TEXT COLLATE NOCASE) WITHOUT ROWID")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS Audio (EmbyId INTEGER PRIMARY KEY, KodiId TEXT COLLATE NOCASE, EmbyFavourite BOOL, EmbyFolder TEXT COLLATE NOCASE, KodiPathId INTEGER, LibraryIds TEXT COLLATE NOCASE, EmbyParentId INTEGER) WITHOUT ROWID")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS Playlist (EmbyId INTEGER PRIMARY KEY, KodiId TEXT COLLATE NOCASE, EmbyFavourite BOOL, EmbyArtwork TEXT COLLATE NOCASE, EmbyLinkedId TEXT COLLATE NOCASE, Name TEXT COLLATE NOCASE) WITHOUT ROWID")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS MediaSources (EmbyId INTEGER, MediaSourceId TEXT COLLATE NOCASE, Path TEXT COLLATE NOCASE, Name TEXT COLLATE NOCASE, Size INTEGER, IntroStart INTEGER, IntroEnd INTEGER, CreditsStart INTEGER, PRIMARY KEY(EmbyId, MediaSourceId))")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS VideoStreams (EmbyId INTEGER, MediaSourceId TEXT COLLATE NOCASE, EmbyIndex INTEGER, Codec TEXT COLLATE NOCASE, BitRate INTEGER, Width INTEGER, KodiIndex INTEGER, PRIMARY KEY(EmbyId, MediaSourceId, EmbyIndex))")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS AudioStreams (EmbyId INTEGER, MediaSourceId TEXT COLLATE NOCASE, EmbyIndex INTEGER, DisplayTitle TEXT COLLATE NOCASE, Codec TEXT COLLATE NOCASE, BitRate INTEGER, KodiIndex INTEGER, PRIMARY KEY(EmbyId, MediaSourceId, EmbyIndex))")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS SubtitleStreams (EmbyId INTEGER, MediaSourceId TEXT COLLATE NOCASE, EmbyIndex INTEGER, Codec TEXT COLLATE NOCASE, Language TEXT COLLATE NOCASE, DisplayTitle TEXT COLLATE NOCASE, External BOOL, KodiIndex INTEGER, PRIMARY KEY(EmbyId, MediaSourceId, EmbyIndex))")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS RemoveItems (EmbyId INTEGER, EmbyLibraryId TEXT COLLATE NOCASE, PRIMARY KEY (EmbyId, EmbyLibraryId))")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS UpdateItems (EmbyId INTEGER, EmbyRequestContent TEXT COLLATE NOCASE, EmbyLibraryId TEXT COLLATE NOCASE, KodiDB TEXT COLLATE NOCASE, PRIMARY KEY(EmbyId, KodiDB))")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS UserdataItems (EmbyId INTEGER PRIMARY KEY, EmbyType TEXT COLLATE NOCASE, EmbyPlaybackPositionTicks INT, EmbyPlayCount INT, EmbyIsFavorite BOOL, EmbyPlayed BOOL, EmbyLastPlayedDate TEXT COLLATE NOCASE, PlayedPercentage INT, UnplayedItemCount INT) WITHOUT ROWID")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS LibrarySynced (EmbyLibraryId TEXT COLLATE NOCASE, EmbyLibraryName TEXT COLLATE NOCASE, EmbyType TEXT COLLATE NOCASE, KodiDBs TEXT COLLATE NOCASE, PRIMARY KEY(EmbyLibraryId, EmbyLibraryName, EmbyType))")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS LibrarySyncedMirrow (EmbyLibraryId TEXT COLLATE NOCASE, EmbyLibraryName TEXT COLLATE NOCASE, EmbyType TEXT COLLATE NOCASE, KodiDBs TEXT COLLATE NOCASE, PRIMARY KEY(EmbyLibraryId, EmbyLibraryName, EmbyType))")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS LastIncrementalSync (Date TEXT)")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS LastIncrementalSyncStart (Date TEXT)")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS LibraryAdd (EmbyLibraryId TEXT COLLATE NOCASE, EmbyLibraryName TEXT COLLATE NOCASE, EmbyType TEXT COLLATE NOCASE, KodiDBs TEXT COLLATE NOCASE, PRIMARY KEY(EmbyLibraryId, EmbyLibraryName, EmbyType, KodiDBs))")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS LibraryRemove (EmbyLibraryId TEXT COLLATE NOCASE PRIMARY KEY, EmbyLibraryName TEXT COLLATE NOCASE)")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS EmbyLibraryMapping (EmbyLibraryId TEXT COLLATE NOCASE, EmbyId INTEGER, EmbyMusicAlbumId INTEGER NOT NULL DEFAULT 0, EmbyMusicArtistId INTEGER NOT NULL DEFAULT 0, EmbyMusicGenreId INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (EmbyLibraryId, EmbyId, EmbyMusicAlbumId, EmbyMusicArtistId, EmbyMusicGenreId))")

            # Verify tables
            self.cursor.execute("SELECT name FROM pragma_table_info('Genre')")
            Cols = self.cursor.fetchall()

            if Cols != [('EmbyId',), ('KodiId',), ('EmbyFavourite',), ('EmbyArtwork',)]:
                Invalid = True

            self.cursor.execute("SELECT name FROM pragma_table_info('Studio')")
            Cols = self.cursor.fetchall()

            if Cols != [('EmbyId',), ('KodiId',), ('EmbyFavourite',), ('EmbyArtwork',)]:
                Invalid = True

            self.cursor.execute("SELECT name FROM pragma_table_info('Tag')")
            Cols = self.cursor.fetchall()

            if Cols != [('EmbyId',), ('KodiId',), ('EmbyFavourite',), ('Memo',), ('EmbyArtwork',)]:
                Invalid = True

            self.cursor.execute("SELECT name FROM pragma_table_info('Person')")
            Cols = self.cursor.fetchall()

            if Cols != [('EmbyId',), ('KodiId',), ('EmbyFavourite',)]:
                Invalid = True

            self.cursor.execute("SELECT name FROM pragma_table_info('Folder')")
            Cols = self.cursor.fetchall()

            if Cols != [('EmbyId',), ('EmbyFolder',), ('EmbyMetaData',)]:
                Invalid = True

            self.cursor.execute("SELECT name FROM pragma_table_info('Movie')")
            Cols = self.cursor.fetchall()

            MovieColumns = [('EmbyId',), ('KodiId',), ('EmbyFavourite',), ('KodiFileId',), ('EmbyPresentationKey',), ('EmbyFolder',), ('KodiPathId',)]
            if Cols == MovieColumns:
                self.cursor.execute("ALTER TABLE Movie ADD COLUMN TmdbId TEXT")
            elif Cols != MovieColumns + [('TmdbId',)]:
                Invalid = True

            self.cursor.execute("SELECT name FROM pragma_table_info('Video')")
            Cols = self.cursor.fetchall()

            if Cols != [('EmbyId',), ('KodiId',), ('EmbyFavourite',), ('KodiFileId',), ('EmbyPresentationKey',), ('EmbyFolder',), ('KodiPathId',), ('EmbyParentId',)]:
                Invalid = True

            self.cursor.execute("SELECT name FROM pragma_table_info('BoxSet')")
            Cols = self.cursor.fetchall()

            if Cols != [('EmbyId',), ('KodiId',), ('EmbyFavourite',), ('KodiParentId',)]:
                Invalid = True

            self.cursor.execute("SELECT name FROM pragma_table_info('Series')")
            Cols = self.cursor.fetchall()

            if Cols != [('EmbyId',), ('KodiId',), ('EmbyFavourite',), ('EmbyPresentationKey',), ('KodiPathId',)]:
                Invalid = True

            self.cursor.execute("SELECT name FROM pragma_table_info('Season')")
            Cols = self.cursor.fetchall()

            if Cols != [('EmbyId',), ('KodiId',), ('EmbyFavourite',), ('KodiParentId',), ('EmbyPresentationKey',)]:
                Invalid = True

            self.cursor.execute("SELECT name FROM pragma_table_info('Episode')")
            Cols = self.cursor.fetchall()

            if Cols != [('EmbyId',), ('KodiId',), ('EmbyFavourite',), ('KodiFileId',), ('KodiParentId',), ('EmbyPresentationKey',), ('EmbyFolder',), ('KodiPathId',)]:
                Invalid = True

            self.cursor.execute("SELECT name FROM pragma_table_info('MusicArtist')")
            Cols = self.cursor.fetchall()

            if Cols != [('EmbyId',), ('KodiId',), ('EmbyFavourite',), ('LibraryIds',)]:
                Invalid = True

            self.cursor.execute("SELECT name FROM pragma_table_info('MusicGenre')")
            Cols = self.cursor.fetchall()

            if Cols != [('EmbyId',), ('KodiId',), ('EmbyFavourite',), ('LibraryIds',), ('EmbyArtwork',)]:
                Invalid = True

            self.cursor.execute("SELECT name FROM pragma_table_info('MusicVideo')")
            Cols = self.cursor.fetchall()

            if Cols != [('EmbyId',), ('KodiId',), ('EmbyFavourite',), ('KodiFileId',), ('EmbyPresentationKey',), ('EmbyFolder',), ('KodiPathId',), ('LibraryIds',)]:
                Invalid = True

            self.cursor.execute("SELECT name FROM pragma_table_info('MusicAlbum')")
            Cols = self.cursor.fetchall()

            if Cols != [('EmbyId',), ('KodiId',), ('EmbyFavourite',), ('LibraryIds',)]:
                Invalid = True

            self.cursor.execute("SELECT name FROM pragma_table_info('Audio')")
            Cols = self.cursor.fetchall()

            if Cols != [('EmbyId',), ('KodiId',), ('EmbyFavourite',), ('EmbyFolder',), ('KodiPathId',), ('LibraryIds',), ('EmbyParentId',)]:
                Invalid = True

            self.cursor.execute("SELECT name FROM pragma_table_info('Playlist')")
            Cols = self.cursor.fetchall()

            if Cols != [('EmbyId',), ('KodiId',), ('EmbyFavourite',), ('EmbyArtwork',), ('EmbyLinkedId',), ('Name',)]:
                Invalid = True

            self.cursor.execute("SELECT name FROM pragma_table_info('MediaSources')")
            Cols = self.cursor.fetchall()

            if Cols != [('EmbyId',), ('MediaSourceId',), ('Path',), ('Name',), ('Size',), ('IntroStart',), ('IntroEnd',), ('CreditsStart',)]:
                Invalid = True

            self.cursor.execute("SELECT name FROM pragma_table_info('VideoStreams')")
            Cols = self.cursor.fetchall()

            if Cols != [('EmbyId',), ('MediaSourceId',), ('EmbyIndex',), ('Codec',), ('BitRate',), ('Width',), ('KodiIndex',)]:
                Invalid = True

            self.cursor.execute("SELECT name FROM pragma_table_info('AudioStreams')")
            Cols = self.cursor.fetchall()

            if Cols != [('EmbyId',), ('MediaSourceId',), ('EmbyIndex',), ('DisplayTitle',), ('Codec',), ('BitRate',), ('KodiIndex',)]:
                Invalid = True

            self.cursor.execute("SELECT name FROM pragma_table_info('SubtitleStreams')")
            Cols = self.cursor.fetchall()

            if Cols != [('EmbyId',), ('MediaSourceId',), ('EmbyIndex',), ('Codec',), ('Language',), ('DisplayTitle',), ('External',), ('KodiIndex',)]:
                Invalid = True

            self.cursor.execute("SELECT name FROM pragma_table_info('RemoveItems')")
            Cols = self.cursor.fetchall()

            if Cols != [('EmbyId',), ('EmbyLibraryId',)]:
                Invalid = True

            self.cursor.execute("SELECT name FROM pragma_table_info('UpdateItems')")
            Cols = self.cursor.fetchall()

            if Cols != [('EmbyId',), ('EmbyRequestContent',), ('EmbyLibraryId',), ('KodiDB',)]:
                Invalid = True

            self.cursor.execute("SELECT name FROM pragma_table_info('UserdataItems')")
            Cols = self.cursor.fetchall()

            if Cols != [('EmbyId',), ('EmbyType',), ('EmbyPlaybackPositionTicks',), ('EmbyPlayCount',), ('EmbyIsFavorite',), ('EmbyPlayed',), ('EmbyLastPlayedDate',), ('PlayedPercentage',), ('UnplayedItemCount',)]:
                Invalid = True

            self.cursor.execute("SELECT name FROM pragma_table_info('LibrarySynced')")
            Cols = self.cursor.fetchall()

            if Cols != [('EmbyLibraryId',), ('EmbyLibraryName',), ('EmbyType',), ('KodiDBs',)]:
                Invalid = True

            self.cursor.execute("SELECT name FROM pragma_table_info('LibrarySyncedMirrow')")
            Cols = self.cursor.fetchall()

            if Cols != [('EmbyLibraryId',), ('EmbyLibraryName',), ('EmbyType',), ('KodiDBs',)]:
                Invalid = True

            self.cursor.execute("SELECT name FROM pragma_table_info('LastIncrementalSync')")
            Cols = self.cursor.fetchall()

            if Cols != [('Date',)]:
                Invalid = True

            self.cursor.execute("SELECT name FROM pragma_table_info('LastIncrementalSyncStart')")
            Cols = self.cursor.fetchall()

            if Cols != [('Date',)]:
                Invalid = True

            self.cursor.execute("SELECT name FROM pragma_table_info('LibraryAdd')")
            Cols = self.cursor.fetchall()

            if Cols != [('EmbyLibraryId',), ('EmbyLibraryName',), ('EmbyType',), ('KodiDBs',)]:
                Invalid = True

            self.cursor.execute("SELECT name FROM pragma_table_info('LibraryRemove')")
            Cols = self.cursor.fetchall()

            if Cols != [('EmbyLibraryId',), ('EmbyLibraryName',)]:
                Invalid = True

            self.cursor.execute("SELECT name FROM pragma_table_info('EmbyLibraryMapping')")
            Cols = self.cursor.fetchall()

            if Cols != [('EmbyLibraryId',), ('EmbyId',), ('EmbyMusicAlbumId',), ('EmbyMusicArtistId',), ('EmbyMusicGenreId',)]:
                Invalid = True

            if not Invalid:
                self.add_Index()
        except Exception as Error: # Database invalid! Database reset mandatory
            xbmc.log(f"EMBY.database.emby_db: Cannot initialize the Emby database: {Error}", xbmc.LOGERROR)
            Invalid = True

        if Invalid:
            self.common_db.delete_tables("Emby")
            return False

        return True

    def add_Index(self):
        try: # xbox issue
            SchemaVersion = self.cursor.execute("PRAGMA schema_version").fetchone()[0]
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_EmbyLibraryMapping_EmbyLibraryId on EmbyLibraryMapping (EmbyLibraryId)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_EmbyLibraryMapping_EmbyId_EmbyMusicAlbumId_EmbyMusicArtistId_EmbyMusicGenreId on EmbyLibraryMapping (EmbyId, EmbyMusicAlbumId, EmbyMusicArtistId, EmbyMusicGenreId)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_EmbyLibraryMapping_EmbyMusicAlbumId_EmbyLibraryId on EmbyLibraryMapping (EmbyMusicAlbumId, EmbyLibraryId)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_EmbyLibraryMapping_EmbyMusicArtistId_EmbyLibraryId on EmbyLibraryMapping (EmbyMusicArtistId, EmbyLibraryId)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_EmbyLibraryMapping_EmbyMusicGenreId_EmbyLibraryId on EmbyLibraryMapping (EmbyMusicGenreId, EmbyLibraryId)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_MediaSources_EmbyId on MediaSources (EmbyId)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_MediaSources_Path on MediaSources (Path)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_Movie_EmbyFolder on Movie (EmbyFolder)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_Video_EmbyFolder on Video (EmbyFolder)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_Video_EmbyParentId on Video (EmbyParentId)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_Episode_EmbyFolder on Episode (EmbyFolder)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_MusicVideo_EmbyFolder on MusicVideo (EmbyFolder)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_Audio_EmbyFolder on Audio (EmbyFolder)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_Video_KodiFileId on Video (KodiFileId)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_Tag_Memo on Tag (Memo)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_Audio_EmbyParentId on Audio (EmbyParentId)")
            for Table in ("Movie", "Series", "Season", "Episode"):
                self.cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{Table}_KodiId ON {Table}(KodiId)")
                self.cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{Table}_PresentationKey ON {Table}(EmbyPresentationKey)")
            self.cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_RemoveItems_EmbyId_NullLibrary ON RemoveItems (EmbyId) WHERE EmbyLibraryId IS NULL")
            self.cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_UpdateItems_EmbyId_NullKodiDB ON UpdateItems (EmbyId) WHERE KodiDB IS NULL")
            if self.cursor.execute("PRAGMA schema_version").fetchone()[0] != SchemaVersion:
                self.cursor.execute("ANALYZE")
                self.cursor.connection.commit()
                self.cursor.execute("BEGIN IMMEDIATE TRANSACTION")
        except Exception as Error:
            xbmc.log(f"EMBY.database.emby_db: Database add index error: {Error}", xbmc.LOGERROR)

    def delete_Index(self):
        try: # xbox issue
            for Table in ("Movie", "Series", "Season", "Episode"):
                self.cursor.execute(f"DROP INDEX IF EXISTS idx_{Table}_KodiId")
                self.cursor.execute(f"DROP INDEX IF EXISTS idx_{Table}_PresentationKey")
            self.cursor.execute("DROP INDEX IF EXISTS idx_MediaSources_EmbyId")
            self.cursor.execute("DROP INDEX IF EXISTS idx_MediaSources_Path")
            self.cursor.execute("DROP INDEX IF EXISTS idx_Movie_EmbyFolder")
            self.cursor.execute("DROP INDEX IF EXISTS idx_Video_EmbyFolder")
            self.cursor.execute("DROP INDEX IF EXISTS idx_Video_EmbyParentId")
            self.cursor.execute("DROP INDEX IF EXISTS idx_Episode_EmbyFolder")
            self.cursor.execute("DROP INDEX IF EXISTS idx_MusicVideo_EmbyFolder")
            self.cursor.execute("DROP INDEX IF EXISTS idx_Audio_EmbyFolder")
            self.cursor.execute("DROP INDEX IF EXISTS idx_Video_KodiFileId")
            self.cursor.execute("DROP INDEX IF EXISTS idx_Audio_EmbyParentId")
            self.cursor.execute("DROP INDEX IF EXISTS idx_RemoveItems_EmbyId_NullLibrary")
            self.cursor.execute("DROP INDEX IF EXISTS idx_UpdateItems_EmbyId_NullKodiDB")
            self.cursor.execute("ANALYZE")
            self.cursor.connection.commit()
            self.cursor.execute("BEGIN IMMEDIATE TRANSACTION")
        except Exception as Error:
            xbmc.log(f"EMBY.database.emby_db: Database delete index error: {Error}", xbmc.LOGERROR)

    # LibrarySynced
    def get_LibrarySynced(self):
        self.cursor.execute("SELECT * FROM LibrarySynced")
        return self.cursor.fetchall()

    def add_LibrarySynced(self, EmbyLibraryId, EmbyLibraryName, EmbyType, KodiDBs):
        self.cursor.execute("INSERT OR REPLACE INTO LibrarySynced (EmbyLibraryId, EmbyLibraryName, EmbyType, KodiDBs) VALUES (?, ?, ?, ?)", (EmbyLibraryId, EmbyLibraryName, EmbyType, KodiDBs))

    def remove_LibrarySynced(self, EmbyLibraryId):
        self.cursor.execute("DELETE FROM LibrarySynced WHERE EmbyLibraryId = ?", (EmbyLibraryId,))

    def get_LibrarySyncedMirrow(self):
        self.cursor.execute("SELECT * FROM LibrarySyncedMirrow")
        return self.cursor.fetchall()

    def add_LibrarySyncedMirrow(self, EmbyLibraryId, EmbyLibraryName, EmbyType, KodiDBs):
        self.cursor.execute("INSERT OR REPLACE INTO LibrarySyncedMirrow (EmbyLibraryId, EmbyLibraryName, EmbyType, KodiDBs) VALUES (?, ?, ?, ?)", (EmbyLibraryId, EmbyLibraryName, EmbyType, KodiDBs))

    def remove_LibrarySyncedMirrow(self, EmbyLibraryId):
        self.cursor.execute("DELETE FROM LibrarySyncedMirrow WHERE EmbyLibraryId = ?", (EmbyLibraryId,))

    # LastIncrementalSync
    def get_LastIncrementalSync(self):
        self.cursor.execute("SELECT * FROM LastIncrementalSync")
        Data = self.cursor.fetchone()

        if Data:
            return Data[0]

        return None

    def get_LastIncrementalSyncStart(self):
        self.cursor.execute("SELECT * FROM LastIncrementalSyncStart")
        Data = self.cursor.fetchone()

        if Data:
            return Data[0]

        return None

    def update_LastIncrementalSync(self, LastIncrementalSync):
        self.cursor.execute("DELETE FROM LastIncrementalSync")
        self.cursor.execute("INSERT INTO LastIncrementalSync (Date) VALUES (?)", (LastIncrementalSync,))

    def update_LastIncrementalSyncStart(self, LastIncrementalSyncStart):
        self.cursor.execute("DELETE FROM LastIncrementalSyncStart")
        self.cursor.execute("INSERT INTO LastIncrementalSyncStart (Date) VALUES (?)", (LastIncrementalSyncStart,))

    # UserdataItems
    def add_Userdatas(self, Data):
        self.cursor.executemany("""
            INSERT INTO UserdataItems VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(EmbyId) DO UPDATE SET
                EmbyType = COALESCE(excluded.EmbyType, EmbyType),
                EmbyPlaybackPositionTicks = COALESCE(excluded.EmbyPlaybackPositionTicks, EmbyPlaybackPositionTicks),
                EmbyPlayCount = COALESCE(excluded.EmbyPlayCount, EmbyPlayCount),
                EmbyIsFavorite = COALESCE(excluded.EmbyIsFavorite, EmbyIsFavorite),
                EmbyPlayed = COALESCE(excluded.EmbyPlayed, EmbyPlayed),
                EmbyLastPlayedDate = COALESCE(excluded.EmbyLastPlayedDate, EmbyLastPlayedDate),
                PlayedPercentage = COALESCE(excluded.PlayedPercentage, PlayedPercentage),
                UnplayedItemCount = COALESCE(excluded.UnplayedItemCount, UnplayedItemCount)
        """, Data)

    def has_Userdata(self):
        self.cursor.execute("SELECT EXISTS(SELECT 1 FROM UserdataItems)")
        return bool(self.cursor.fetchone()[0])

    def get_Userdata(self):
        self.cursor.execute("SELECT * FROM UserdataItems")
        return self.cursor.fetchall()

    def delete_Userdata(self, EmbyId):
        self.cursor.execute("DELETE FROM UserdataItems WHERE EmbyId = ?", (EmbyId,))

    # PendingSync
    def add_LibraryAdd(self, EmbyLibraryId, EmbyLibraryName, EmbyType, KodiDBs):
        self.cursor.execute("INSERT OR IGNORE INTO LibraryAdd (EmbyLibraryId, EmbyLibraryName, EmbyType, KodiDBs) VALUES (?, ?, ?, ?)", (EmbyLibraryId, EmbyLibraryName, EmbyType, KodiDBs))

    def remove_LibraryAdd(self, EmbyLibraryId, EmbyLibraryName, EmbyType, KodiDBs):
        self.cursor.execute("DELETE FROM LibraryAdd WHERE EmbyLibraryId = ? AND EmbyLibraryName = ? AND EmbyType = ? AND KodiDBs = ?", (EmbyLibraryId, EmbyLibraryName, EmbyType, KodiDBs))

    def get_LibraryAdd(self):
        self.cursor.execute("SELECT * FROM LibraryAdd")
        return self.cursor.fetchall()

    def add_LibraryRemove(self, EmbyLibraryId, EmbyLibraryName):
        self.cursor.execute("INSERT OR IGNORE INTO LibraryRemove (EmbyLibraryId, EmbyLibraryName) VALUES (?, ?)", (EmbyLibraryId, EmbyLibraryName))

    def get_LibraryRemove(self):
        self.cursor.execute("SELECT * FROM LibraryRemove")
        return self.cursor.fetchall()

    def get_LibraryAdd_EmbyLibraryIds(self):
        PendingSyncAdded = set()
        self.cursor.execute("SELECT EmbyLibraryId FROM LibraryAdd")
        EmbyLibraryIds = self.cursor.fetchall()

        if EmbyLibraryIds:
            for EmbyLibraryId in EmbyLibraryIds:
                PendingSyncAdded.add(EmbyLibraryId[0])

        return PendingSyncAdded

    def get_LibraryRemove_EmbyLibraryIds(self):
        PendingSyncRemoved = set()
        self.cursor.execute("SELECT EmbyLibraryId FROM LibraryRemove")
        EmbyLibraryIds = self.cursor.fetchall()

        if EmbyLibraryIds:
            for EmbyLibraryId in EmbyLibraryIds:
                PendingSyncRemoved.add(EmbyLibraryId[0])

        return PendingSyncRemoved

    def remove_LibraryRemove(self, EmbyLibraryId):
        self.cursor.execute("DELETE FROM LibraryRemove WHERE EmbyLibraryId = ?", (EmbyLibraryId,))

    # UpdateItems
    def exist_UpdateItem(self, EmbyId):
        self.cursor.execute("SELECT EXISTS(SELECT 1 FROM UpdateItems WHERE EmbyId = ?)", (EmbyId,))
        return self.cursor.fetchone()[0]

    def add_UpdateItem(self, EmbyId, EmbyRequestContent, EmbyLibraryId, KodiDB=""):
        self.cursor.execute("INSERT OR REPLACE INTO UpdateItems (EmbyId, EmbyRequestContent, EmbyLibraryId, KodiDB) VALUES (?, ?, ?, ?)", (EmbyId, EmbyRequestContent, EmbyLibraryId, KodiDB))

    def add_UpdateItems(self, Data):
        self.cursor.executemany("INSERT OR REPLACE INTO UpdateItems (EmbyId, EmbyRequestContent, EmbyLibraryId) VALUES (?, ?, ?)", Data)


    def get_UpdateItem(self):
        self.cursor.execute("SELECT * FROM UpdateItems")
        Items = self.cursor.fetchall()
        ItemsCount = len(Items)

        if not ItemsCount:
            return {}, 0, {}

        Data = {}
        KodiDBMapping = {}

        for Item in Items:
            EmbyLibraryId = Item[2] # EmbyLibraryId

            if EmbyLibraryId not in Data:
                # Preserve the returned category order without reserving every queue row per category.
                Data[EmbyLibraryId] = {MediaType: [] for MediaType in (
                    "MusicVideo", "Folder", "Movie", "Video", "Series", "Season", "Episode",
                    "MusicArtist", "MusicAlbum", "Audio", "Person", "MusicGenre", "Genre",
                    "Studio", "Tag", "BoxSet", "Playlist", "unknown"
                )}

        for Item in Items:
            EmbyId = Item[0]
            EmbyRequestContent = Item[1]
            EmbyLibraryId = Item[2]
            KodiDB = Item[3]

            EmbyId = str(Item[0])

            if KodiDB:
                if KodiDB == "music":
                    if EmbyId not in KodiDBMapping:
                        KodiDBMapping[EmbyId] = ("music",)
                    elif "video" in KodiDBMapping[EmbyId]:
                        KodiDBMapping[EmbyId] = ("music", "video")
                elif KodiDB == "video":
                    if EmbyId not in KodiDBMapping:
                        KodiDBMapping[EmbyId] = ("video",)
                    elif "music" in KodiDBMapping[EmbyId]:
                        KodiDBMapping[EmbyId] = ("music", "video")

            if EmbyRequestContent in Data[EmbyLibraryId]:
                Data[EmbyLibraryId][EmbyRequestContent].append(EmbyId)
            else: # Unknown item type
                Data[EmbyLibraryId]["unknown"].append(EmbyId)

        return Data, ItemsCount, KodiDBMapping

    def delete_UpdateItem(self, EmbyId):
        self.cursor.execute("DELETE FROM UpdateItems WHERE EmbyId = ?", (EmbyId,))


    # RemoveItems
    def add_RemoveItem(self, EmbyId, EmbyLibraryId):
        self.cursor.execute("INSERT OR IGNORE INTO RemoveItems (EmbyId, EmbyLibraryId) VALUES (?, ?)", (EmbyId, EmbyLibraryId))

    def add_RemoveItems_EmbyId(self, EmbyIds):
        SQLData = []

        for EmbyId in EmbyIds:
            SQLData.append((EmbyId,))

        self.cursor.executemany("INSERT OR IGNORE INTO RemoveItems (EmbyId) VALUES (?)", SQLData)


    def get_RemoveItem(self):
        self.cursor.execute("SELECT * FROM RemoveItems")
        return self.cursor.fetchall()

    def empty_RemoveItem(self):
        self.cursor.execute("SELECT EXISTS(SELECT 1 FROM RemoveItems)")
        return self.cursor.fetchone()[0]

    def delete_RemoveItem(self, EmbyId):
        self.cursor.execute("DELETE FROM RemoveItems WHERE EmbyId = ? ", (EmbyId,))

    # Subtitle

    # MediaSources


    def get_mediasource(self, EmbyId):
        MediaSources = {}
        self.cursor.execute("SELECT Path, Name, Size, MediaSourceId, IntroStart, IntroEnd, CreditsStart FROM MediaSources WHERE EmbyId = ?", (EmbyId,))
        MediaSourcesData = self.cursor.fetchall()

        for MediaSourceData in MediaSourcesData:
            MediaSources[MediaSourceData[3]] = {"Path": MediaSourceData[0], "Name": MediaSourceData[1], "Size": MediaSourceData[2], "IntroStart": MediaSourceData[4], "IntroEnd": MediaSourceData[5], "CreditsStart": MediaSourceData[6], "MediaSourceId": MediaSourceData[3], "EmbyId": EmbyId}

        return {Source['MediaSourceId']: Source for Source in versions.sort_sources(MediaSources.values())}


    def get_mediasourceid_by_path(self, Path):
        self.cursor.execute("SELECT MediaSourceId FROM MediaSources WHERE Path = ?", (Path,))
        EmbyId = self.cursor.fetchone()

        if EmbyId:
            return EmbyId[0]

        return None

    def get_mediasource_EmbyID_by_path(self, Path):
        self.cursor.execute("SELECT EmbyId FROM MediaSources WHERE Path = ?", (Path,))
        EmbyId = self.cursor.fetchone()

        if EmbyId:
            return EmbyId[0]

        return None

    # Mapping
    def get_embypresentationkey_by_id_embytype(self, EmbyId, Tables):
        for Table in Tables:
            self.cursor.execute(f"SELECT EmbyPresentationKey FROM {Table} WHERE EmbyId = ?", (EmbyId,))
            Data = self.cursor.fetchone()

            if Data:
                return Data[0]

        return ""

    def get_albumid_by_id(self, EmbyId):
        self.cursor.execute("SELECT EmbyMusicAlbumId FROM EmbyLibraryMapping WHERE EmbyId = ? AND EmbyMusicAlbumId != 0", (EmbyId,))
        Data = self.cursor.fetchone()

        if Data:
            return str(Data[0])

        return ""

    def get_id_by_albumid(self, EmbyMusicAlbumId):
        ReturnData = ()
        self.cursor.execute("SELECT EmbyId FROM EmbyLibraryMapping WHERE EmbyMusicAlbumId = ?", (EmbyMusicAlbumId,))
        EmbyIds = self.cursor.fetchall()

        for EmbyId in EmbyIds:
            ReturnData += (str(EmbyId[0]),)

        return ReturnData

    def add_reference_audio(self, EmbyId, EmbyLibraryId, KodiIds, EmbyFolder, KodiPathId, EmbyLibraryIds, EmbyMusicAlbumId, EmbyMusicArtistIds, EmbyMusicGenreIds, EmbyParentId):
        self.cursor.execute("INSERT OR REPLACE INTO Audio (EmbyId, KodiId, EmbyFolder, KodiPathId, LibraryIds, EmbyParentId) VALUES (?, ?, ?, ?, ?, ?)", (EmbyId, ",".join(KodiIds), EmbyFolder, KodiPathId, ",".join(EmbyLibraryIds), EmbyParentId))
        SQLData = [(EmbyLibraryId, EmbyId, 0, 0, 0)]

        if EmbyMusicAlbumId:
            SQLData.append((EmbyLibraryId, EmbyId, EmbyMusicAlbumId, 0, 0))

        for EmbyMusicArtistId in EmbyMusicArtistIds:
            SQLData.append((EmbyLibraryId, EmbyId, 0, EmbyMusicArtistId, 0))

        for EmbyMusicGenreId in EmbyMusicGenreIds:
            SQLData.append((EmbyLibraryId, EmbyId, 0, 0, EmbyMusicGenreId))

        self.cursor.executemany("INSERT OR IGNORE INTO EmbyLibraryMapping (EmbyLibraryId, EmbyId, EmbyMusicAlbumId, EmbyMusicArtistId, EmbyMusicGenreId) VALUES (?, ?, ?, ?, ?)", SQLData)
        del SQLData


    def add_reference_musicartist(self, EmbyId, EmbyLibraryId, KodiIds, EmbyLibraryIds):
        self.cursor.execute("INSERT OR REPLACE INTO MusicArtist (EmbyId, KodiId, LibraryIds) VALUES (?, ?, ?)", (EmbyId, KodiIds, EmbyLibraryIds))
        self.cursor.execute("INSERT OR IGNORE INTO EmbyLibraryMapping (EmbyLibraryId, EmbyId) VALUES (?, ?)", (EmbyLibraryId, EmbyId))

    def add_reference_musicgenre(self, EmbyId, EmbyLibraryId, KodiIds, EmbyArtwork, LibraryIds):
        self.cursor.execute("INSERT OR REPLACE INTO MusicGenre (EmbyId, KodiId, LibraryIds, EmbyArtwork) VALUES (?, ?, ?, ?)", (EmbyId, KodiIds, LibraryIds, EmbyArtwork))
        self.cursor.execute("INSERT OR IGNORE INTO EmbyLibraryMapping (EmbyLibraryId, EmbyId) VALUES (?, ?)", (EmbyLibraryId, EmbyId))

    def add_reference_musicalbum(self, EmbyId, EmbyLibraryId, KodiIds, EmbyLibraryIds, EmbyMusicArtistIds):
        self.cursor.execute("INSERT OR REPLACE INTO MusicAlbum (EmbyId, KodiId, LibraryIds) VALUES (?, ?, ?)", (EmbyId, ",".join(KodiIds), ",".join(EmbyLibraryIds)))
        SQLData = [(EmbyLibraryId, EmbyId, 0)]

        for EmbyMusicArtistId in EmbyMusicArtistIds:
            SQLData.append((EmbyLibraryId, EmbyId, EmbyMusicArtistId))

        self.cursor.executemany("INSERT OR IGNORE INTO EmbyLibraryMapping (EmbyLibraryId, EmbyId, EmbyMusicArtistId) VALUES (?, ?, ?)", SQLData)
        del SQLData

    def add_reference_episode(self, EmbyId, EmbyLibraryId, KodiId, KodiFileId, KodiParentId, EmbyPresentationKey, EmbyFolder, KodiPathId):
        self.cursor.execute("INSERT OR REPLACE INTO Episode (EmbyId, KodiId, KodiFileId, KodiParentId, EmbyPresentationKey, EmbyFolder, KodiPathId) VALUES (?, ?, ?, ?, ?, ?, ?)", (EmbyId, KodiId, KodiFileId, KodiParentId, EmbyPresentationKey, EmbyFolder, KodiPathId))
        self.cursor.execute("INSERT OR IGNORE INTO EmbyLibraryMapping (EmbyLibraryId, EmbyId) VALUES (?, ?)", (EmbyLibraryId, EmbyId))

    def add_reference_season(self, EmbyId, EmbyLibraryId, KodiId, KodiParentId, EmbyPresentationKey):
        self.cursor.execute("INSERT OR REPLACE INTO Season (EmbyId, KodiId, KodiParentId, EmbyPresentationKey) VALUES (?, ?, ?, ?)", (EmbyId, KodiId, KodiParentId, EmbyPresentationKey))
        self.cursor.execute("INSERT OR IGNORE INTO EmbyLibraryMapping (EmbyLibraryId, EmbyId) VALUES (?, ?)", (EmbyLibraryId, EmbyId))

    def add_reference_series(self, EmbyId, EmbyLibraryId, KodiId, EmbyPresentationKey, KodiPathId):
        self.cursor.execute("INSERT OR REPLACE INTO Series (EmbyId, KodiId, EmbyPresentationKey, KodiPathId) VALUES (?, ?, ?, ?)", (EmbyId, KodiId, EmbyPresentationKey, KodiPathId))
        self.cursor.execute("INSERT OR IGNORE INTO EmbyLibraryMapping (EmbyLibraryId, EmbyId) VALUES (?, ?)", (EmbyLibraryId, EmbyId))

    def add_reference_boxset(self, EmbyId, EmbyLibraryId, KodiId, KodiParentId):
        self.cursor.execute("INSERT OR REPLACE INTO BoxSet (EmbyId, KodiId, KodiParentId) VALUES (?, ?, ?)", (EmbyId, KodiId, KodiParentId))
        self.cursor.execute("INSERT OR IGNORE INTO EmbyLibraryMapping (EmbyLibraryId, EmbyId) VALUES (?, ?)", (EmbyLibraryId, EmbyId))

    def add_reference_movie(self, EmbyId, EmbyLibraryId, KodiId, KodiFileId, EmbyPresentationKey, EmbyFolder, KodiPathId, TmdbId):
        self.cursor.execute("INSERT OR REPLACE INTO Movie (EmbyId, KodiId, KodiFileId, EmbyPresentationKey, EmbyFolder, KodiPathId, TmdbId) VALUES (?, ?, ?, ?, ?, ?, ?)", (EmbyId, KodiId, KodiFileId, EmbyPresentationKey, EmbyFolder, KodiPathId, TmdbId))
        self.cursor.execute("INSERT OR IGNORE INTO EmbyLibraryMapping (EmbyLibraryId, EmbyId) VALUES (?, ?)", (EmbyLibraryId, EmbyId))

    def add_reference_musicvideo(self, EmbyId, EmbyLibraryId, KodiId, KodiFileId, EmbyPresentationKey, EmbyFolder, KodiPathId, LibraryIds, EmbyMusicArtistIds, EmbyMusicGenreIds):
        if KodiId:
            KodiId = ",".join(KodiId)
            KodiFileId = ",".join(KodiFileId)
            KodiPathId = ",".join(KodiPathId)

        self.cursor.execute("INSERT OR REPLACE INTO MusicVideo (EmbyId, KodiId, KodiFileId, EmbyPresentationKey, EmbyFolder, KodiPathId, LibraryIds) VALUES (?, ?, ?, ?, ?, ?, ?)", (EmbyId, KodiId, KodiFileId, EmbyPresentationKey, EmbyFolder, KodiPathId, LibraryIds))
        SQLData = [(EmbyLibraryId, EmbyId, 0, 0)]

        for EmbyMusicArtistId in EmbyMusicArtistIds:
            SQLData.append((EmbyLibraryId, EmbyId, EmbyMusicArtistId, 0))

        for EmbyMusicGenreId in EmbyMusicGenreIds:
            SQLData.append((EmbyLibraryId, EmbyId, 0, EmbyMusicGenreId))

        self.cursor.executemany("INSERT OR IGNORE INTO EmbyLibraryMapping (EmbyLibraryId, EmbyId, EmbyMusicArtistId, EmbyMusicGenreId) VALUES (?, ?, ?, ?)", SQLData)
        del SQLData

    def add_reference_video(self, EmbyId, EmbyLibraryId, KodiId, KodiFileId, EmbyParentId, EmbyPresentationKey, EmbyFolder, KodiPathId):
        self.cursor.execute("INSERT OR REPLACE INTO Video (EmbyId, KodiId, KodiFileId, EmbyParentId, EmbyPresentationKey, EmbyFolder, KodiPathId) VALUES (?, ?, ?, ?, ?, ?, ?)", (EmbyId, KodiId, KodiFileId, EmbyParentId, EmbyPresentationKey, EmbyFolder, KodiPathId))
        self.cursor.execute("INSERT OR IGNORE INTO EmbyLibraryMapping (EmbyLibraryId, EmbyId) VALUES (?, ?)", (EmbyLibraryId, EmbyId))


    def add_reference_folder(self, EmbyId, EmbyLibraryId, EmbyFolder, EmbyMetaData):
        self.cursor.execute("INSERT OR REPLACE INTO Folder (EmbyId, EmbyFolder, EmbyMetaData) VALUES (?, ?, ?)", (EmbyId, EmbyFolder, EmbyMetaData))
        self.cursor.execute("INSERT OR IGNORE INTO EmbyLibraryMapping (EmbyLibraryId, EmbyId) VALUES (?, ?)", (EmbyLibraryId, EmbyId))

    def add_reference_metadata(self, EmbyId, EmbyLibraryId, EmbyType, KodiId):
        self.cursor.execute(f"INSERT OR REPLACE INTO {EmbyType} (EmbyId, KodiId) VALUES (?, ?)", (EmbyId, KodiId))
        self.cursor.execute("INSERT OR IGNORE INTO EmbyLibraryMapping (EmbyLibraryId, EmbyId) VALUES (?, ?)", (EmbyLibraryId, EmbyId))

    def add_reference_tag(self, EmbyId, EmbyLibraryId, KodiId, Memo, EmbyArtwork):
        self.cursor.execute("INSERT OR REPLACE INTO Tag (EmbyId, KodiId, Memo, EmbyArtwork) VALUES (?, ?, ?, ?)", (EmbyId, KodiId, Memo, EmbyArtwork))
        self.cursor.execute("INSERT OR IGNORE INTO EmbyLibraryMapping (EmbyLibraryId, EmbyId) VALUES (?, ?)", (EmbyLibraryId, EmbyId))

    def add_reference_genre(self, EmbyId, EmbyLibraryId, KodiId, EmbyArtwork):
        self.cursor.execute("INSERT OR REPLACE INTO Genre (EmbyId, KodiId, EmbyArtwork) VALUES (?, ?, ?)", (EmbyId, KodiId, EmbyArtwork))
        self.cursor.execute("INSERT OR IGNORE INTO EmbyLibraryMapping (EmbyLibraryId, EmbyId) VALUES (?, ?)", (EmbyLibraryId, EmbyId))

    def add_reference_playlist(self, EmbyId, EmbyLibraryId, KodiId, EmbyArtwork, EmbyLinkedId, Name):
        self.cursor.execute("""INSERT INTO Playlist (EmbyId, KodiId, EmbyArtwork, EmbyLinkedId, Name) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(EmbyId) DO UPDATE SET KodiId = excluded.KodiId, EmbyArtwork = excluded.EmbyArtwork,
                EmbyLinkedId = excluded.EmbyLinkedId, Name = excluded.Name""", (EmbyId, KodiId, EmbyArtwork, EmbyLinkedId, Name))
        self.cursor.execute("INSERT OR IGNORE INTO EmbyLibraryMapping (EmbyLibraryId, EmbyId) VALUES (?, ?)", (EmbyLibraryId, EmbyId))

    def get_library_playlists(self, LibraryId):
        self.cursor.execute("""SELECT Playlist.EmbyLinkedId FROM Playlist
            JOIN EmbyLibraryMapping USING (EmbyId) WHERE EmbyLibraryId = ?""", (LibraryId,))
        return [Row[0] for Row in self.cursor.fetchall()]

    def cancel_playlist_member_removals(self, LibraryId, Members):
        # A later playlist update can add a member queued for removal by another list.
        self.cursor.executemany("DELETE FROM RemoveItems WHERE EmbyId = ? AND EmbyLibraryId = ?",
                                ((EmbyId, LibraryId) for EmbyId in Members))

    def add_reference_studio(self, EmbyId, EmbyLibraryId, KodiId, EmbyArtwork):
        self.cursor.execute("INSERT OR REPLACE INTO Studio (EmbyId, KodiId, EmbyArtwork) VALUES (?, ?, ?)", (EmbyId, KodiId, EmbyArtwork))
        self.cursor.execute("INSERT OR IGNORE INTO EmbyLibraryMapping (EmbyLibraryId, EmbyId) VALUES (?, ?)", (EmbyLibraryId, EmbyId))

    def update_reference_video(self, EmbyId, EmbyParentId, EmbyPresentationKey, EmbyLibraryId):
        self.cursor.execute("UPDATE Video SET EmbyParentId = ?, EmbyPresentationKey = ? WHERE EmbyId = ?", (EmbyParentId, EmbyPresentationKey, EmbyId))
        self.cursor.execute("INSERT OR IGNORE INTO EmbyLibraryMapping (EmbyLibraryId, EmbyId) VALUES (?, ?)", (EmbyLibraryId, EmbyId))

    def update_reference_studio(self, EmbyId, EmbyArtwork, EmbyLibraryId):
        self.cursor.execute("UPDATE Studio SET EmbyArtwork = ? WHERE EmbyId = ?", (EmbyArtwork, EmbyId))
        self.cursor.execute("INSERT OR IGNORE INTO EmbyLibraryMapping (EmbyLibraryId, EmbyId) VALUES (?, ?)", (EmbyLibraryId, EmbyId))

    def update_reference_genre(self, EmbyId, EmbyArtwork, EmbyLibraryId):
        self.cursor.execute("UPDATE Genre SET EmbyArtwork = ? WHERE EmbyId = ?", (EmbyArtwork, EmbyId))
        self.cursor.execute("INSERT OR IGNORE INTO EmbyLibraryMapping (EmbyLibraryId, EmbyId) VALUES (?, ?)", (EmbyLibraryId, EmbyId))

    def update_reference_tag(self, EmbyId, Memo, EmbyArtwork, EmbyLibraryId):
        self.cursor.execute("UPDATE Tag SET EmbyArtwork = ?, Memo = ? WHERE EmbyId = ?", (EmbyArtwork, Memo, EmbyId))
        self.cursor.execute("INSERT OR IGNORE INTO EmbyLibraryMapping (EmbyLibraryId, EmbyId) VALUES (?, ?)", (EmbyLibraryId, EmbyId))

    def update_reference_musicvideo(self, EmbyId, EmbyPresentationKey, EmbyLibraryId, EmbyMusicArtistIds, EmbyMusicGenreIds):
        self.cursor.execute("UPDATE MusicVideo SET EmbyPresentationKey = ? WHERE EmbyId = ?", (EmbyPresentationKey, EmbyId))
        self.cursor.execute("INSERT OR IGNORE INTO EmbyLibraryMapping (EmbyLibraryId, EmbyId) VALUES (?, ?)", (EmbyLibraryId, EmbyId))
        SQLData = [(EmbyLibraryId, EmbyId, 0, 0)]

        for EmbyMusicArtistId in EmbyMusicArtistIds:
            SQLData.append((EmbyLibraryId, EmbyId, EmbyMusicArtistId, 0))

        for EmbyMusicGenreId in EmbyMusicGenreIds:
            SQLData.append((EmbyLibraryId, EmbyId, 0, EmbyMusicGenreId))

        self.cursor.executemany("INSERT OR IGNORE INTO EmbyLibraryMapping (EmbyLibraryId, EmbyId, EmbyMusicArtistId, EmbyMusicGenreId) VALUES (?, ?, ?, ?)", SQLData)
        del SQLData

    def update_reference_movie(self, EmbyId, EmbyPresentationKey, EmbyLibraryId, TmdbId):
        self.cursor.execute("UPDATE Movie SET EmbyPresentationKey = ?, TmdbId = ? WHERE EmbyId = ?", (EmbyPresentationKey, TmdbId, EmbyId))
        self.cursor.execute("INSERT OR IGNORE INTO EmbyLibraryMapping (EmbyLibraryId, EmbyId) VALUES (?, ?)", (EmbyLibraryId, EmbyId))

    def update_deleted_musicvideo(self, EmbyId, KodiItemIds, KodiFileIds, KodiPathIds, EmbyLibraryIds):
        self.cursor.execute("UPDATE MusicVideo SET KodiId = ?, KodiFileId = ?, KodiPathId = ?, LibraryIds = ? WHERE EmbyId = ?", (KodiItemIds, KodiFileIds, KodiPathIds, EmbyLibraryIds, EmbyId))

    def update_reference_episode(self, EmbyId, KodiParentId, EmbyPresentationKey, EmbyLibraryId):
        self.cursor.execute("UPDATE Episode SET KodiParentId = ?, EmbyPresentationKey = ? WHERE EmbyId = ?", (KodiParentId, EmbyPresentationKey, EmbyId))
        self.cursor.execute("INSERT OR IGNORE INTO EmbyLibraryMapping (EmbyLibraryId, EmbyId) VALUES (?, ?)", (EmbyLibraryId, EmbyId))

    def update_reference_musicgenre(self, EmbyId, EmbyArtwork, EmbyLibraryId):
        self.cursor.execute("UPDATE MusicGenre SET EmbyArtwork = ? WHERE EmbyId = ?", (EmbyArtwork, EmbyId))
        self.cursor.execute("INSERT OR IGNORE INTO EmbyLibraryMapping (EmbyLibraryId, EmbyId) VALUES (?, ?)", (EmbyLibraryId, EmbyId))

    def update_reference_audio(self, EmbyId, EmbyLibraryId, EmbyMusicAlbumId, EmbyMusicArtistIds, EmbyMusicGenreIds):
        SQLData = [(EmbyLibraryId, EmbyId, 0, 0, 0), (EmbyLibraryId, EmbyId, EmbyMusicAlbumId, 0, 0)]

        for EmbyMusicArtistId in EmbyMusicArtistIds:
            SQLData.append((EmbyLibraryId, EmbyId, 0, EmbyMusicArtistId, 0))

        for EmbyMusicGenreId in EmbyMusicGenreIds:
            SQLData.append((EmbyLibraryId, EmbyId, 0, 0, EmbyMusicGenreId))

        self.cursor.execute("DELETE FROM EmbyLibraryMapping WHERE EmbyId = ? AND EmbyLibraryId = ?", (EmbyId, EmbyLibraryId))
        self.cursor.executemany("INSERT OR IGNORE INTO EmbyLibraryMapping (EmbyLibraryId, EmbyId, EmbyMusicAlbumId, EmbyMusicArtistId, EmbyMusicGenreId) VALUES (?, ?, ?, ?, ?)", SQLData)
        del SQLData

    def update_reference_musicartist(self, EmbyId, EmbyLibraryId):
        self.cursor.execute("INSERT OR IGNORE INTO EmbyLibraryMapping (EmbyLibraryId, EmbyId) VALUES (?, ?)", (EmbyLibraryId, EmbyId))

    def update_reference_musicalbum(self, EmbyId, EmbyLibraryId, EmbyMusicArtistIds):
        SQLData = [(EmbyLibraryId, EmbyId, 0)]

        for EmbyMusicArtistId in EmbyMusicArtistIds:
            SQLData.append((EmbyLibraryId, EmbyId, EmbyMusicArtistId))

        self.cursor.executemany("INSERT OR IGNORE INTO EmbyLibraryMapping (EmbyLibraryId, EmbyId, EmbyMusicArtistId) VALUES (?, ?, ?)", SQLData)
        del SQLData

    def update_reference_generic(self, EmbyId, EmbyLibraryId):
        self.cursor.execute("INSERT OR IGNORE INTO EmbyLibraryMapping (EmbyLibraryId, EmbyId) VALUES (?, ?)", (EmbyLibraryId, EmbyId))

    def update_favourite(self, EmbyFavourite, EmbyId, EmbyType):
        self.cursor.execute(f"UPDATE {EmbyType} SET EmbyFavourite = ? WHERE EmbyId = ?", (EmbyFavourite, EmbyId))

    def update_EmbyLibraryMapping(self, EmbyId, EmbyLibraryId):
        self.cursor.execute("INSERT OR IGNORE INTO EmbyLibraryMapping (EmbyLibraryId, EmbyId) VALUES (?, ?)", (EmbyLibraryId, EmbyId))

    def get_UserData_MetaData(self, EmbyId, EmbyType):
        if EmbyType:
            EmbyTypesMod = (EmbyType,)
        else:
            EmbyTypesMod = EmbyTypes

        for EmbyTypeMod in EmbyTypesMod:
            if EmbyTypeMod in ("Season", "BoxSet"):
                self.cursor.execute(f"SELECT KodiId, KodiParentId FROM {EmbyTypeMod} WHERE EmbyId = ?", (EmbyId,))
                Data = self.cursor.fetchone()

                if Data:
                    return {"KodiItemId": Data[0], "KodiFileId": "", "Type": EmbyTypeMod, "KodiParentId": Data[1], "Name": ""}

            if EmbyTypeMod == "Episode":
                self.cursor.execute("SELECT KodiId, KodiParentId, KodiFileId FROM Episode WHERE EmbyId = ?", (EmbyId,))
                Data = self.cursor.fetchone()

                if Data:
                    return {"KodiItemId": Data[0], "KodiFileId": Data[2], "Type": EmbyTypeMod, "KodiParentId": Data[1], "Name": ""}

            if EmbyTypeMod in ("Movie", "Video", "MusicVideo"):
                self.cursor.execute(f"SELECT KodiId, KodiFileId FROM {EmbyTypeMod} WHERE EmbyId = ?", (EmbyId,))
                Data = self.cursor.fetchone()

                if Data:
                    return {"KodiItemId": Data[0], "KodiFileId": Data[1], "Type": EmbyTypeMod, "KodiParentId": "", "Name": ""}

            if EmbyTypeMod == "Folder": # Content only synced to local emby database
                self.cursor.execute(f"SELECT * FROM {EmbyTypeMod} WHERE EmbyId = ?", (EmbyId,)) # Check if exists
                Data = self.cursor.fetchone()

                if Data:
                    return {"KodiItemId": "", "KodiFileId": "", "Type": EmbyTypeMod, "KodiParentId": "", "Name": ""}

            if EmbyTypeMod == "Playlist":
                self.cursor.execute("SELECT KodiId, Name, EmbyLinkedId FROM Playlist WHERE EmbyId = ?", (EmbyId,))
                Data = self.cursor.fetchone()

                if Data:
                    return {"KodiItemId": Data[0], "KodiFileId": "", "Type": EmbyTypeMod, "KodiParentId": "", "Name": Data[1], "EmbyLinkedId": Data[2]}

            if EmbyTypeMod == "MusicAlbum":
                self.cursor.execute("SELECT KodiId, LibraryIds FROM MusicAlbum WHERE EmbyId = ?", (EmbyId,))
                Data = self.cursor.fetchone()

                if Data:
                    return {"KodiItemId": Data[0], "KodiFileId": "", "Type": EmbyTypeMod, "KodiParentId": "", "Name": "", "LibraryIds": Data[1]}

            if EmbyTypeMod == "MusicArtist":
                self.cursor.execute("SELECT KodiId, LibraryIds FROM MusicArtist WHERE EmbyId = ?", (EmbyId,))
                Data = self.cursor.fetchone()

                if Data:
                    return {"KodiItemId": Data[0], "KodiFileId": "", "Type": EmbyTypeMod, "KodiParentId": "", "Name": "", "LibraryIds": Data[1]}

            if EmbyTypeMod in ("Series", "Genre", "MusicGenre", "Tag", "Studio", "Person", "Audio"):
                self.cursor.execute(f"SELECT KodiId FROM {EmbyTypeMod} WHERE EmbyId = ?", (EmbyId,))
                Data = self.cursor.fetchone()

                if Data:
                    return {"KodiItemId": Data[0], "KodiFileId": "", "Type": EmbyTypeMod, "KodiParentId": "", "Name": ""}

        return {"KodiItemId": "", "KodiFileId": "", "Type": "", "KodiParentId": "", "Name": ""}

    def get_remove_generator_items(self, EmbyId, EmbyLibraryId):
        RemoveItems = []
        ItemFound = False
        EmbyIds = []

        for Table in ("Movie", "Episode"):
            self.cursor.execute(f"SELECT KodiId, KodiFileId, EmbyPresentationKey, KodiPathId FROM {Table} WHERE EmbyId = ?", (EmbyId,))
            Data = self.cursor.fetchone()

            if Data:
                if EmbyId not in EmbyIds:
                    RemoveItems.append({"Id": EmbyId, "KodiItemId": Data[0], "KodiFileId": Data[1], "Type": Table, "PresentationUniqueKey": Data[2], "KodiParentId": None, "KodiPathId": Data[3], "EmbyLinkedId": "", "LibraryIds": "", "Name": ""})
                    EmbyIds.append(EmbyId)

                ItemFound = True
                break

        if not ItemFound:
            self.cursor.execute("SELECT KodiId, KodiFileId, EmbyPresentationKey, KodiPathId, LibraryIds FROM MusicVideo WHERE EmbyId = ?", (EmbyId,))
            Data = self.cursor.fetchone()

            if Data:
                if EmbyId not in EmbyIds:
                    RemoveItems.append({"Id": EmbyId, "KodiItemId": Data[0], "KodiFileId": Data[1], "Type": "MusicVideo", "PresentationUniqueKey": Data[2], "KodiParentId": None, "KodiPathId": Data[3], "EmbyLinkedId": "", "LibraryIds": Data[4], "Name": ""})
                    EmbyIds.append(EmbyId)

                ItemFound = True

        if not ItemFound:
            self.cursor.execute("SELECT KodiId, KodiFileId, EmbyPresentationKey, KodiPathId FROM Video WHERE EmbyId = ?", (EmbyId,))
            Data = self.cursor.fetchone()

            if Data:
                if EmbyId not in EmbyIds:
                    RemoveItems.append({"Id": EmbyId, "KodiItemId": Data[0], "KodiFileId": Data[1], "Type": "Video", "PresentationUniqueKey": Data[2], "KodiParentId": None, "KodiPathId": Data[3], "EmbyLinkedId": "", "LibraryIds": "", "Name": ""})
                    EmbyIds.append(EmbyId)

                ItemFound = True

        if not ItemFound:
            self.cursor.execute("SELECT KodiId, EmbyPresentationKey, KodiPathId FROM Series WHERE EmbyId = ?", (EmbyId,))
            Data = self.cursor.fetchone()

            if Data:
                if EmbyId not in EmbyIds:
                    RemoveItems.append({"Id": EmbyId, "KodiItemId": Data[0], "KodiFileId": None, "Type": "Series", "PresentationUniqueKey": Data[1], "KodiParentId": None, "KodiPathId": Data[2], "EmbyLinkedId": "", "LibraryIds": "", "Name": ""})
                    EmbyIds.append(EmbyId)

                ItemFound = True

        if not ItemFound:
            self.cursor.execute("SELECT KodiId, EmbyPresentationKey, KodiParentId FROM Season WHERE EmbyId = ?", (EmbyId,))
            Data = self.cursor.fetchone()

            if Data:
                if EmbyId not in EmbyIds:
                    RemoveItems.append({"Id": EmbyId, "KodiItemId": Data[0], "KodiFileId": None, "Type": "Season", "PresentationUniqueKey": Data[1], "KodiParentId": Data[2], "KodiPathId": None, "EmbyLinkedId": "", "LibraryIds": "", "Name": ""})
                    EmbyIds.append(EmbyId)

                ItemFound = True

        if not ItemFound:
            self.cursor.execute("SELECT KodiId, EmbyLinkedId, Name FROM Playlist WHERE EmbyId = ?", (EmbyId,))
            Data = self.cursor.fetchone()

            if Data:
                if EmbyId not in EmbyIds:
                    RemoveItems.append({"Id": EmbyId, "KodiItemId": Data[0], "KodiFileId": None, "Type": "Playlist", "PresentationUniqueKey": None, "KodiParentId": None, "KodiPathId": None, "EmbyLinkedId": Data[1], "LibraryIds": "", "Name": Data[2]})
                    EmbyIds.append(EmbyId)

                ItemFound = True

        if not ItemFound:
            for Table in ("Genre", "Tag", "Person", "Studio", "BoxSet"):
                self.cursor.execute(f"SELECT KodiId FROM {Table} WHERE EmbyId = ?", (EmbyId,))
                Data = self.cursor.fetchone()

                if Data:
                    if EmbyId not in EmbyIds:
                        RemoveItems.append({"Id": EmbyId, "KodiItemId": Data[0], "KodiFileId": None, "Type": Table, "PresentationUniqueKey": None, "KodiParentId": None, "KodiPathId": None, "EmbyLinkedId": "", "LibraryIds": "", "Name": ""})
                        EmbyIds.append(EmbyId)

                    ItemFound = True
                    break

        if not ItemFound:
            for Table in ("MusicArtist", "MusicGenre"):
                self.cursor.execute(f"SELECT KodiId, LibraryIds FROM {Table} WHERE EmbyId = ?", (EmbyId,))
                Data = self.cursor.fetchone()

                if Data:
                    if EmbyId not in EmbyIds:
                        RemoveItems.append({"Id": EmbyId, "KodiItemId": Data[0], "KodiFileId": None, "Type": Table, "PresentationUniqueKey": None, "KodiParentId": None, "KodiPathId": None, "EmbyLinkedId": "", "LibraryIds": Data[1], "Name": ""})
                        EmbyIds.append(EmbyId)

                    ItemFound = True
                    break

        if not ItemFound:
            self.cursor.execute("SELECT KodiId, LibraryIds FROM MusicAlbum WHERE EmbyId = ?", (EmbyId,))
            Data = self.cursor.fetchone()

            if Data:
                if EmbyId not in EmbyIds:
                    RemoveItems.append({"Id": EmbyId, "KodiItemId": Data[0], "KodiFileId": None, "Type": "MusicAlbum", "PresentationUniqueKey": None, "KodiParentId": None, "KodiPathId": None, "EmbyLinkedId": "", "LibraryIds": Data[1], "Name": ""})
                    EmbyIds.append(EmbyId)

                    # MyMusic.db trigger removes all referenced songs, so add them here
                    if not EmbyLibraryId: # only if not a complete library was removed
                        self.cursor.execute("SELECT EmbyId FROM EmbyLibraryMapping WHERE EmbyMusicAlbumId = ?", (EmbyId,))
                        Datas = self.cursor.fetchall()

                        for Data in Datas:
                            self.cursor.execute("SELECT KodiId, KodiPathId, LibraryIds FROM Audio WHERE EmbyId = ?", (Data[0],))
                            DataSub = self.cursor.fetchone()

                            if DataSub:
                                if Data[0] not in EmbyIds:
                                    RemoveItems.append({"Id": Data[0], "KodiItemId": DataSub[0], "KodiFileId": None, "Type": "Audio", "PresentationUniqueKey": None, "KodiParentId": None, "KodiPathId": DataSub[1], "EmbyLinkedId": "", "LibraryIds": DataSub[2], "Name": ""})
                                    EmbyIds.append(Data[0])

                ItemFound = True

        if not ItemFound:
            self.cursor.execute("SELECT KodiId, KodiPathId, LibraryIds FROM Audio WHERE EmbyId = ?", (EmbyId,))
            Data = self.cursor.fetchone()

            if Data:
                if EmbyId not in EmbyIds:
                    RemoveItems.append({"Id": EmbyId, "KodiItemId": Data[0], "KodiFileId": None, "Type": "Audio", "PresentationUniqueKey": None, "KodiParentId": None, "KodiPathId": Data[1], "EmbyLinkedId": "", "LibraryIds": Data[2], "Name": ""})
                    EmbyIds.append(EmbyId)

                ItemFound = True


        if not ItemFound: # Folder
            self.cursor.execute("SELECT EmbyFolder FROM Folder WHERE EmbyId = ?", (EmbyId,))
            EmbyFolder = self.cursor.fetchone()

            if EmbyFolder and EmbyFolder[0]:
                Search = EmbyFolder[0].replace("\\", "\\\\").replace("_", "\\_").replace("%", "\\%") # underline and percent are wildcards in sqlite

                if EmbyId not in EmbyIds:
                    RemoveItems.append({"Id": EmbyId, "KodiItemId": "", "KodiFileId": None, "Type": "Folder", "PresentationUniqueKey": None, "KodiParentId": None, "KodiPathId": None, "EmbyLinkedId": "", "LibraryIds": "", "Name": ""})
                    EmbyIds.append(EmbyId)

                # Delete items by same folder
                if not EmbyLibraryId: # only if not a complete library was removed
                    for Table in ("Movie", "Episode", "MusicVideo"):
                        self.cursor.execute(f"SELECT EmbyId, KodiId, KodiFileId, EmbyPresentationKey, KodiPathId FROM {Table} WHERE EmbyFolder LIKE ? ESCAPE '\\'", (f"{Search}%",))
                        Datas = self.cursor.fetchall()

                        for Data in Datas:
                            if Data[0] not in EmbyIds:
                                RemoveItems.append({"Id": Data[0], "KodiItemId": Data[1], "KodiFileId": Data[2], "Type": Table, "PresentationUniqueKey": Data[3], "KodiParentId": None, "KodiPathId": Data[4], "EmbyLinkedId": "", "LibraryIds": "", "Name": ""})
                                EmbyIds.append(Data[0])

                    self.cursor.execute("SELECT EmbyId, KodiId, KodiFileId, EmbyPresentationKey, KodiPathId FROM Video WHERE EmbyFolder LIKE ? ESCAPE '\\'", (f"{Search}%",))
                    Datas = self.cursor.fetchall()

                    for Data in Datas:
                        if Data[0] not in EmbyIds:
                            RemoveItems.append({"Id": Data[0], "KodiItemId": Data[1], "KodiFileId": Data[2], "Type": "Video", "PresentationUniqueKey": Data[3], "KodiParentId": None, "KodiPathId": Data[4], "EmbyLinkedId": "", "LibraryIds": "", "Name": ""})
                            EmbyIds.append(Data[0])

                    self.cursor.execute("SELECT EmbyId, KodiId, KodiPathId, LibraryIds FROM Audio WHERE EmbyFolder LIKE ? ESCAPE '\\'", (f"{Search}%",))
                    Datas = self.cursor.fetchall()

                    for Data in Datas:
                        if Data[0] not in EmbyIds:
                            RemoveItems.append({"Id": Data[0], "KodiItemId": Data[1], "KodiFileId": None, "Type": "Audio", "PresentationUniqueKey": None, "KodiParentId": None, "KodiPathId": Data[2], "EmbyLinkedId": "", "LibraryIds": Data[3], "Name": ""})
                            EmbyIds.append(Data[0])

        return tuple(RemoveItems)

    def add_remove_library_items(self, EmbyLibraryId):
        self.cursor.execute("SELECT EmbyId, EmbyLibraryId FROM EmbyLibraryMapping WHERE EmbyLibraryId = ? AND EmbyId NOT LIKE ?", (EmbyLibraryId, "9999999%"))
        SQLData = self.cursor.fetchall()

        if SQLData:
            self.cursor.executemany("INSERT OR REPLACE INTO RemoveItems (EmbyId, EmbyLibraryId) VALUES (?, ?)", SQLData)

        SQLData = []

         # Remove library subitems
        self.cursor.execute("SELECT EXISTS(SELECT 1 FROM EmbyLibraryMapping WHERE EmbyId = ? AND EmbyLibraryId = ?)", (f"{utils.MappingIds['Tag']}00{EmbyLibraryId}", EmbyLibraryId))

        if self.cursor.fetchone()[0]:
            self.cursor.execute("INSERT OR REPLACE INTO RemoveItems (EmbyId, EmbyLibraryId) VALUES (?, ?)", (f"{utils.MappingIds['Tag']}00{EmbyLibraryId}", EmbyLibraryId))

        # Remove favorite subitems
        # Movies (Favorites)
        self.cursor.execute("SELECT EXISTS(SELECT 1 FROM EmbyLibraryMapping WHERE EmbyId = ? AND EmbyLibraryId = ?)", (f"{utils.MappingIds['Tag']}01{EmbyLibraryId}", EmbyLibraryId))

        if self.cursor.fetchone()[0]:
            self.cursor.execute("INSERT OR REPLACE INTO RemoveItems (EmbyId, EmbyLibraryId) VALUES (?, ?)", (f"{utils.MappingIds['Tag']}01{EmbyLibraryId}", EmbyLibraryId))

        # Musicvideos (Favorites)
        self.cursor.execute("SELECT EXISTS(SELECT 1 FROM EmbyLibraryMapping WHERE EmbyId = ? AND EmbyLibraryId = ?)", (f"{utils.MappingIds['Tag']}02{EmbyLibraryId}", EmbyLibraryId))

        if self.cursor.fetchone()[0]:
            self.cursor.execute("INSERT OR REPLACE INTO RemoveItems (EmbyId, EmbyLibraryId) VALUES (?, ?)", (f"{utils.MappingIds['Tag']}02{EmbyLibraryId}", EmbyLibraryId))

        # TVShows (Favorites)
        self.cursor.execute("SELECT EXISTS(SELECT 1 FROM EmbyLibraryMapping WHERE EmbyId = ? AND EmbyLibraryId = ?)", (f"{utils.MappingIds['Tag']}03{EmbyLibraryId}", EmbyLibraryId))

        if self.cursor.fetchone()[0]:
            self.cursor.execute("INSERT OR REPLACE INTO RemoveItems (EmbyId, EmbyLibraryId) VALUES (?, ?)", (f"{utils.MappingIds['Tag']}03{EmbyLibraryId}", EmbyLibraryId))

        for _, MappingId in list(utils.MappingIds.items()):
            self.cursor.execute("SELECT EXISTS(SELECT 1 FROM EmbyLibraryMapping WHERE EmbyId = ? AND EmbyLibraryId = ?)", (MappingId, EmbyLibraryId))

            if self.cursor.fetchone()[0]:
                SQLData.append((MappingId, EmbyLibraryId))

        if SQLData:
            self.cursor.executemany("INSERT OR REPLACE INTO RemoveItems (EmbyId, EmbyLibraryId) VALUES (?, ?)", SQLData)

        del SQLData
        self.cursor.execute("DELETE FROM UpdateItems WHERE EmbyLibraryId = ?", (EmbyLibraryId,))

    def add_remove_library_items_person(self):
        self.cursor.execute("SELECT EmbyId, '999999999' FROM Person")
        SQLData = self.cursor.fetchall()

        if SQLData:
            self.cursor.executemany("INSERT OR REPLACE INTO RemoveItems (EmbyId, EmbyLibraryId) VALUES (?, ?)", SQLData)

        del SQLData

    def get_episode_fav(self):
        self.cursor.execute("SELECT KodiId FROM Episode WHERE EmbyFavourite = ?", ("1",))
        return self.cursor.fetchall()

    def get_season_fav(self):
        self.cursor.execute("SELECT KodiId FROM Season WHERE EmbyFavourite = ?", ("1",))
        return self.cursor.fetchall()


    def get_KodiParentIds(self, EmbyId, EmbyType):
        self.cursor.execute(f"SELECT KodiParentId FROM {EmbyType} WHERE EmbyId = ?", (EmbyId,))
        Data = self.cursor.fetchone()

        if Data and Data[0]:
            return str(Data[0]).split(";")

        return []


    def get_KodiSpecialTagIds(self):
        self.cursor.execute("SELECT KodiId FROM Tag WHERE Memo = ? OR Memo = ?", ("library", "playlist"))
        return self.cursor.fetchall()


    def get_EmbyId_KodiId_ImageUrl_by_KodiId_EmbyType(self, KodiId, EmbyType, ContentType):
        if EmbyType == "MusicArtist" and ContentType == "video":
            self.cursor.execute("SELECT EmbyId, KodiId, LibraryIds FROM MusicArtist WHERE ',' || substr(KodiId, instr(KodiId, ';') + 1) || ',' LIKE ?", (f"%,{KodiId},%",))
            Data = self.cursor.fetchone()

            if not Data:
                return "", "", "", ""

            return Data[0], Data[1], "", Data[2]

        if EmbyType == "MusicArtist" and ContentType == "music":
            self.cursor.execute("SELECT EmbyId, KodiId, LibraryIds FROM MusicArtist WHERE ',' || substr(KodiId, 1, instr(KodiId, ';') - 1) || ',' LIKE ?", (f"%,{KodiId},%",))
            Data = self.cursor.fetchone()

            if not Data:
                return "", "", "", ""

            return Data[0], Data[1], "", Data[2]

        if EmbyType == "MusicAlbum":
            self.cursor.execute("SELECT EmbyId, KodiId FROM MusicAlbum WHERE KodiId = ? OR KodiId LIKE ? OR KodiId LIKE ? OR KodiId LIKE ?", (KodiId, f"%,{KodiId}", f"{KodiId},%", f"%,{KodiId},%"))

        elif EmbyType == "Playlist" and ContentType == "music":
            self.cursor.execute("SELECT EmbyId, KodiId, EmbyArtwork FROM Playlist WHERE KodiId LIKE ?", (f"{KodiId};%",))
        elif EmbyType == "Playlist" and ContentType == "video":
            self.cursor.execute("SELECT EmbyId, KodiId, EmbyArtwork FROM Playlist WHERE KodiId LIKE ?", (f"%;{KodiId}",))
        else:
            self.cursor.execute(f"SELECT EmbyId, KodiId FROM {EmbyType} WHERE KodiId = ?", (KodiId,))

        Data = self.cursor.fetchone()

        if Data:
            if len(Data) == 3:
                return Data[0], Data[1], Data[2], ""

            return Data[0], Data[1], "", ""

        return "", "", "", ""

    def get_KodiId_ImageUrl_by_EmbyId_EmbyType(self, EmbyId, EmbyType):
        if EmbyType == "Playlist":
            self.cursor.execute("SELECT KodiId, EmbyArtwork FROM Playlist WHERE EmbyId = ?", (EmbyId,))
        else:
            self.cursor.execute(f"SELECT KodiId FROM {EmbyType} WHERE EmbyId = ?", (EmbyId,))

        Data = self.cursor.fetchone()

        if Data:
            if len(Data) == 2:
                return Data[0], Data[1]

            return Data[0], ""

        return "", ""

    def remove_item_by_KodiId(self, KodiId, EmbyType, EmbyLibraryId):
        self.cursor.execute(f"SELECT EmbyId FROM {EmbyType} WHERE KodiId = ?", (KodiId,))
        Data = self.cursor.fetchone()

        if Data:
            self.remove_item(Data[0], EmbyType, EmbyLibraryId)

    def get_EmbyId_by_KodiId_KodiType(self, KodiId, KodiType):
        if KodiType not in utils.KodiTypeMapping:
            xbmc.log(f"EMBY.database.emby_db: KodiType invalid (get_EmbyId_by_KodiId_KodiType): {KodiType}", xbmc.LOGERROR)
            return None

        self.cursor.execute(f"SELECT EmbyId FROM {utils.KodiTypeMapping[KodiType]} WHERE KodiId = ?", (KodiId,))
        Data = self.cursor.fetchone()

        if Data:
            return Data[0]

        if KodiType == "movie": # Emby homevideos are synced as "movie" content into Kodi
            self.cursor.execute("SELECT EmbyId FROM Video WHERE KodiId = ?", (KodiId,))
            Data = self.cursor.fetchone()

        if Data:
            return Data[0]

        return None

    def get_LibraryIds_by_EmbyIds(self, EmbyIds):
        LibraryIds = {}

        for EmbyId in EmbyIds:
            self.cursor.execute("SELECT EmbyLibraryId FROM EmbyLibraryMapping WHERE EmbyId = ?", (EmbyId,))
            Datas = self.cursor.fetchall()

            if Datas:
                LibraryIds[EmbyId] = Datas

        return LibraryIds

    def get_LibraryIds_by_EmbyId(self, EmbyId):
        self.cursor.execute("SELECT EmbyLibraryId FROM EmbyLibraryMapping WHERE EmbyId = ?", (EmbyId,))
        return self.cursor.fetchall()


    def get_EmbyId_EmbyFavourite_by_KodiId_KodiType(self, KodiId, KodiType):
        if KodiType not in utils.KodiTypeMapping:
            xbmc.log(f"EMBY.database.emby_db: KodiType invalid (get_EmbyId_EmbyFavourite_by_KodiId_KodiType): {KodiType}", xbmc.LOGERROR)
            return None, None

        EmbyType = utils.KodiTypeMapping[KodiType]

        if EmbyType == "MusicArtist":
            self.cursor.execute(f"SELECT EmbyId, EmbyFavourite FROM {EmbyType} WHERE KodiId LIKE ? OR KodiId LIKE ? OR KodiId LIKE ? OR KodiId LIKE ? OR KodiId LIKE ?", (f"{KodiId};%", f"%;{KodiId}", f"%;{KodiId},%", f",%{KodiId};%", f",%{KodiId},%"))
        elif EmbyType == "MusicAlbum":
            self.cursor.execute(f"SELECT EmbyId, EmbyFavourite FROM {EmbyType} WHERE KodiId = ? OR KodiId LIKE ? OR KodiId LIKE ? OR KodiId LIKE ?", (KodiId, f"%,{KodiId}", f"{KodiId},%", f"%,{KodiId},%"))
        else:
            self.cursor.execute(f"SELECT EmbyId, EmbyFavourite FROM {EmbyType} WHERE KodiId = ?", (KodiId,))

        Data = self.cursor.fetchone()

        if Data:
            return Data[0], Data[1]

        if KodiType == "movie": # Emby homevideos are synced as "movie" content into Kodi
            self.cursor.execute("SELECT EmbyId, EmbyFavourite FROM Video WHERE KodiId = ?", (KodiId,))
            Data = self.cursor.fetchone()

        if Data:
            return Data[0], Data[1]

        return None, None

    def get_playback_data_by_KodiId_KodiType(self, KodiId, KodiType):
        if KodiType == "videoversion":
            self.cursor.execute("SELECT EmbyId FROM Movie WHERE KodiFileId = ?", (KodiId,))
            Data = self.cursor.fetchone()
            EmbyType = "Movie"

            if not Data:
                self.cursor.execute("SELECT EmbyId FROM Video WHERE KodiFileId = ?", (KodiId,))
                Data = self.cursor.fetchone()
                EmbyType = "Video"
        else:
            if KodiType not in utils.KodiTypeMapping:
                xbmc.log(f"EMBY.database.emby_db: KodiType invalid (get_playback_data): {KodiType}", xbmc.LOGERROR)
                return None, None, None, None, None

            EmbyType = utils.KodiTypeMapping[KodiType]
            self.cursor.execute(f"SELECT EmbyId FROM {EmbyType} WHERE KodiId = ?", (KodiId,))
            Data = self.cursor.fetchone()

            if not Data and KodiType == "movie": # Emby homevideos are synced as "movie" content into Kodi
                self.cursor.execute("SELECT EmbyId FROM Video WHERE KodiId = ?", (KodiId,))
                Data = self.cursor.fetchone()
                EmbyType = "Video"

        if Data:
            self.cursor.execute("SELECT IntroStart, IntroEnd, CreditsStart FROM MediaSources WHERE EmbyId = ?", (Data[0],))
            Markers = self.cursor.fetchone()

            if Markers:
                return Data[0], EmbyType, Markers[0], Markers[1], Markers[2]

            return Data[0], EmbyType, None, None, None

        return None, None, None, None, None

    def get_item_by_id(self, EmbyId, EmbyType):
        if not EmbyType:
            Tables = EmbyTypes
        else:
            Tables = [EmbyType]

        for Table in Tables:
            self.cursor.execute(f"SELECT * FROM {Table} WHERE EmbyId = ?", (EmbyId,))
            Data = self.cursor.fetchone()

            if Data:
                return Data

        return []

    def get_movie_tmdb_migration(self):
        self.cursor.execute("PRAGMA user_version")
        if self.cursor.fetchone()[0] >= MovieTmdbMigrationVersion:
            return None

        self.cursor.execute("SELECT EmbyId, KodiId FROM Movie WHERE TmdbId IS NULL AND KodiId > 0")
        return self.cursor.fetchall()

    def complete_movie_tmdb_migration(self, Updates):
        self.cursor.executemany("UPDATE Movie SET TmdbId = ? WHERE EmbyId = ? AND TmdbId IS NULL", Updates)
        # Commit the backfill and its completion version in the same Gen transaction.
        self.cursor.execute(f"PRAGMA user_version = {MovieTmdbMigrationVersion}")

    def has_movie_resume_owners(self, UserId):
        # This object belongs to one open connection; a worker reopen checks again.
        if UserId not in self.MovieResumeOwnerPresence:
            self.cursor.execute("SELECT 1 FROM ResumeOwner WHERE UserId = ? AND MediaType = 'Movie' AND Provider = 'tmdb' LIMIT 1", (UserId,))
            self.MovieResumeOwnerPresence[UserId] = self.cursor.fetchone() is not None
        return self.MovieResumeOwnerPresence[UserId]

    def get_movie_resume_owner(self, UserId, EmbyId):
        self.cursor.execute("""
            SELECT movie.TmdbId, movie.KodiId, chosen.EmbyId, chosen.KodiId, owner.RetiredEmbyId
            FROM Movie AS movie
            LEFT JOIN ResumeOwner AS owner ON owner.UserId = ? AND owner.MediaType = 'Movie'
                AND owner.Provider = 'tmdb' AND owner.ProviderId = movie.TmdbId
            LEFT JOIN Movie AS chosen ON chosen.EmbyId = owner.EmbyId
                AND chosen.TmdbId = movie.TmdbId AND chosen.KodiId > 0 AND chosen.KodiFileId > 0
            WHERE movie.EmbyId = ? AND movie.TmdbId IS NOT NULL
                AND movie.KodiId > 0 AND movie.KodiFileId > 0
        """, (UserId, EmbyId))
        return self.cursor.fetchone()

    def set_movie_resume_owner(self, UserId, TmdbId, EmbyId, RetiredEmbyId):
        self.cursor.execute("""
            INSERT INTO ResumeOwner (UserId, MediaType, Provider, ProviderId, EmbyId, RetiredEmbyId)
            VALUES (?, 'Movie', 'tmdb', ?, ?, ?)
            ON CONFLICT (UserId, MediaType, Provider, ProviderId) DO UPDATE SET
                EmbyId = excluded.EmbyId, RetiredEmbyId = excluded.RetiredEmbyId
        """, (UserId, TmdbId, EmbyId, RetiredEmbyId))
        self.MovieResumeOwnerPresence[UserId] = True

    def get_movie_resume_retirements(self, UserId):
        self.cursor.execute("""
            SELECT retired.KodiId
            FROM ResumeOwner AS owner
            LEFT JOIN Movie AS chosen ON chosen.EmbyId = owner.EmbyId AND chosen.TmdbId = owner.ProviderId
            LEFT JOIN Movie AS retired ON retired.EmbyId = owner.RetiredEmbyId
                AND retired.TmdbId = owner.ProviderId AND retired.KodiId <> chosen.KodiId
            WHERE owner.UserId = ? AND owner.MediaType = 'Movie' AND owner.Provider = 'tmdb'
                AND owner.RetiredEmbyId IS NOT NULL
        """, (UserId,))
        return self.cursor.fetchall()

    def clear_movie_resume_retirements(self, UserId):
        self.cursor.execute("UPDATE ResumeOwner SET RetiredEmbyId = NULL WHERE UserId = ? AND MediaType = 'Movie' AND Provider = 'tmdb' AND RetiredEmbyId IS NOT NULL", (UserId,))

    def clear_movie_resume_owners(self):
        self.cursor.execute("DELETE FROM ResumeOwner")

    def clear_movie_resume_owner(self, UserId, EmbyId):
        self.cursor.execute("DELETE FROM ResumeOwner WHERE UserId = ? AND MediaType = 'Movie' AND Provider = 'tmdb' AND EmbyId = ? AND RetiredEmbyId IS NULL", (UserId, EmbyId))

    def get_movieversions(self, EmbyId):
        self.cursor.execute("SELECT KodiId FROM Movie WHERE EmbyId = ?", (EmbyId,))
        KodiId = self.cursor.fetchone()

        if KodiId:
            self.cursor.execute("SELECT EmbyId, KodiFileId, KodiId, KodiPathId FROM Movie WHERE KodiId = ?", (KodiId[0],))
            Data = self.cursor.fetchall()
            return Data

        return []


    # favorite infos
    def get_FavoriteInfos(self, Table):
        if Table in ("MusicArtist", "MusicAlbum", "Audio"):
            self.cursor.execute(f"SELECT EmbyFavourite, KodiId, EmbyId, LibraryIds FROM {Table}")
        elif Table in ("Series", "BoxSet"):
            self.cursor.execute(f"SELECT EmbyFavourite, KodiId, EmbyId FROM {Table}")
        elif Table == "Season":
            self.cursor.execute("SELECT EmbyFavourite, KodiId, KodiParentId, EmbyId FROM Season")
        elif Table in ("Movie", "Episode", "Video"):
            self.cursor.execute(f"SELECT EmbyFavourite, KodiFileId, KodiId, EmbyId FROM {Table}")
        elif Table == "MusicVideo":
            self.cursor.execute(f"SELECT EmbyFavourite, KodiFileId, KodiId, EmbyId, LibraryIds FROM {Table}")
        elif Table == "Playlist":
            self.cursor.execute("SELECT EmbyFavourite, KodiId, EmbyArtwork, EmbyId FROM Playlist")
        else:
            return []

        return self.cursor.fetchall()

    def get_contenttype_by_id(self, EmbyId):
        for EmbyType in EmbyTypes:
            self.cursor.execute(f"SELECT EXISTS(SELECT 1 FROM {EmbyType} WHERE EmbyId = ?)", (EmbyId, ))

            if self.cursor.fetchone()[0]:
                return EmbyType

        return ""

    def get_item_exists_by_id(self, EmbyId, EmbyType):
        self.cursor.execute(f"SELECT EXISTS(SELECT 1 FROM {EmbyType} WHERE EmbyId = ?)", (EmbyId, ))
        return self.cursor.fetchone()[0]

    def get_item_exists_multi_library(self, EmbyId, EmbyType, LibraryId):
        if LibraryId:
            self.cursor.execute(f"SELECT LibraryIds FROM {EmbyType} WHERE EmbyId = ?", (EmbyId,))
            LibraryIds = self.cursor.fetchone()

            if LibraryIds:
                Temp = LibraryIds[0].split(",")

                if str(LibraryId) in Temp:
                    return True

        return False

    def get_item_exists_multi_db(self, EmbyId, EmbyType, LibraryId, Index):
        if LibraryId:
            self.cursor.execute(f"SELECT LibraryIds FROM {EmbyType} WHERE EmbyId = ?", (EmbyId,))
            LibraryIds = self.cursor.fetchone()

            if LibraryIds:
                LibraryIds = LibraryIds[0].split(";")[Index]
                Temp = LibraryIds.split(",")

                if str(LibraryId) in Temp:
                    return True
        else:
            self.cursor.execute(f"SELECT KodiId FROM {EmbyType} WHERE EmbyId = ?", (EmbyId,))
            KodiIds = self.cursor.fetchone()

            if KodiIds:
                KodiIds = KodiIds[0].split(";")

                if KodiIds[Index]:
                    return True

        return False


    def isLinked_EmbyMusicAlbumId(self, EmbyLibraryId, EmbyMusicAlbumId):
        self.cursor.execute("SELECT EXISTS(SELECT 1 FROM EmbyLibraryMapping WHERE EmbyMusicAlbumId = ? AND EmbyLibraryId = ?)", (EmbyMusicAlbumId, EmbyLibraryId))
        return self.cursor.fetchone()[0]

    def isLinked_EmbyMusicArtistId(self, EmbyLibraryId, EmbyMusicArtistId):
        self.cursor.execute("SELECT EXISTS(SELECT 1 FROM EmbyLibraryMapping WHERE EmbyMusicArtistId = ? AND EmbyLibraryId = ?)", (EmbyMusicArtistId, EmbyLibraryId))
        return self.cursor.fetchone()[0]

    def isLinked_EmbyMusicGenreId(self, EmbyLibraryId, EmbyMusicGenreId):
        self.cursor.execute("SELECT EXISTS(SELECT 1 FROM EmbyLibraryMapping WHERE EmbyMusicGenreId = ? AND EmbyLibraryId = ?)", (EmbyMusicGenreId, EmbyLibraryId))
        return self.cursor.fetchone()[0]

    def get_KodiIds_LibraryIds_from_ContentItem(self, EmbyId, EmbyType):
        if EmbyType == "MusicVideo":
            self.cursor.execute("SELECT LibraryIds, KodiId, KodiFileId, KodiPathId FROM MusicVideo WHERE EmbyId = ?", (EmbyId,))
            Data = self.cursor.fetchone()

            if Data:
                return Data[0], Data[1], Data[2], Data[3]
        else:
            self.cursor.execute(f"SELECT LibraryIds, KodiId FROM {EmbyType} WHERE EmbyId = ?", (EmbyId,))
            Data = self.cursor.fetchone()

            if Data:
                return Data[0], Data[1], "", ""

        return "", "", "", ""

    def get_Linked_EmbyMusicArtists(self, EmbyId, EmbyLibraryId):
        EmbyMusicArtistIds = ()
        self.cursor.execute("SELECT EmbyMusicArtistId FROM EmbyLibraryMapping WHERE EmbyId = ? AND EmbyLibraryId = ? AND EmbyMusicArtistId != 0", (EmbyId, EmbyLibraryId))
        Datas = self.cursor.fetchall()

        for Data in Datas:
            EmbyMusicArtistIds += Data

        return EmbyMusicArtistIds

    def get_Linked_EmbyMusicGenres(self, EmbyId, EmbyLibraryId):
        EmbyMusicGenreIds = ()
        self.cursor.execute("SELECT EmbyMusicGenreId FROM EmbyLibraryMapping WHERE EmbyId = ? AND EmbyLibraryId = ? AND EmbyMusicGenreId != 0", (EmbyId, EmbyLibraryId))
        Datas = self.cursor.fetchall()

        for Data in Datas:
            EmbyMusicGenreIds += Data

        return EmbyMusicGenreIds

    def get_Linked_EmbyMusicAlbum(self, EmbyId, EmbyLibraryId):
        self.cursor.execute("SELECT EmbyMusicAlbumId FROM EmbyLibraryMapping WHERE EmbyId = ? AND EmbyLibraryId = ? AND EmbyMusicAlbumId != 0", (EmbyId, EmbyLibraryId))
        Data = self.cursor.fetchone()

        if Data:
            # This function is used on audio updates, check if it's the last EmbyMusicAlbumId mapping remaining. Returning "" will not delete the album.
            self.cursor.execute("SELECT COUNT(*) FROM EmbyLibraryMapping WHERE EmbyMusicAlbumId = ?", (Data[0],))
            count = self.cursor.fetchone()[0]

            if count > 1:
                return ""

            return Data[0]

        return ""

    def get_Links(self, EmbyId, EmbyLibraryId):
        Links = {"EmbyMusicAlbumId": "", "EmbyMusicArtistId": (), "EmbyMusicGenreId": ()}
        self.cursor.execute("SELECT EmbyMusicAlbumId, EmbyMusicArtistId, EmbyMusicGenreId FROM EmbyLibraryMapping WHERE EmbyId = ? AND EmbyLibraryId = ?", (EmbyId, EmbyLibraryId))
        Datas = self.cursor.fetchall()

        for Data in Datas:
            if Data[0]:
                Links["EmbyMusicAlbumId"] = Data[0]
            elif Data[1]:
                Links["EmbyMusicArtistId"] += (Data[1],)
            elif Data[2]:
                Links["EmbyMusicGenreId"] += (Data[2],)

        return Links

    def remove_item(self, EmbyId, EmbyType, EmbyLibraryId):
        DeleteItem = True

        # Delete mapping item
        if not EmbyLibraryId or EmbyLibraryId == "None":
            self.cursor.execute("DELETE FROM EmbyLibraryMapping WHERE EmbyId = ?", (EmbyId,))
            DeleteItem = True
        else:
            self.cursor.execute("DELETE FROM EmbyLibraryMapping WHERE EmbyId = ? AND EmbyLibraryId = ?", (EmbyId, EmbyLibraryId))
            self.cursor.execute("SELECT EXISTS(SELECT 1 FROM EmbyLibraryMapping WHERE EmbyId = ? AND EmbyMusicAlbumId = ? AND EmbyMusicArtistId = ? AND EmbyMusicGenreId = ?)", (EmbyId, 0, 0, 0))

            if self.cursor.fetchone()[0]:
                DeleteItem = False

        # Delete content item
        if DeleteItem:
            self.cursor.execute(f"DELETE FROM {EmbyType} WHERE EmbyId = ?", (EmbyId,))

            if EmbyType == "Movie":
                self.cursor.execute("DELETE FROM ResumeOwner WHERE MediaType = 'Movie' AND EmbyId = ?", (EmbyId,))

            if EmbyType in ("Movie", "Video", "MusicVideo", "Episode", "Audio"):
                self.remove_item_streaminfos(EmbyId)

        return DeleteItem

    def update_references(self, EmbyId, KodiId, EmbyType, LibraryIds):
        self.cursor.execute(f"UPDATE {EmbyType} SET KodiId = ?, LibraryIds = ? WHERE EmbyId = ?", (KodiId, LibraryIds, EmbyId))

    def get_KodiId_by_EmbyPresentationKey(self, EmbyType, EmbyPresentationKey):
        if EmbyPresentationKey:
            self.cursor.execute(f"SELECT KodiId FROM {EmbyType} WHERE EmbyPresentationKey = ?", (EmbyPresentationKey,))
            KodiIds = self.cursor.fetchall()

            if KodiIds:
                for KodiId in KodiIds:
                    if KodiId[0]:
                        return KodiId[0]

        return None

    def get_EmbyId_by_EmbyPresentationKey(self, EmbyPresentationKey, EmbyType):
        self.cursor.execute(f"SELECT EmbyId FROM {EmbyType} WHERE EmbyPresentationKey = ?", (EmbyPresentationKey,))
        Data = self.cursor.fetchone()

        if Data:
            return Data[0]

        return None

    def get_EmbyIds_by_EmbyPresentationKey(self, EmbyPresentationKey, EmbyType):
        self.cursor.execute(f"SELECT EmbyId FROM {EmbyType} WHERE EmbyPresentationKey = ?", (EmbyPresentationKey,))
        EmbyIds = self.cursor.fetchall()
        ReturnData = ()

        for EmbyId in EmbyIds:
            self.cursor.execute("SELECT EmbyLibraryId FROM EmbyLibraryMapping WHERE EmbyId = ?", (EmbyId[0],))
            LibraryIds = self.cursor.fetchall()
            ReturnData += ((EmbyId[0], LibraryIds),)

        return ReturnData

    def get_boxsets(self):
        self.cursor.execute("SELECT EmbyId FROM BoxSet")
        return self.cursor.fetchall()


    def get_KodiId_by_EmbyId(self, EmbyId):
        for EmbyType in EmbyTypesWithKodiId:
            self.cursor.execute(f"SELECT KodiId FROM {EmbyType} WHERE EmbyId = ?", (EmbyId,))
            Data = self.cursor.fetchone()

            if Data:
                return Data[0], utils.EmbyTypeMapping[EmbyType]

        return None, None

    def get_KodiId_by_EmbyId_EmbyType(self, EmbyId, EmbyType):
        self.cursor.execute(f"SELECT KodiId FROM {EmbyType} WHERE EmbyId = ?", (EmbyId,))
        Data = self.cursor.fetchone()

        if Data:
            return Data[0]

        return None

    def get_similar_item(self, EmbyId, EmbyType):
        self.cursor.execute(f"""
            SELECT Item.KodiId, Library.EmbyLibraryName
            FROM {EmbyType} AS Item
            LEFT JOIN EmbyLibraryMapping AS Mapping ON Mapping.EmbyId = Item.EmbyId
            LEFT JOIN LibrarySyncedMirrow AS Library ON Library.EmbyLibraryId = Mapping.EmbyLibraryId
            WHERE Item.EmbyId = ?
            ORDER BY Mapping.EmbyLibraryId, Library.EmbyLibraryName
        """, (EmbyId,))
        return self.cursor.fetchall()

    def get_metadata_by_EmbyId_EmbyType(self, EmbyId, EmbyContentType):
        ContentData = None

        if EmbyContentType:
            self.cursor.execute(f"SELECT KodiId FROM {EmbyContentType} WHERE EmbyId = ?", (EmbyId,))
            ContentData = self.cursor.fetchone()
        else:
            for EmbyType in EmbyTypesWithKodiId:
                self.cursor.execute(f"SELECT KodiId FROM {EmbyType} WHERE EmbyId = ?", (EmbyId,))
                ContentData = self.cursor.fetchone()

                if ContentData:
                    EmbyContentType = EmbyType
                    break

        if not ContentData:
            return 0, "", []

        MediaSourcesData = []

        if EmbyContentType not in EmbyFolderTypes:
            self.cursor.execute("SELECT IntroStart, IntroEnd, CreditsStart, Size, Name, MediaSourceId, Path FROM MediaSources WHERE EmbyId = ?", (EmbyId,))
            MediaSourcesData = self.cursor.fetchall()

        if not MediaSourcesData:
            return ContentData[0], "", []

        MediaSources = len(MediaSourcesData) * [{}]

        for MediaSourceIndex, MediaSourceData in enumerate(MediaSourcesData):
            MediaSources[MediaSourceIndex] = {'IntroStartPositionTicks': MediaSourceData[0], 'IntroEndPositionTicks': MediaSourceData[1], 'CreditsPositionTicks': MediaSourceData[2], 'Size': MediaSourceData[3], 'Name': MediaSourceData[4], 'Id': MediaSourceData[5], 'Path': MediaSourceData[6], 'KodiStreams': {'Subtitle': [], 'Audio': [], 'Video': []}, 'IndexMappingAudioEmby': {}, 'IndexMappingAudioKodi': {}, 'IndexMappingVideoEmby': {}, 'IndexMappingVideoKodi': {}, 'IndexMappingSubtitleEmby': {}, 'IndexMappingSubtitleKodi': {}, 'MediaStreams': []}
            self.cursor.execute("SELECT EmbyIndex, KodiIndex FROM AudioStreams WHERE EmbyId = ? AND MediaSourceId = ?", (EmbyId, MediaSourceData[5]))
            AudioStreamsData = self.cursor.fetchall()

            if AudioStreamsData:
                MediaSources[MediaSourceIndex]['KodiStreams']['Audio'] = len(AudioStreamsData) * [{}]

                for AudioStreamData in AudioStreamsData:
                    MediaSources[MediaSourceIndex]['KodiStreams']['Audio'][AudioStreamData[1]] = {'Index': AudioStreamData[0]}
                    MediaSources[MediaSourceIndex]['IndexMappingAudioEmby'][str(AudioStreamData[0])] = int(AudioStreamData[1])
                    MediaSources[MediaSourceIndex]['IndexMappingAudioKodi'][int(AudioStreamData[1])] = str(AudioStreamData[0])

            self.cursor.execute("SELECT EmbyIndex, KodiIndex, Width, Codec, Bitrate, EmbyIndex FROM VideoStreams WHERE EmbyId = ? AND MediaSourceId = ?", (EmbyId, MediaSourceData[5]))
            VideoStreamsData = self.cursor.fetchall()

            if VideoStreamsData:
                MediaSources[MediaSourceIndex]['KodiStreams']['Video'] = len(VideoStreamsData) * [{}]

                for VideoStreamData in VideoStreamsData:
                    MediaSources[MediaSourceIndex]['KodiStreams']['Video'][VideoStreamData[1]] = {'Index': VideoStreamData[0]}
                    MediaSources[MediaSourceIndex]['IndexMappingVideoEmby'][str(VideoStreamData[0])] = int(VideoStreamData[1])
                    MediaSources[MediaSourceIndex]['IndexMappingVideoKodi'][int(VideoStreamData[1])] = str(VideoStreamData[0])
                    MediaSources[MediaSourceIndex]['MediaStreams'].append({'Type': "Video", 'BitRate': VideoStreamData[4], 'Codec': VideoStreamData[3], 'Width': VideoStreamData[2], "Index": VideoStreamData[5]})

            self.cursor.execute("SELECT EmbyIndex, KodiIndex FROM SubtitleStreams WHERE EmbyId = ? AND MediaSourceId = ?", (EmbyId, MediaSourceData[5]))
            SubtitleStreamsData = self.cursor.fetchall()

            if SubtitleStreamsData:
                MediaSources[MediaSourceIndex]['KodiStreams']['Subtitle'] = len(SubtitleStreamsData) * [{}]

                for SubtitleStreamData in SubtitleStreamsData:
                    MediaSources[MediaSourceIndex]['KodiStreams']['Subtitle'][SubtitleStreamData[1]] = {'Index': SubtitleStreamData[0]}
                    MediaSources[MediaSourceIndex]['IndexMappingSubtitleEmby'][str(SubtitleStreamData[0])] = int(SubtitleStreamData[1])
                    MediaSources[MediaSourceIndex]['IndexMappingSubtitleKodi'][int(SubtitleStreamData[1])] = str(SubtitleStreamData[0])

        return ContentData[0], EmbyContentType, versions.sort_sources(MediaSources)

    def get_KodiId_LibraryId_by_EmbyId_EmbyType(self, EmbyId, EmbyType):
        self.cursor.execute(f"SELECT KodiId, LibraryIds FROM {EmbyType} WHERE EmbyId = ?", (EmbyId,))
        Data = self.cursor.fetchone()

        if Data:
            return Data[0], Data[1]

        return None, None

    def get_Records_by_EmbyType(self, EmbyType):
        self.cursor.execute(f"SELECT * FROM {EmbyType}")
        return self.cursor.fetchall()


    def get_MusicAlbum_by_EmbyId(self, EmbyId):
        self.cursor.execute("SELECT KodiId, LibraryIds FROM MusicAlbum WHERE EmbyId = ?", (EmbyId,))
        Data = self.cursor.fetchone()

        if Data:
            return Data[0].split(","), Data[1].split(",")

        return [], []

    def get_KodiId_by_EmbyId_multi_db(self, EmbyId, EmbyType, KodiDB):
        self.cursor.execute(f"SELECT KodiId FROM {EmbyType} WHERE EmbyId = ?", (EmbyId,))
        Data = self.cursor.fetchone()

        if Data:
            Data = Data[0].split(";")

            if KodiDB == "video":
                return Data[1]

            return Data[0]

        return ""

    # stream infos
    def remove_item_streaminfos(self, EmbyId):
        self.cursor.execute("DELETE FROM MediaSources WHERE EmbyId = ?", (EmbyId,))
        self.cursor.execute("DELETE FROM VideoStreams WHERE EmbyId = ?", (EmbyId,))
        self.cursor.execute("DELETE FROM AudioStreams WHERE EmbyId = ?", (EmbyId,))
        self.cursor.execute("DELETE FROM SubtitleStreams WHERE EmbyId = ?", (EmbyId,))

    def add_streamdata(self, EmbyId, MediaSources):
        self.remove_item_streaminfos(EmbyId)
        SQLData = []
        SQLData1 = []
        SQLData2 = []
        SQLData3 = []

        for MediaSource in versions.sort_sources(MediaSources):
            SQLData.append((EmbyId, MediaSource['Id'], MediaSource['Path'], MediaSource['Name'], MediaSource['Size'], MediaSource['IntroStartPositionTicks'], MediaSource['IntroEndPositionTicks'], MediaSource['CreditsPositionTicks']))

            for IndexVideoStream, VideoStream in enumerate(MediaSource['KodiStreams']['Video']):
                SQLData1.append((EmbyId, MediaSource['Id'], VideoStream['Index'], VideoStream['codec'], VideoStream['BitRate'], VideoStream['width'], IndexVideoStream))

            for IndexAudioStream, AudioStream in enumerate(MediaSource['KodiStreams']['Audio']):
                SQLData2.append((EmbyId, MediaSource['Id'], AudioStream['Index'], AudioStream['DisplayTitle'], AudioStream['codec'], AudioStream['BitRate'], IndexAudioStream))

            for IndexSubtitleStream, SubtitleStream in enumerate(MediaSource['KodiStreams']['Subtitle']):
                SQLData3.append((EmbyId, MediaSource['Id'], SubtitleStream['Index'], SubtitleStream['codec'], SubtitleStream['language'], SubtitleStream['DisplayTitle'], SubtitleStream['external'], IndexSubtitleStream))

        if SQLData:
            self.cursor.executemany("INSERT OR REPLACE INTO MediaSources (EmbyId, MediaSourceId, Path, Name, Size, IntroStart, IntroEnd, CreditsStart) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", SQLData)

        if SQLData1:
            self.cursor.executemany("INSERT OR REPLACE INTO VideoStreams (EmbyId, MediaSourceId, EmbyIndex, Codec, BitRate, Width, KodiIndex) VALUES (?, ?, ?, ?, ?, ?, ?)", SQLData1)

        if SQLData2:
            self.cursor.executemany("INSERT OR REPLACE INTO AudioStreams (EmbyId, MediaSourceId, EmbyIndex, DisplayTitle, Codec, BitRate, KodiIndex) VALUES (?, ?, ?, ?, ?, ?, ?)", SQLData2)

        if SQLData3:
            self.cursor.executemany("INSERT OR REPLACE INTO SubtitleStreams (EmbyId, MediaSourceId, EmbyIndex, Codec, Language, DisplayTitle, External, KodiIndex) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", SQLData3)

        del SQLData
        del SQLData1
        del SQLData2
        del SQLData3
