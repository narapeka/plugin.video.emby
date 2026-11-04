import xbmc
from helper import utils
from . import common_db

class MusicDatabase:
    def __init__(self, cursor):
        self.cursor = cursor
        self.common_db = common_db.CommonDatabase(cursor)
        self.Index = {}

    def add_Index(self):
        self.cursor.execute("INSERT OR REPLACE INTO role(idRole, strRole) VALUES (?, ?)", (1, "artist"))
        self.cursor.execute("INSERT OR REPLACE INTO role(idRole, strRole) VALUES (?, ?)", (2, "composer"))

        try: # xbox issue
            self.cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_album_strType'")
            IndexTest = self.cursor.fetchone()

            if not IndexTest:
                self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_album_strType on album (strType)")
                self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_album_dateadded on album (dateAdded)")
                self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_song_dateadded on song (dateAdded)")
                self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_song_comment_strGenres on song (comment, strGenres)")
                self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_artist_strDisambiguation on artist (strDisambiguation)")
                self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_album_strReleaseType on album (strReleaseType)")
                self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_song_idAlbum_lastplayed_iTimesPlayed on song (idAlbum, lastplayed, iTimesPlayed)")
                self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_song_strMusicBrainzTrackID on song (strMusicBrainzTrackID)")
                self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_song_strArtistDisp_strTitle on song (strArtistDisp, strTitle)")
                self.cursor.execute("ANALYZE")
                self.cursor.connection.commit()
                self.cursor.execute("BEGIN IMMEDIATE TRANSACTION")
        except Exception as Error:
            xbmc.log(f"EMBY.database.music_db: Database add index error: {Error}", xbmc.LOGERROR)

    def delete_Index(self):
        try: # xbox issue
            self.cursor.execute("DROP INDEX IF EXISTS idx_album_strType")
            self.cursor.execute("DROP INDEX IF EXISTS idx_album_dateadded")
            self.cursor.execute("DROP INDEX IF EXISTS idx_song_dateadded")
            self.cursor.execute("DROP INDEX IF EXISTS idx_song_comment_strGenres")
            self.cursor.execute("DROP INDEX IF EXISTS idx_artist_strDisambiguation")
            self.cursor.execute("DROP INDEX IF EXISTS idx_album_strReleaseType")
            self.cursor.execute("DROP INDEX IF EXISTS idx_song_idAlbum_lastplayed_iTimesPlayed")
            self.cursor.execute("DROP INDEX IF EXISTS idx_song_strMusicBrainzTrackID")
            self.cursor.execute("DROP INDEX IF EXISTS idx_song_strArtistDisp_strTitle")
            self.cursor.execute("ANALYZE")
            self.cursor.connection.commit()
            self.cursor.execute("BEGIN IMMEDIATE TRANSACTION")
        except Exception as Error:
            xbmc.log(f"EMBY.database.music_db: Database delete index error: {Error}", xbmc.LOGERROR)

    # Make sure rescan and kodi db set
    def disable_rescan(self, Timestamp):
        self.cursor.execute("DELETE FROM versiontagscan")
        self.cursor.execute("INSERT OR REPLACE INTO versiontagscan(idVersion, iNeedsScan, lastscanned, artistlinksupdated, genresupdated) VALUES (?, ?, ?, ?, ?)", (str(utils.DatabaseFiles['music-version']), "0", Timestamp, Timestamp, Timestamp))

    def get_ArtistSortname(self, KodiArtistId):
        self.cursor.execute("SELECT strSortName FROM artist WHERE idArtist = ? ", (KodiArtistId,))
        Data = self.cursor.fetchone()

        if Data:
            return Data[0]

        return ""

    # artists
    def add_musicartist_link(self, ArtistId, MediaId, Role, Order, Name):
        self.cursor.execute("INSERT OR REPLACE INTO song_artist(idArtist, idSong, idRole, iOrder, strArtist) VALUES (?, ?, ?, ?, ?)", (ArtistId, MediaId, Role, Order, Name))

    def del_musicartist(self, ArtistId):
        self.cursor.execute("DELETE FROM art WHERE media_id = ? AND media_type = ?", (ArtistId, "artist"))
        self.cursor.execute("DELETE FROM song_artist WHERE idArtist = ?", (ArtistId,))
        self.cursor.execute("DELETE FROM album_artist WHERE idArtist = ?", (ArtistId,))
        self.cursor.execute("DELETE FROM artist WHERE idArtist = ?", (ArtistId,))
        self.cursor.execute("DELETE FROM removed_link")

    def get_Artist(self, ArtistId):
        Artists = False
        self.cursor.execute("SELECT strArtist, strImage FROM artist WHERE idArtist = ?", (ArtistId,))
        Data = self.cursor.fetchone()

        if Data:
            self.cursor.execute("SELECT EXISTS(SELECT 1 FROM song_artist WHERE idArtist = ?)", (ArtistId,))

            if self.cursor.fetchone()[0]:
                Artists = True

            return Data[0], Data[1], Artists

        return "", "", False

    def add_artist(self, ArtistName, MusicbrainzId, Genre, Bio, Thumb, LastScraped, SortName, DateAdded, LibraryId):
        self.cursor.execute("SELECT coalesce(max(idArtist), 0) FROM artist")
        ArtistId = self.cursor.fetchone()[0] + 1

        while MusicbrainzId != "UNKNOWN ERROR":
            try:
                self.cursor.execute("INSERT INTO artist(idArtist, strArtist, strMusicBrainzArtistID, strGenres, strBiography, strImage, lastScraped, strSortName, dateAdded, strDisambiguation) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (ArtistId, ArtistName, MusicbrainzId, Genre, Bio, Thumb, LastScraped, SortName, DateAdded, f"EmbyLibraryId-{LibraryId}"))
                return ArtistId
            except Exception as error:
                MusicbrainzId = errorhandler_MusicBrainzID(ArtistName, MusicbrainzId, error)

        return None

    def update_artist(self, KodiItemId, ArtistName, MusicbrainzId, Genre, Bio, Thumb, LastScraped, SortName, DateAdded):
        while MusicbrainzId != "UNKNOWN ERROR":
            try:
                self.cursor.execute("UPDATE artist SET strArtist = ?, strMusicBrainzArtistID = ?, strGenres = ?, strBiography = ?, strImage = ?, lastScraped = ?, strSortName = ?, dateAdded = ? WHERE idArtist = ?", (ArtistName, MusicbrainzId, Genre, Bio, Thumb, LastScraped, SortName, DateAdded, KodiItemId))
                break
            except Exception as error:
                MusicbrainzId = errorhandler_MusicBrainzID(ArtistName, MusicbrainzId, error)


    def get_artistid_by_songid(self, KodiId):
        self.cursor.execute("SELECT idArtist FROM song_artist WHERE idSong = ? AND idRole = ? ORDER BY iOrder LIMIT 1", (KodiId, 1))
        ArtistId = self.cursor.fetchone()

        if not ArtistId:
            return None

        return ArtistId[0]

    def get_albumartistid_by_albumid(self, KodiId):
        self.cursor.execute("SELECT idArtist FROM album_artist WHERE idAlbum = ? ORDER BY iOrder LIMIT 1", (KodiId,))
        ArtistId = self.cursor.fetchone()

        if not ArtistId:
            return None

        return ArtistId[0]

    # album
    def update_album_info_by_audio(self, KodiAlbumId, DiscNumber, Tracknumber, isPlaylist):
        self.cursor.execute("UPDATE OR IGNORE album SET iDiscTotal = CASE WHEN ? IS NOT NULL AND ? AND iDiscTotal < ? THEN ? ELSE iDiscTotal END, strReleaseType = CASE WHEN ? THEN 'album' WHEN ? THEN CASE WHEN ? > 1 OR (? AND ? > 1) THEN 'album' WHEN strReleaseType IS NULL OR strReleaseType != 'album' THEN 'single' ELSE strReleaseType END ELSE 'album' END WHERE idAlbum = ?", (DiscNumber, DiscNumber, DiscNumber, DiscNumber, isPlaylist, Tracknumber, Tracknumber, DiscNumber, DiscNumber, KodiAlbumId))

    def add_album(self, Title, Artist, ProductionYear, PremiereDate, Genre, Bio, Thumb, CommunityRating, LastScraped, DateAdded, MusicBrainzAlbumID, UniqueIdReleaseGroup, Compilation, Studios, RunTime, ArtistSort, LibraryId):
        self.cursor.execute("SELECT coalesce(max(idAlbum), 0) FROM album")
        idAlbum = self.cursor.fetchone()[0] + 1

        if not RunTime:
            RunTime = 0

        if CommunityRating:
            Rating = float(CommunityRating)
        else:
            Rating = 0.0

        while MusicBrainzAlbumID != "UNKNOWN ERROR":
            try: # strReleaseType will be set to single, audio content sync will update this info
                self.cursor.execute("INSERT INTO album(idAlbum, strAlbum, strMusicBrainzAlbumID, strReleaseGroupMBID, strReleaseType, strArtistDisp, strReleaseDate, strOrigReleaseDate, strGenres, strReview, strImage, fRating, lastScraped, dateAdded, bCompilation, strLabel, iAlbumDuration, strArtistSort, strType) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (idAlbum, Title, MusicBrainzAlbumID, UniqueIdReleaseGroup, "single", Artist, ProductionYear, PremiereDate, Genre, Bio, Thumb, Rating, LastScraped, DateAdded, Compilation, Studios, RunTime, ArtistSort, f"EmbyLibraryId-{LibraryId}"))
                return idAlbum
            except Exception as error:
                MusicBrainzAlbumID = errorhandler_MusicBrainzID(Title, MusicBrainzAlbumID, error)

        return None

    def update_album(self, KodiItemId, Title, Artist, ProductionYear, PremiereDate, Genre, Bio, Thumb, CommunityRating, LastScraped, DateAdded, MusicBrainzAlbumID, UniqueIdReleaseGroup, Compilation, Studios, RunTime, ArtistSort):
        if not RunTime:
            RunTime = 0

        if CommunityRating:
            Rating = float(CommunityRating)
        else:
            Rating = 0.0

        while MusicBrainzAlbumID != "UNKNOWN ERROR":
            try:
                self.cursor.execute("UPDATE album SET strAlbum = ?, strMusicBrainzAlbumID = ?, strReleaseGroupMBID = ?, strArtistDisp = ?, strReleaseDate = ?, strOrigReleaseDate = ?, strGenres = ?, strReview = ?, strImage = ?, fRating = ?, lastScraped = ?, dateAdded = ?, bCompilation = ?, strLabel = ?, iAlbumDuration = ?, strArtistSort = ? WHERE idAlbum = ?", (Title, MusicBrainzAlbumID, UniqueIdReleaseGroup, Artist, ProductionYear, PremiereDate, Genre, Bio, Thumb, Rating, LastScraped, DateAdded, Compilation, Studios, RunTime, ArtistSort, KodiItemId))
                return
            except Exception as error:
                MusicBrainzAlbumID = errorhandler_MusicBrainzID(Title, MusicBrainzAlbumID, error)


    def delete_link_album_artist(self, idAlbum):
        self.cursor.execute("DELETE FROM album_artist WHERE idAlbum = ?", (idAlbum,))
        self.cursor.execute("DELETE FROM removed_link")

    def add_albumartist_link(self, ArtistId, idAlbum, Order, Name):
        self.cursor.execute("INSERT OR REPLACE INTO album_artist(idArtist, idAlbum, iOrder, strArtist) VALUES (?, ?, ?, ?)", (ArtistId, idAlbum, Order, Name))


    # song


    def add_song_tag(self, KodiId, Tag): # e.g. for playlists
        self.cursor.execute("SELECT comment FROM song WHERE idSong = ?", (KodiId,))
        Comment = self.cursor.fetchone()

        if Comment:
            Comment = f"{Comment[0]}\n{Tag}"
            self.cursor.execute("UPDATE song SET comment = ? WHERE idSong = ?", (Comment, KodiId))

    def add_song(self, KodiPathId, AlbumId, Artist, Genre, Title, Index, Runtime, PremiereDate, Year, Filename, CommunityRating, Comment, DateAdded, BitRate, SampleRate, Channels, MusicBrainzTrackID, ArtistSort, LibraryId):
        if CommunityRating:
            Rating = float(CommunityRating)
        else:
            Rating = 0.0

        self.cursor.execute("SELECT coalesce(max(idSong), 0) FROM song")
        idSong = self.cursor.fetchone()[0] + 1

        if Comment:
            Comment = f"{Comment}\nEmbyLibraryId-{LibraryId}"
        else:
            Comment = f"EmbyLibraryId-{LibraryId}"

        BitRate, SampleRate, Channels, _ = set_metadata_song(Artist, Title, BitRate, SampleRate, Channels, None)

        while MusicBrainzTrackID != "UNKNOWN ERROR":
            try:
                self.cursor.execute("INSERT INTO song(idSong, idAlbum, idPath, strArtistDisp, strGenres, strTitle, iTrack, iDuration, strOrigReleaseDate, strReleaseDate, strFileName, rating, comment, dateAdded, iBitRate, iSampleRate, iChannels, strMusicBrainzTrackID, strArtistSort) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (idSong, AlbumId, KodiPathId, Artist, Genre, Title, Index, Runtime, Year, PremiereDate, Filename, Rating, Comment, DateAdded, BitRate, SampleRate, Channels, MusicBrainzTrackID, ArtistSort))
                return idSong
            except Exception as error:
                MusicBrainzTrackID = errorhandler_MusicBrainzID(Title, MusicBrainzTrackID, error)

        return None

    def update_song(self, KodiItemId, KodiPathId, AlbumId, Artist, Genre, Title, Index, Runtime, PremiereDate, Year, Filename, CommunityRating, Comment, DateAdded, BitRate, SampleRate, Channels, MusicBrainzTrackID, ArtistSort, KodiPath, PlaylistId):
        if CommunityRating:
            Rating = float(CommunityRating)
        else:
            Rating = 0.0

        # Get/keep current Tags
        self.cursor.execute("SELECT comment FROM song WHERE idSong = ?", (KodiItemId,))
        CommentCurrent = self.cursor.fetchone()

        if not CommentCurrent:
            xbmc.log(f"EMBY.database.music_db: update_song error: {KodiItemId}", xbmc.LOGERROR)
            return

        CommentsCurrent = CommentCurrent[0].split("\n")
        EmbyLibraryIds = ()
        EmbyPlaylistIds = ()

        for CommentCurrent in CommentsCurrent:
            if CommentCurrent.startswith("EmbyLibraryId-"):
                Tag = CommentCurrent.split("-")
                EmbyLibraryIds += (Tag[1],)
            elif CommentCurrent.startswith("EmbyPlaylistId-"):
                Tag = CommentCurrent.split("-")
                EmbyPlaylistIds += (Tag[1],)

        if not Comment: # Comment could be None
            Comment = ""

        for EmbyLibraryId in EmbyLibraryIds:
            if Comment:
                Comment += f"\nEmbyLibraryId-{EmbyLibraryId}"
            else:
                Comment += f"EmbyLibraryId-{EmbyLibraryId}"

        for EmbyPlaylistId in EmbyPlaylistIds:
            if Comment:
                Comment += f"\nEmbyPlaylistId-{EmbyPlaylistId}"
            else:
                Comment += f"EmbyPlaylistId-{EmbyPlaylistId}"

        # Update song
        BitRate, SampleRate, Channels, _ = set_metadata_song(Artist, Title, BitRate, SampleRate, Channels, None)

        if EmbyPlaylistIds and (not PlaylistId or str(PlaylistId) not in EmbyPlaylistIds): # Do not update existing track numbers when metadata from playlist
            while MusicBrainzTrackID != "UNKNOWN ERROR":
                try:
                    self.cursor.execute("UPDATE song SET idAlbum = ?, idPath = ?, strArtistDisp = ?, strGenres = ?, strTitle = ?, iDuration = ?, strOrigReleaseDate = ?, strReleaseDate = ?, strFileName = ?, rating = ?, comment = ?, dateAdded = ?, iBitRate = ?, iSampleRate = ?, iChannels = ?, strMusicBrainzTrackID = ?, strArtistSort = ? WHERE idSong = ?", (AlbumId, KodiPathId, Artist, Genre, Title, Runtime, Year, PremiereDate, Filename, Rating, Comment, DateAdded, BitRate, SampleRate, Channels, MusicBrainzTrackID, ArtistSort, KodiItemId))
                    break
                except Exception as error:
                    MusicBrainzTrackID = errorhandler_MusicBrainzID(Title, MusicBrainzTrackID, error)
        else:
            while MusicBrainzTrackID != "UNKNOWN ERROR":
                try:
                    self.cursor.execute("UPDATE song SET idAlbum = ?, idPath = ?, strArtistDisp = ?, strGenres = ?, strTitle = ?, iTrack = ?, iDuration = ?, strOrigReleaseDate = ?, strReleaseDate = ?, strFileName = ?, rating = ?, comment = ?, dateAdded = ?, iBitRate = ?, iSampleRate = ?, iChannels = ?, strMusicBrainzTrackID = ?, strArtistSort = ? WHERE idSong = ?", (AlbumId, KodiPathId, Artist, Genre, Title, Index, Runtime, Year, PremiereDate, Filename, Rating, Comment, DateAdded, BitRate, SampleRate, Channels, MusicBrainzTrackID, ArtistSort, KodiItemId))
                    break
                except Exception as error:
                    MusicBrainzTrackID = errorhandler_MusicBrainzID(Title, MusicBrainzTrackID, error)

        if MusicBrainzTrackID != "UNKNOWN ERROR":
            self.cursor.execute("UPDATE path SET strPath = ? WHERE idPath = ?", (KodiPath, KodiPathId))

    def delete_link_song_artist(self, SongId):
        self.cursor.execute("DELETE FROM song_artist WHERE idSong = ?", (SongId,))
        self.cursor.execute("DELETE FROM removed_link")

    def update_song_metadata(self, iTimesPlayed, lastplayed, idSong):
        self.cursor.execute("UPDATE song SET iTimesPlayed = ?, lastplayed = ? WHERE idSong = ?", (iTimesPlayed, lastplayed, idSong))

    def get_song_metadata_for_listitem(self, KodiId):
        self.cursor.execute("SELECT strArtists, strGenres, strTitle, iTrack, iDuration, strReleaseDate, strMusicBrainzTrackID, iTimesPlayed, comment, strAlbum, strPath, strAlbumArtists, strFileName, rating, strVideoURL, lastplayed, idAlbum FROM songview WHERE idSong = ?", (KodiId,))
        SongData = self.cursor.fetchone()

        if not SongData:
            return {}

        Artwork = self.common_db.get_artwork(KodiId, "song", "")
        Artwork.update(self.common_db.get_artwork(SongData[16], "album", "album."))
        ArtistId = self.get_artistid_by_songid(KodiId)
        Artwork.update(self.common_db.get_artwork(ArtistId, "artist", "artist."))
        AlbumArtistId = self.get_albumartistid_by_albumid(SongData[16])
        Artwork.update(self.common_db.get_artwork(AlbumArtistId, "artist", "albumartist."))

        if SongData[3]:
            Track = SongData[3] % 65536
            Disc = int(int(SongData[3]) / 65536)
        else:
            Track = None
            Disc = None

        if SongData[10].endswith('|redirect-limit=1000&failonerror=false'):
            Pathandfilename = f"{SongData[10].replace('|redirect-limit=1000&failonerror=false', '')}{SongData[12]}|redirect-limit=1000&failonerror=false"
        else:
            Pathandfilename = f"{SongData[10]}{SongData[12]}"

        return {'KodiMetadataMediatype': "song", "KodiMetadataDBID": KodiId, 'KodiMetadataArtist': SongData[0], 'KodiMetadataGenre': SongData[1], 'KodiMetadataTitle': SongData[2], 'KodiMetadataTrack': Track, 'KodiMetadataDisc': Disc, 'KodiMetadataDuration': SongData[4], 'KodiMetadataReleasedate': SongData[5], 'KodiMetadataYear': utils.convert_to_local(SongData[5], False, True), 'KodiMetadataMusicbrainztrackId': SongData[6], 'KodiMetadataPlaycount': SongData[7], 'KodiMetadataComment': SongData[8], 'KodiMetadataAlbum': SongData[9], 'KodiMetadataPath': SongData[10], 'KodiMetadataAlbumartists': SongData[11], 'KodiMetadataPathandfilename': Pathandfilename, 'KodiMetadataProperties': {'IsFolder': 'false', 'IsPlayable': 'true'}, 'KodiMetadataArtwork': Artwork, 'KodiMetadataCommunityRating': SongData[13], 'KodiMetadataSongVideoURL': SongData[14], 'KodiMetadataPlaybackPositionTicks': 0,'KodiMetadataLastplayed': SongData[15]}


    # genres
    def get_genre_name(self, GenreId):
        self.cursor.execute("SELECT strGenre FROM genre WHERE idGenre = ?", (GenreId,))
        Row = self.cursor.fetchone()
        return Row[0] if Row else ""

    def get_genre(self, LibraryId):
        self.cursor.execute(
            "SELECT DISTINCT genre.strGenre FROM genre JOIN song_genre USING (idGenre) "
            "JOIN song USING (idSong) WHERE instr(char(10) || song.comment || char(10), ?) > 0 "
            "ORDER BY genre.strGenre COLLATE NOCASE",
            (f"\nEmbyLibraryId-{LibraryId}\n",))
        return [Name for Name, in self.cursor.fetchall() if Name]

    def add_genre_link(self, GenreId, MediaId, Order):
        self.cursor.execute("INSERT OR REPLACE INTO song_genre(idGenre, idSong, iOrder) VALUES (?, ?, ?)", (GenreId, MediaId, Order))

    def update_genre(self, GenreName, GenreId):
        GenreNameMod = GenreName

        while True:
            try:
                self.cursor.execute("UPDATE genre SET strGenre = ? WHERE idGenre = ?", (GenreNameMod, GenreId))
                break
            except Exception:
                GenreNameMod += " "

    def get_add_genre(self, GenreName):
        self.cursor.execute("SELECT idGenre FROM genre WHERE strGenre = ?", (GenreName,))
        Data = self.cursor.fetchone()

        if Data:
            return Data[0]

        self.cursor.execute("SELECT coalesce(max(idGenre), 0) FROM genre")
        GenreId = self.cursor.fetchone()[0] + 1
        self.cursor.execute("INSERT INTO genre(idGenre, strGenre) VALUES (?, ?)", (GenreId, GenreName))
        return GenreId


    def delete_genre_by_Id(self, GenreId):
        GenreName = ""
        self.cursor.execute("SELECT strGenre FROM genre WHERE idGenre = ?", (GenreId,))
        Data = self.cursor.fetchone()

        if Data:
            GenreName = Data[0]

        self.cursor.execute("DELETE FROM song_genre WHERE idGenre = ?", (GenreId,))
        self.cursor.execute("DELETE FROM genre WHERE idGenre = ?", (GenreId,))
        return GenreName


    def delete_album(self, idAlbum):
        self.cursor.execute("DELETE FROM album_artist WHERE idAlbum = ?", (idAlbum,))
        self.cursor.execute("DELETE FROM album_source WHERE idAlbum = ?", (idAlbum,))
        self.common_db.delete_artwork(idAlbum, "album")
        self.cursor.execute("DELETE FROM removed_link")
        self.cursor.execute("DELETE FROM album WHERE idAlbum = ?", (idAlbum,))

    def delete_song(self, idSong):
        self.cursor.execute("DELETE FROM song_artist WHERE idSong = ?", (idSong,))
        self.cursor.execute("DELETE FROM song WHERE idSong = ?", (idSong,))
        self.common_db.delete_artwork(idSong, "song")
        self.cursor.execute("DELETE FROM removed_link")

    # Path
    def delete_path(self, KodiPath):
        self.cursor.execute("DELETE FROM path WHERE strPath = ?", (KodiPath,))

    def get_add_path(self, strPath):
        self.cursor.execute("SELECT idPath FROM path WHERE strPath = ?", (strPath,))
        Data = self.cursor.fetchone()

        if Data:
            return Data[0]

        self.cursor.execute("SELECT coalesce(max(idPath), 0) FROM path")
        path_id = self.cursor.fetchone()[0] + 1
        self.cursor.execute("INSERT INTO path(idPath, strPath) VALUES (?, ?)", (path_id, strPath))
        return path_id


    # Favorite for content
    def get_favoriteData(self, KodiId):
        self.cursor.execute("SELECT idPath, strTitle, strFilename, idAlbum FROM song WHERE idSong = ?", (KodiId,))
        ItemData = self.cursor.fetchone()
        Thumbnail = ""

        if ItemData:
            self.cursor.execute("SELECT strPath FROM path WHERE idPath = ?", (ItemData[0],))
            DataPath = self.cursor.fetchone()

            if DataPath:
                self.cursor.execute("SELECT url FROM art WHERE media_id = ? AND media_type = ? AND type = ?", (ItemData[3], "album", "thumb"))
                ArtworkData = self.cursor.fetchone()

                if ArtworkData:
                    Thumbnail = ArtworkData[0]

                return f"{DataPath[0]}{ItemData[2]}", Thumbnail, ItemData[1]

        return "", "", ""

    # Favorite for subcontent
    def get_FavoriteSubcontent(self, KodiId, ContentType):
        Thumbnail = ""

        self.cursor.execute("SELECT url FROM art WHERE media_id = ? AND media_type = ? AND type = ?", (KodiId, ContentType, "thumb"))
        ArtworkData = self.cursor.fetchone()

        if ArtworkData:
            Thumbnail = ArtworkData[0]

        if ContentType == "artist":
            self.cursor.execute("SELECT strArtist FROM artist WHERE idArtist = ?", (KodiId,))
        elif ContentType == "album":
            self.cursor.execute("SELECT strAlbum FROM album WHERE idAlbum = ?", (KodiId,))
        else:
            return "", ""

        ItemData = self.cursor.fetchone()

        if ItemData:
            return Thumbnail, ItemData[0]

        return "", ""

def set_metadata_song(Artist, Title, BitRate, SampleRate, Channels, PlayCount):
    if not PlayCount:
        PlayCount = 0

    if not BitRate:
        BitRate = 0

    if not SampleRate:
        SampleRate = 0

    if not Channels:
        Channels = 0

    return BitRate, SampleRate, Channels, PlayCount

def errorhandler_MusicBrainzID(Title, MusicBrainzID, error):
    error = str(error)

    if "MusicBrainz" in error:  # Duplicate musicbrainz
        MusicBrainzID += " "
        return MusicBrainzID

    xbmc.log(f"EMBY.database.music_db: Unknown error: {Title} / {MusicBrainzID} / {error}", xbmc.LOGERROR)
    return "UNKNOWN ERROR"
