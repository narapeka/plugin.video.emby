import xbmc
from helper import utils
from . import common_db

if utils.DatabaseFiles["video-version"] >= 135:
    VideoversionTypes = {"regular": 1, "special": 2}
else:
    VideoversionTypes = {"regular": 0, "special": 1}

SeasonPlot = utils.DatabaseFiles["video-version"] >= 145


class VideoDatabase:
    _UNCHANGED = object()

    def __init__(self, cursor):
        self.cursor = cursor
        self.common_db = common_db.CommonDatabase(cursor)

    def get_existing_similar_ids(self, KodiType, KodiIds):
        Table, Column = {"movie": ("movie", "idMovie"), "tvshow": ("tvshow", "idShow")}[KodiType]
        if not KodiIds:
            return set()
        self.cursor.execute(f"SELECT {Column} FROM {Table} WHERE {Column} IN ({','.join('?' for _ in KodiIds)})", tuple(KodiIds))
        return {Row[0] for Row in self.cursor.fetchall()}

    def add_Index(self):
        try: # xbox issue
            SchemaVersion = self.cursor.execute("PRAGMA schema_version").fetchone()[0]
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_strFilename on files (strFilename)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_dateAdded on files (dateAdded)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_lastPlayed on files (lastPlayed)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_playCount on files (playCount)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_bookmark_type on bookmark (type)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_bookmark_timeInSeconds on bookmark (timeInSeconds)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_rating_rating on rating (rating)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_episode_c12 on episode (c12)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_episode_idShow_idFile_c12 on episode (idShow, idFile, c12)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_genre_link_genre_id_media_id_media_type ON genre_link(genre_id, media_id, media_type)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_movie_idSet on movie (idSet)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_videoversion_media_type on videoversion (media_type)")
            if self.cursor.execute("PRAGMA schema_version").fetchone()[0] != SchemaVersion:
                self.cursor.execute("ANALYZE")
                self.cursor.connection.commit()
                self.cursor.execute("BEGIN IMMEDIATE TRANSACTION")
        except Exception as Error:
            xbmc.log(f"EMBY.database.video_db: Database add index error: {Error}", xbmc.LOGERROR)

    def delete_Index(self):
        try: # xbox issue
            self.cursor.execute("DROP INDEX IF EXISTS idx_files_strFilename")
            self.cursor.execute("DROP INDEX IF EXISTS idx_files_dateAdded")
            self.cursor.execute("DROP INDEX IF EXISTS idx_files_lastPlayed")
            self.cursor.execute("DROP INDEX IF EXISTS idx_files_playCount")
            self.cursor.execute("DROP INDEX IF EXISTS idx_bookmark_type")
            self.cursor.execute("DROP INDEX IF EXISTS idx_bookmark_timeInSeconds")
            self.cursor.execute("DROP INDEX IF EXISTS idx_rating_rating")
            self.cursor.execute("DROP INDEX IF EXISTS idx_episode_c12")
            self.cursor.execute("DROP INDEX IF EXISTS idx_episode_idShow_idFile_c12")
            self.cursor.execute("DROP INDEX IF EXISTS idx_genre_link_genre_id_media_id_media_type")
            self.cursor.execute("DROP INDEX IF EXISTS idx_movie_idSet")
            self.cursor.execute("DROP INDEX IF EXISTS idx_videoversion_media_type")
            self.cursor.execute("ANALYZE")
            self.cursor.connection.commit()
            self.cursor.execute("BEGIN IMMEDIATE TRANSACTION")
        except Exception as Error:
            xbmc.log(f"EMBY.database.video_db: Database delete index error: {Error}", xbmc.LOGERROR)

    # playcount
    def get_playcount(self, KodiItemId, ContentType):
        if ContentType == "movie":
            self.cursor.execute("SELECT idFile FROM movie WHERE idMovie = ?", (KodiItemId,))
        elif ContentType == "musicvideo":
            self.cursor.execute("SELECT idFile FROM musicvideo WHERE idMVideo = ?", (KodiItemId,))
        elif ContentType == "episode":
            self.cursor.execute("SELECT idFile FROM episode WHERE idEpisode = ?", (KodiItemId,))
        else:
            return 0

        KodiFileId = self.cursor.fetchone()

        if KodiFileId:
            self.cursor.execute("SELECT playCount FROM files WHERE idFile = ?", (KodiFileId[0],))
            KodiPlayCount = self.cursor.fetchone()

            if KodiPlayCount and KodiPlayCount[0]:
                return KodiPlayCount[0]

        return 0

    # Favorite for content
    def get_favoriteData(self, KodiFileId, KodiItemId, ContentType):
        Image = ""

        if ContentType == "set":
            self.cursor.execute("SELECT strSet FROM sets WHERE idSet = ?", (KodiItemId,))
            DataSet = self.cursor.fetchone()

            if DataSet:
                for ImageId in ("poster", "thumb"):
                    self.cursor.execute("SELECT url FROM art WHERE media_id = ? AND media_type = ? AND type = ?", (KodiItemId, "set", ImageId))
                    ArtworkData = self.cursor.fetchone()

                    if ArtworkData:
                        Image = ArtworkData[0]
                        break

                return "", Image, DataSet[0]

            return "", "", ""

        if ContentType == "movie":
            self.cursor.execute("SELECT idMedia FROM videoversion WHERE idFile = ? AND media_type = ?", (KodiFileId, "movie"))
            DataVideoversion = self.cursor.fetchone()

            if DataVideoversion:
                self.cursor.execute("SELECT idFile FROM movie WHERE idMovie = ?", (DataVideoversion[0],))
                DataMovie = self.cursor.fetchone()

                if DataMovie:
                    KodiFileId = DataMovie[0]
                else:
                    return "", "", ""
        elif ContentType not in ("episode", "musicvideo"):
            return "", "", ""

        self.cursor.execute("SELECT idPath, strFilename FROM files WHERE idFile = ?", (KodiFileId,))
        DataFile = self.cursor.fetchone()

        if DataFile:
            self.cursor.execute("SELECT strPath FROM path WHERE idPath = ?", (DataFile[0],))
            DataPath = self.cursor.fetchone()

            if DataPath:
                if ContentType == "movie":
                    self.cursor.execute("SELECT c00, idMovie FROM movie WHERE idFile = ?", (KodiFileId,))
                elif ContentType == "musicvideo":
                    self.cursor.execute("SELECT c00, idMVideo FROM musicvideo WHERE idFile = ?", (KodiFileId,))
                elif ContentType == "episode":
                    self.cursor.execute("SELECT c00, idEpisode FROM episode WHERE idFile = ?", (KodiFileId,))
                else:
                    return "", "", ""

                ItemData = self.cursor.fetchone()

                if ItemData:
                    for ImageId in ("poster", "thumb"):
                        self.cursor.execute("SELECT url FROM art WHERE media_id = ? AND media_type = ? AND type = ?", (ItemData[1], ContentType, ImageId))
                        ArtworkData = self.cursor.fetchone()

                        if ArtworkData:
                            Image = ArtworkData[0]
                            break

                    if DataPath[0].endswith('|redirect-limit=1000&failonerror=false'):
                        return f"{DataPath[0].replace('|redirect-limit=1000&failonerror=false', '')}{DataFile[1]}|redirect-limit=1000&failonerror=false", Image, ItemData[0]

                    return f"{DataPath[0]}{DataFile[1]}", Image, ItemData[0]

        return "", "", ""

    # Favorite for subcontent
    def get_FavoriteSubcontent(self, KodiItemId, ContentType):
        Image = ""

        if ContentType == "tvshow":
            self.cursor.execute("SELECT c00 FROM tvshow WHERE idShow = ?", (KodiItemId,))
        else:
            self.cursor.execute("SELECT name, season, idShow FROM seasons WHERE idSeason = ?", (KodiItemId,))

        ItemData = self.cursor.fetchone()

        if ItemData:
            Name = ItemData[0]

            if ContentType == "season":
                self.cursor.execute("SELECT c00 FROM tvshow WHERE idShow = ?", (ItemData[2],))
                TVShowData = self.cursor.fetchone()

                if TVShowData:
                    Name = f"{TVShowData[0]} - {Name}"

            for ImageId in ("poster", "thumb"):
                self.cursor.execute("SELECT url FROM art WHERE media_id = ? AND media_type = ? AND type = ?", (KodiItemId, ContentType, ImageId))
                ArtworkData = self.cursor.fetchone()

                if ArtworkData:
                    Image = ArtworkData[0]
                    break

            if ContentType == "tvshow":
                return Image, Name, -1

            return Image, Name, ItemData[1]

        return "", "", -1

    # movies
    def get_setId(self, KodiId):
        self.cursor.execute("SELECT idSet FROM movie WHERE idMovie = ?", (KodiId,))
        SetInfo = self.cursor.fetchone()

        if SetInfo:
            return SetInfo[0]

        return 0


    def add_movie(self, KodiItemId, KodiFileId, Name, Overview, ShortOverview, Tagline, RatingId, Writers, Poster, Unique, SortName, RunTimeTicks, OfficialRating, Genre, Directors, OriginalTitle, Studio, Trailer, KodiFanart, ProductionLocation, KodiFullPath, KodiPathId, PremiereDate, Filename, DateCreated, idSet, KodiStackedFilename, VersionName):
        self.cursor.execute("INSERT INTO movie (idMovie, idFile, c00, c01, c02, c03, c05, c06, c08, c09, c10, c11, c12, c14, c15, c16, c18, c19, c20, c21, c22, c23, premiered, idSet) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (KodiItemId, KodiFileId, Name, Overview, ShortOverview, Tagline, RatingId, Writers, Poster, Unique, SortName, RunTimeTicks, OfficialRating, Genre, Directors, OriginalTitle, Studio, Trailer, KodiFanart, ProductionLocation, KodiFullPath, KodiPathId, PremiereDate, idSet))
        self.add_file(KodiPathId, Filename, DateCreated, KodiFileId, KodiStackedFilename)
        VideoVersionTypeId = self.get_add_videoversiontype(VersionName, "regular")
        self.cursor.execute("INSERT OR IGNORE INTO videoversion(idFile, idMedia, media_type, itemType, idType) VALUES (?, ?, ?, ?, ?)", (KodiFileId, KodiItemId, "movie", VideoversionTypes["regular"], VideoVersionTypeId))

    def add_movie_version(self, KodiItemId, KodiFileId, KodiPathId, Filename, DateCreated, KodiStackedFilename, VersionName, KodiType, ContentType):
        self.add_file(KodiPathId, Filename, DateCreated, KodiFileId, KodiStackedFilename)
        VideoVersionTypeId = self.get_add_videoversiontype(VersionName, ContentType)
        self.cursor.execute("INSERT OR IGNORE INTO videoversion(idFile, idMedia, media_type, itemType, idType) VALUES (?, ?, ?, ?, ?)", (KodiFileId, KodiItemId, KodiType, VideoversionTypes[ContentType], VideoVersionTypeId))

    def update_movie(self, KodiItemId, KodiFileId, Name, Overview, ShortOverview, Tagline, RatingId, Writers, Poster, Unique, SortName, RunTimeTicks, OfficialRating, Genre, Directors, OriginalTitle, Studio, Trailer, KodiFanart, ProductionLocation, PremiereDate, idSet, Filename, KodiStackedFilename, DateCreated, VersionName, KodiPathId, Path, KodiFullPath, PreserveVersions=False):
        self.cursor.execute("UPDATE movie SET c00 = ?, c01 = ?, c02 = ?, c03 = ?, c05 = ?, c06 = ?, c08 = ?, c09 = ?, c10 = ?, c11 = ?, c12 = ?, c14 = ?, c15 = ?, c16 = ?, c18 = ?, c19 = ?, c20 = ?, c21 = ?, c22 = CASE WHEN ? THEN c22 ELSE ? END, c23 = CASE WHEN ? THEN c23 ELSE ? END, premiered = ?, idSet = CASE WHEN ? THEN idSet ELSE ? END WHERE idMovie = ?", (Name, Overview, ShortOverview, Tagline, RatingId, Writers, Poster, Unique, SortName, RunTimeTicks, OfficialRating, Genre, Directors, OriginalTitle, Studio, Trailer, KodiFanart, ProductionLocation, PreserveVersions, KodiFullPath, PreserveVersions, KodiPathId, PremiereDate, PreserveVersions, idSet, KodiItemId))
        self.update_file(KodiFileId, DateCreated, Filename, KodiStackedFilename)
        self.cursor.execute("DELETE FROM movielinktvshow WHERE idMovie = ?", (KodiItemId,))
        self.cursor.execute("UPDATE path SET strPath = ? WHERE idPath = ?", (Path, KodiPathId))

        # update videoversions
        VideoVersionTypeId = self.get_add_videoversiontype(VersionName, "regular")
        self.cursor.execute("UPDATE videoversion SET idType = ? WHERE idFile = ? AND idMedia = ? AND media_type = ? AND itemType = ?", (VideoVersionTypeId, KodiFileId, KodiItemId, "movie", VideoversionTypes["regular"]))

    def get_movieversion_fileids(self, KodiItemId):
        self.cursor.execute("SELECT idFile FROM videoversion WHERE idMedia = ? AND media_type = ? AND itemType = ?", (KodiItemId, "movie", VideoversionTypes["regular"]))
        return {Data[0] for Data in self.cursor.fetchall()}

    def get_alternate_movie_path(self, KodiItemId, KodiFileId):
        self.cursor.execute("""SELECT path.strPath, files.strFilename FROM videoversion
            JOIN movie ON movie.idMovie = videoversion.idMedia
            JOIN files ON files.idFile = videoversion.idFile
            JOIN path ON path.idPath = files.idPath
            WHERE movie.idMovie = ? AND files.idFile = ? AND movie.idFile <> files.idFile
                AND videoversion.media_type = 'movie' AND videoversion.itemType = ?""",
                            (KodiItemId, KodiFileId, VideoversionTypes["regular"]))
        Row = self.cursor.fetchone()
        if not Row:
            return ""
        Path, Filename = Row
        if Filename.startswith(("stack://", "plugin://")):
            return Filename
        Folder, Separator, Options = Path.partition("|")
        return Folder + Filename + Separator + Options

    def update_movie_version(self, KodiItemId, KodiFileId, KodiPathId, Path, Filename, DateCreated, KodiStackedFilename, VersionName):
        self.update_file(KodiFileId, DateCreated, Filename, KodiStackedFilename)
        self.cursor.execute("UPDATE path SET strPath = ? WHERE idPath = ?", (Path, KodiPathId))
        VideoVersionTypeId = self.get_add_videoversiontype(VersionName, "regular")
        self.cursor.execute("UPDATE videoversion SET idType = ? WHERE idFile = ? AND idMedia = ? AND media_type = ? AND itemType = ?", (VideoVersionTypeId, KodiFileId, KodiItemId, "movie", VideoversionTypes["regular"]))

    def update_default_movieversion(self, KodiItemId, KodiFileId, KodiPathId, Path):
        self.cursor.execute("UPDATE movie SET idFile = ?, c23 = ?, c22 = ? WHERE idMovie = ?", (KodiFileId, KodiPathId, Path, KodiItemId))


    def create_movie_entry(self):
        self.cursor.execute("SELECT coalesce(max(idMovie), 0) FROM movie")
        return self.cursor.fetchone()[0] + 1

    def delete_movie(self, KodiItemId, KodiFileId):
        self.cursor.execute("DELETE FROM movie WHERE idMovie = ?", (KodiItemId,))
        self.cursor.execute("DELETE FROM files WHERE idFile = ?", (KodiFileId,))
        self.cursor.execute("DELETE FROM movielinktvshow WHERE idMovie = ?", (KodiItemId,))
        self.cursor.execute("SELECT idFile FROM videoversion WHERE idMedia = ? AND media_type = ?", (KodiItemId, "movie"))
        FileIds = self.cursor.fetchall()

        if FileIds:
            self.cursor.executemany("DELETE FROM files WHERE idFile = ?", FileIds)
            self.cursor.execute("DELETE FROM videoversion WHERE idMedia = ? AND media_type = ?", (KodiItemId, "movie"))


    def get_movie_metadata_for_listitem(self, KodiItemId, PathAndFilename):
        self.cursor.execute("SELECT c00, c01, c02, c03, c06, c10, c11, c12, c14, c15, c16, c18, c19, c21, premiered, userrating, strPath, playCount, lastPlayed, dateAdded, rating, totalTimeInSeconds, resumeTimeInSeconds, votes, rating_type, uniqueid_value, uniqueid_type, strFileName, strSet, strSetOverview, idSet, videoVersionTypeName FROM movie_view WHERE idMovie = ? AND isDefaultVersion = 1", (KodiItemId,))
        MovieData = self.cursor.fetchone()

        if not MovieData:
            return {}

        if not PathAndFilename:
            if MovieData[16].endswith('|redirect-limit=1000&failonerror=false'):
                PathAndFilename = f"{MovieData[16].replace('|redirect-limit=1000&failonerror=false', '')}{MovieData[27]}|redirect-limit=1000&failonerror=false"
            else:
                PathAndFilename = f"{MovieData[16]}{MovieData[27]}"

        Artwork = self.common_db.get_artwork(KodiItemId, "movie", "")
        Artwork.update(self.common_db.get_artwork(MovieData[30], "set", "set."))
        People = self.get_people_artwork(KodiItemId, "movie")

        # get ratings
        self.cursor.execute("SELECT rating_type, rating, votes FROM rating WHERE media_id = ? AND media_type = ?", (KodiItemId, "movie"))
        Ratings = self.cursor.fetchall()

        # get showlinks
        self.cursor.execute("SELECT idShow FROM movielinktvshow WHERE idMovie = ?", (KodiItemId,))
        ShowIds = self.cursor.fetchall()
        ShowLinks = ()

        if ShowIds:
            ShowIdList = []

            for Row in ShowIds:
                ShowIdList.append(Row[0])

            Query = "SELECT c00 FROM tvshow WHERE idShow IN (" + ",".join("?" * len(ShowIdList)) + ")"
            self.cursor.execute(Query, tuple(ShowIdList))
            ShowData = self.cursor.fetchall()

            for Row in ShowData:
                ShowLinks += (Row[0],)

        # Get tags
        Tags = self.get_Tags(KodiItemId, "movie")

        # UniqueIds
        UniqueIds = self.get_UniqueIds(KodiItemId, "movie")
        return {'KodiMetadataMediatype': "movie", "KodiMetadataDBID": KodiItemId, 'KodiMetadataTitle': MovieData[0], 'KodiMetadataOverview': MovieData[1], 'KodiMetadataShortOverview': MovieData[2], 'KodiMetadataTagline': MovieData[3], 'KodiMetadataWriter': MovieData[4], 'KodiMetadataSortName': MovieData[5], 'KodiMetadataDuration': MovieData[6], 'KodiMetadataMPAA': MovieData[7], 'KodiMetadataGenre': MovieData[8], 'KodiMetadataDirector': MovieData[9], 'OriginalTitle': MovieData[10], 'KodiMetadataStudioName': MovieData[11], 'KodiMetadataProductionLocation': MovieData[13], 'KodiMetadataUserRating': MovieData[15], 'KodiMetadataPremiereDate': MovieData[14], 'KodiMetadataPlaycount': MovieData[17], 'KodiMetadataLastplayed': MovieData[18], 'KodiMetadataDateCreated': MovieData[19], 'KodiMetadataCommunityRating': MovieData[20], 'KodiMetadataTrailer': MovieData[12], 'KodiMetadataPath': MovieData[16], 'KodiMetadataPathandfilename': PathAndFilename, 'KodiMetadataProperties': {'IsFolder': 'false', 'IsPlayable': 'true'}, 'KodiMetadataPeople': People, 'KodiMetadataArtwork': Artwork, 'KodiMetadataRunTimeTicks': MovieData[21], 'KodiMetadataPlaybackPositionTicks': MovieData[22], 'KodiMetadataVotes': MovieData[23], 'KodiMetadataRatingType': MovieData[24], 'KodiMetadataUniqueIdValue': MovieData[25], 'KodiMetadataUniqueIdType': MovieData[26], 'KodiMetadataRatings': Ratings, 'KodiMetadataSet': MovieData[28], 'KodiMetadataSetOverview': MovieData[29], 'KodiMetadataSetId': MovieData[30], 'KodiMetadataVideoAssetTitle': MovieData[31], 'KodiMetadataShowLinks': ShowLinks, 'KodiMetadataTags': Tags, 'KodiMetadataUniqueIds': UniqueIds}

    # musicvideo


    def add_musicvideos(self, KodiItemId, KodiFileId, Name, Poster, RunTimeTicks, Directors, Studio, Overview, Album, Artist, Genre, IndexNumber, KodiFullPath, KodiPathId, PremiereDate, DateCreated, Filename, KodiStackedFilename, isPlaylist):
        # c15 (not used by Kodi) contains if it's a playlist
        if isPlaylist:
            C15 = "playlist"
        else:
            C15 = None

        self.cursor.execute("INSERT INTO musicvideo (idMVideo, idFile, c00, c01, c04, c05, c06, c08, c09, c10, c11, c12, c13, c14, premiered, c15) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (KodiItemId, KodiFileId, Name, Poster, RunTimeTicks, Directors, Studio, Overview, Album, Artist, Genre, IndexNumber, KodiFullPath, KodiPathId, PremiereDate, C15))
        self.add_file(KodiPathId, Filename, DateCreated, KodiFileId, KodiStackedFilename)

    def update_musicvideos(self, KodiItemId, KodiFileId, Name, Poster, RunTimeTicks, Directors, Studio, Overview, Album, Artist, Genre, IndexNumber, PremiereDate, Filename, KodiStackedFilename, DateCreated, KodiPathId, Path, isPlaylist, KodiFullPath):
        self.cursor.execute("SELECT c15 FROM musicvideo_view WHERE idMVideo = ?", (KodiItemId,))
        Temp = self.cursor.fetchone()
        isPlaylistItem = Temp[0] == "playlist"

        # c15 (not used by Kodi) contains if it's a playlist
        if isPlaylist and not isPlaylistItem or not isPlaylist and isPlaylistItem: # Skip tracknumber updates
            self.cursor.execute("UPDATE musicvideo SET c00 = ?, c01 = ?, c04 = ?, c05 = ?, c06 = ?, c08 = ?, c09 = ?, c10 = ?, c11 = ?, c13 = ?, c14 = ?, premiered = ? WHERE idMVideo = ?", (Name, Poster, RunTimeTicks, Directors, Studio, Overview, Album, Artist, Genre, KodiFullPath, KodiPathId, PremiereDate, KodiItemId))
        else:
            self.cursor.execute("UPDATE musicvideo SET c00 = ?, c01 = ?, c04 = ?, c05 = ?, c06 = ?, c08 = ?, c09 = ?, c10 = ?, c11 = ?, c12 = ?, c13 = ?, c14 = ?, premiered = ? WHERE idMVideo = ?", (Name, Poster, RunTimeTicks, Directors, Studio, Overview, Album, Artist, Genre, IndexNumber, KodiFullPath, KodiPathId, PremiereDate, KodiItemId))

        self.update_file(KodiFileId, DateCreated, Filename, KodiStackedFilename)
        self.cursor.execute("UPDATE path SET strPath = ? WHERE idPath = ?", (Path, KodiPathId))

    def create_entry_musicvideos(self):
        self.cursor.execute("SELECT coalesce(max(idMVideo), 0) FROM musicvideo")
        return self.cursor.fetchone()[0] + 1

    def delete_musicvideos(self, KodiItemId, KodiFileId):
        self.cursor.execute("DELETE FROM bookmark WHERE idFile = ?", (KodiFileId,))
        self.cursor.execute("DELETE FROM files WHERE idFile = ?", (KodiFileId,))
        self.cursor.execute("DELETE FROM musicvideo WHERE idMVideo = ?", (KodiItemId,))

    def get_musicvideos_metadata_for_listitem(self, KodiItemId, PathAndFilename):
        self.cursor.execute("SELECT c00, c04, c05, c06, c08, c09, c11, c12, premiered, playCount, lastPlayed, strPath, strFileName, totalTimeInSeconds, resumeTimeInSeconds, dateAdded FROM musicvideo_view WHERE idMVideo = ?", (KodiItemId,))
        MusicVideoData = self.cursor.fetchone()

        if not MusicVideoData:
            return {}

        if not PathAndFilename:
            if MusicVideoData[11].endswith('|redirect-limit=1000&failonerror=false'):
                PathAndFilename = f"{MusicVideoData[11].replace('|redirect-limit=1000&failonerror=false', '')}{MusicVideoData[12]}|redirect-limit=1000&failonerror=false"
            else:
                PathAndFilename = f"{MusicVideoData[11]}{MusicVideoData[12]}"

        Artwork = self.common_db.get_artwork(KodiItemId, "musicvideo", "")
        People = self.get_people_artwork(KodiItemId, "musicvideo")
        Tags = self.get_Tags(KodiItemId, "musicvideo")
        return {'KodiMetadataMediatype': "musicvideo", "KodiMetadataDBID": KodiItemId, 'KodiMetadataTitle': MusicVideoData[0], 'KodiMetadataDuration': MusicVideoData[1], 'KodiMetadataDirector': MusicVideoData[2], 'KodiMetadataStudioName': MusicVideoData[3], 'KodiMetadataOverview': MusicVideoData[4], 'KodiMetadataAlbum': MusicVideoData[5], 'KodiMetadataGenre': MusicVideoData[6], 'KodiMetadataTrack': MusicVideoData[7], 'KodiMetadataPremiereDate': MusicVideoData[8], 'KodiMetadataPlaycount': MusicVideoData[9], 'KodiMetadataLastplayed': MusicVideoData[10], 'KodiMetadataPath': MusicVideoData[11], 'KodiMetadataPathandfilename': PathAndFilename, 'KodiMetadataProperties': {'IsFolder': 'false', 'IsPlayable': 'true'}, 'KodiMetadataPeople': People, 'KodiMetadataArtwork': Artwork, 'KodiMetadataRunTimeTicks': MusicVideoData[13], 'KodiMetadataPlaybackPositionTicks': MusicVideoData[14], 'KodiMetadataDateCreated': MusicVideoData[15], 'KodiMetadataTags': Tags}

    def get_musicvideos_recentlyadded_albums(self, Tag):
        self.cursor.execute('select actor_link.actor_id, musicvideo.c09, musicvideo.c10, musicvideo.idMVideo from musicvideo JOIN files ON files.idFile=musicvideo.idFile JOIN actor_link ON actor_link.media_id=musicvideo.idMVideo AND actor_link.media_type="musicvideo" JOIN tag_link ON tag_link.media_id=musicvideo.idMVideo AND tag_link.media_type="musicvideo" JOIN tag ON tag.tag_id=tag_link.tag_id AND tag.name=? GROUP BY musicvideo.c10,musicvideo.c09 ORDER BY files.dateadded DESC LIMIT ?', (Tag, utils.maxnodeitems))
        return self.cursor.fetchall()


    # tvshow

    def update_tvshow(self, TVShowName, c01, c02, c04, c05, c06, c08, c09, c11, c12, c13, c14, TVShowSortName, duration, KodiShowId, Trailer, KodiPathId, Path):
        self.cursor.execute("UPDATE tvshow SET c00 = ?, c01 = ?, c02 = ?, c04 = ?, c05 = ?, c06 = ?, c08 = ?, c09 = ?, c11 = ?, c12 = ?, c13 = ?, c14 = ?, c15 = ?, duration = ?, c16 = ? WHERE idShow = ?", (TVShowName, c01, c02, c04, c05, c06, c08, c09, c11, c12, c13, c14, TVShowSortName, duration, Trailer, KodiShowId))
        self.cursor.execute("UPDATE path SET strPath = ? WHERE idPath = ?", (Path, KodiPathId))

    def add_tvshow(self, KodiShowId, c00, c01, c02, c04, c05, c06, c08, c09, c11, c12, c13, c14, c15, duration, Trailer):
        self.cursor.execute("INSERT INTO tvshow(idShow, c00, c01, c02, c04, c05, c06, c08, c09, c11, c12, c13, c14, c15, duration, c16) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (KodiShowId, c00, c01, c02, c04, c05, c06, c08, c09, c11, c12, c13, c14, c15, duration, Trailer))

    def create_entry_tvshow(self):
        self.cursor.execute("SELECT coalesce(max(idShow), 0) FROM tvshow")
        return self.cursor.fetchone()[0] + 1

    def delete_tvshow(self, KodiShowId, KodiPathId):
        SubcontentKodiIds = ()
        self.common_db.delete_artwork(KodiShowId, "tvshow")
        self.delete_links_tags(KodiShowId, "tvshow", None, True)
        self.cursor.execute("SELECT idSeason FROM seasons WHERE idShow = ?", (KodiShowId,))
        SeasonsData = self.cursor.fetchall()

        for SeasonData in SeasonsData:
            SubcontentKodiIds += ((SeasonData[0], "Season"),)
            SubcontentKodiIds += self.delete_season(SeasonData[0])

        self.cursor.execute("DELETE FROM tvshowlinkpath WHERE idShow = ?", (KodiShowId,))
        self.cursor.execute("DELETE FROM movielinktvshow WHERE idShow = ?", (KodiShowId,))
        self.cursor.execute("DELETE FROM uniqueid WHERE media_id = ? AND media_type = ?", (KodiShowId, "tvshow"))
        self.cursor.execute("DELETE FROM rating WHERE media_id = ? AND media_type = ?", (KodiShowId, "tvshow"))
        self.cursor.execute("DELETE FROM tvshow WHERE idShow = ?", (KodiShowId,))
        self.cursor.execute("DELETE FROM path WHERE idPath = ?", (KodiPathId,))
        return SubcontentKodiIds

    def add_link_tvshow(self, KodiShowId, idPath):
        self.cursor.execute("INSERT OR REPLACE INTO tvshowlinkpath(idShow, idPath) VALUES (?, ?)", (KodiShowId, idPath))


    def get_inprogress_mixedIds(self):
        self.cursor.execute("SELECT idFile FROM bookmark WHERE type = ?", (1,))
        KodiFileIds = self.cursor.fetchall()
        InProgressInfos = ()

        for KodiFileId in KodiFileIds:
            self.cursor.execute("SELECT lastPlayed, idMovie FROM movie_view WHERE idFile = ?", (KodiFileId[0],))
            MovieData = self.cursor.fetchone()

            if MovieData:
                if not MovieData[0]:
                    InProgressInfos += (f"0000;{MovieData[1]};Movie",)
                else:
                    InProgressInfos += (f"{MovieData[0]};{MovieData[1]};Movie",)
            else:
                self.cursor.execute("SELECT lastPlayed, idEpisode FROM episode_view WHERE idFile = ?", (KodiFileId[0],))
                EpisodeData = self.cursor.fetchone()

                if EpisodeData:
                    if not EpisodeData[0]:
                        InProgressInfos += (f"0000;{EpisodeData[1]};Episode",)
                    else:
                        InProgressInfos += (f"{EpisodeData[0]};{EpisodeData[1]};Episode",)
                else:
                    self.cursor.execute("SELECT lastPlayed, idMVideo FROM musicvideo_view WHERE idFile = ?", (KodiFileId[0],))
                    MusicVideoData = self.cursor.fetchone()

                    if MusicVideoData:
                        if not MusicVideoData[0]:
                            InProgressInfos += (f"0000;{MusicVideoData[1]};MusicVideo",)
                        else:
                            InProgressInfos += (f"{MusicVideoData[0]};{MusicVideoData[1]};MusicVideo",)

        InProgressInfos = sorted(InProgressInfos, reverse=True)
        return InProgressInfos

    def get_next_episodesIds(self, TagName):
        if TagName != "unknown":
            self.cursor.execute("SELECT tag_id FROM tag WHERE name = ?", (TagName,))
            TagId = self.cursor.fetchone()

            if TagId:
                TagId = TagId[0]
            else:
                return ()

            self.cursor.execute("SELECT DISTINCT media_id FROM tag_link WHERE tag_id = ? AND media_type = ?", (TagId, "tvshow"))
        else:
            self.cursor.execute("SELECT DISTINCT media_id FROM tag_link WHERE media_type = ?", ("tvshow",))

        KodiShowIds = self.cursor.fetchall()
        NextEpisodeInfos = ()

        for KodiShowId in KodiShowIds:
            self.cursor.execute("SELECT idEpisode, idFile, c12, playCount, lastPlayed FROM episode_view WHERE idShow = ? ORDER BY CAST(c12 AS INT) ASC, CAST(c13 AS INT) ASC", (KodiShowId[0],))
            Episodes = self.cursor.fetchall()
            LastPlayedDate = "0000"
            PlayedFound = False
            NextEpisodeId = "-1"

            for Episode in Episodes:
                if Episode[4] and Episode[4] > LastPlayedDate: # find highest PlayedDate
                    LastPlayedDate = str(Episode[4])

                if Episode[2] == "0": # Skip special seasons
                    continue

                if Episode[3]: # Playcount
                    PlayedFound = True
                else:
                    if PlayedFound: # get episode Id from the next (not played) episode
                        NextEpisodeId = Episode[0]
                        PlayedFound = False

            if NextEpisodeId != "-1":
                NextEpisodeInfos += (f"{LastPlayedDate};{NextEpisodeId};Episode",)

        NextEpisodeInfos = sorted(NextEpisodeInfos, reverse=True) # reverse sort by date
        return NextEpisodeInfos

    def get_last_played_next_episodesIds(self, TagName):
        if TagName != "unknown":
            self.cursor.execute("SELECT tag_id FROM tag WHERE name = ?", (TagName,))
            TagId = self.cursor.fetchone()

            if TagId:
                TagId = TagId[0]
            else:
                return ()

            self.cursor.execute("SELECT DISTINCT media_id FROM tag_link WHERE tag_id = ? AND media_type = ?", (TagId, "tvshow"))
        else:
            self.cursor.execute("SELECT DISTINCT media_id FROM tag_link WHERE media_type = ?", ("tvshow",))

        KodiShowIds = self.cursor.fetchall()
        NextEpisodeInfos = ()

        for KodiShowId in KodiShowIds:
            self.cursor.execute("SELECT idEpisode, c12, c13, lastPlayed, resumeTimeInSeconds, c15, c16 FROM episode_view WHERE idShow = ? AND lastPlayed IS NOT NULL and COALESCE(c15,c12) is not '0' AND (playCount > 0 or resumeTimeInSeconds IS NOT NULL) ORDER BY lastPlayed DESC, CAST(COALESCE(c15,c12) AS INT) DESC, CAST(COALESCE(c16,c13) AS INT) DESC, CAST(c12 as INT) ASC, idEpisode ASC LIMIT 1", (KodiShowId[0],))
            Episode = self.cursor.fetchone()

            if Episode:
                LastPlayedDate = str(Episode[3])

                if Episode[4]:
                    NextEpisodeId = Episode[0]
                    NextEpisodeInfos += (f"{LastPlayedDate};{NextEpisodeId};Episode",)
                else:
                    if Episode[5]: # It was a special inserted into the season
                        # Search for more specials at the same point
                        self.cursor.execute("SELECT idEpisode FROM episode_view WHERE idShow = ? AND CAST(c15 AS INT) = ? AND CAST(c16 AS INT) = ? and idEpisode > ? ORDER BY idEpisode ASC LIMIT 1", (KodiShowId[0], Episode[5], Episode[6], Episode[0]))
                        nextEpisode = self.cursor.fetchone()

                        if not nextEpisode:
                            # No more specials, get the regular episode
                            self.cursor.execute("SELECT idEpisode FROM episode_view WHERE idShow = ? AND ((CAST(c12 AS INT) = ? AND CAST(c13 AS INT) >= ?) OR (CAST(c12 AS INT) > ?)) ORDER BY CAST(c12 AS INT) ASC, CAST(c13 AS INT) ASC LIMIT 1", (KodiShowId[0], Episode[5], Episode[6], Episode[5]))
                            nextEpisode = self.cursor.fetchone()
                    else: # It was a regular episode, get the next special or regular episode after it
                        self.cursor.execute("SELECT idEpisode FROM episode_view WHERE idShow = ? AND ((CAST(COALESCE(c15,c12) AS INT) = ? AND CAST(COALESCE(c16,c13) AS INT) > ?) OR (CAST(COALESCE(c15,c12) AS INT) > ?)) ORDER BY CAST(COALESCE(c15,c12) AS INT) ASC, CAST(COALESCE(c16,c13) AS INT) ASC, CAST(c12 as INT) ASC, idEpisode ASC LIMIT 1", (KodiShowId[0], Episode[1], Episode[2], Episode[1]))
                        nextEpisode = self.cursor.fetchone()

                    if nextEpisode:
                        NextEpisodeId = nextEpisode[0]
                        NextEpisodeInfos += (f"{LastPlayedDate};{NextEpisodeId};Episode",)

        NextEpisodeInfos = sorted(NextEpisodeInfos, reverse=True) # reverse sort by date
        return NextEpisodeInfos


    # seasons


    def add_season(self, KodiSeasonId, KodiShowId, SeasonNumber, SeasonName, Overview):
        if SeasonPlot:
            self.cursor.execute("INSERT OR REPLACE INTO seasons(idSeason, idShow, season, name, plot) VALUES (?, ?, ?, ?, ?)", (KodiSeasonId, KodiShowId, SeasonNumber, SeasonName, Overview)) # IGNORE required for stacked content
        else:
            self.cursor.execute("INSERT OR REPLACE INTO seasons(idSeason, idShow, season, name) VALUES (?, ?, ?, ?)", (KodiSeasonId, KodiShowId, SeasonNumber, SeasonName)) # IGNORE required for stacked content

    def update_season(self, KodiShowId, SeasonNumber, SeasonName, KodiSeasonId, Overview):
        if SeasonPlot:
            self.cursor.execute("UPDATE seasons SET idShow = ?, season = ?, name = ?, plot = ? WHERE idSeason = ?", (KodiShowId, SeasonNumber, SeasonName, Overview, KodiSeasonId))
        else:
            self.cursor.execute("UPDATE seasons SET idShow = ?, season = ?, name = ? WHERE idSeason = ?", (KodiShowId, SeasonNumber, SeasonName, KodiSeasonId))

    def create_entry_season(self):
        self.cursor.execute("SELECT coalesce(max(idSeason), 0) FROM seasons")
        return self.cursor.fetchone()[0] + 1

    def delete_season(self, KodiSeasonId):
        # Delete Season and subcontent
        SubcontentKodiIds = ()
        SQLData = ()
        SQLData1 = ()
        self.common_db.delete_artwork(KodiSeasonId, "season")
        self.cursor.execute("SELECT idEpisode, idFile FROM episode WHERE idSeason = ?", (KodiSeasonId,))
        EpisodesData = self.cursor.fetchall()

        for EpisodeData in EpisodesData:
            SubcontentKodiIds += ((EpisodeData[0], "Episode"),)
            self.delete_episode(EpisodeData[0], EpisodeData[1])
            SQLData += ((EpisodeData[0],),)
            SQLData1 += ((EpisodeData[1],),)

        if SQLData:
            self.cursor.executemany("DELETE FROM episode WHERE idEpisode = ?", SQLData)

        if SQLData1:
            self.cursor.executemany("DELETE FROM files WHERE idFile = ?", SQLData1)

        del SQLData
        del SQLData1
        self.cursor.execute("DELETE FROM seasons WHERE idSeason = ?", (KodiSeasonId,))
        return SubcontentKodiIds

    def get_season_metadata_for_listitem(self, KodiSeasonId):
        self.cursor.execute("SELECT season, name, userrating, showTitle, plot, premiered, genre, studio, mpaa, aired, idShow, episodes, playCount FROM season_view WHERE idSeason = ?", (KodiSeasonId,))
        SeasonData = self.cursor.fetchone()

        if not SeasonData:
            return {}

        if SeasonData[11]:
            if SeasonData[12]:
                UnWatchedEpisodes = int(SeasonData[11]) - int(SeasonData[12])
            else:
                UnWatchedEpisodes = int(SeasonData[11])
        else:
            UnWatchedEpisodes = 0

        Artwork = self.common_db.get_artwork(KodiSeasonId, "season", "")
        Artwork.update(self.common_db.get_artwork(SeasonData[10], "tvshow", "tvshow."))
        People = self.get_people_artwork(KodiSeasonId, "season")
        return {'KodiMetadataMediatype': "season", "KodiMetadataDBID": KodiSeasonId, 'KodiMetadataParentIndexNumber': SeasonData[0], 'KodiMetadataTitle': SeasonData[1], 'KodiMetadataUserRating': SeasonData[2], 'KodiMetadataSeriesName': SeasonData[3], 'KodiMetadataOverview': SeasonData[4], 'KodiMetadataPremiereDate': SeasonData[5], 'KodiMetadataGenre': SeasonData[6], 'KodiMetadataStudioName': SeasonData[7], 'KodiMetadataMPAA': SeasonData[8], 'KodiMetadataFirstaired': SeasonData[9], 'KodiMetadataPath': f"videodb://tvshows/titles/{SeasonData[10]}/{SeasonData[0]}/", 'KodiMetadataProperties': {'TVShowDBID': SeasonData[10], 'NumEpisodes': SeasonData[11], 'WatchedEpisodes': SeasonData[12], 'UnWatchedEpisodes': UnWatchedEpisodes, 'IsFolder': 'true', 'IsPlayable': 'true'}, 'KodiMetadataPeople': People, 'KodiMetadataArtwork': Artwork}


    def get_episode_parent_ids(self, KodiEpisodeId):
        self.cursor.execute("SELECT idShow, idSeason FROM episode WHERE idEpisode = ?", (KodiEpisodeId,))
        return self.cursor.fetchone()

    def get_seasonid_by_showid_number(self, KodiTVShowId, KodiSeasonNumber):
        self.cursor.execute("SELECT idSeason FROM seasons WHERE idShow = ? AND season = ?", (KodiTVShowId, KodiSeasonNumber))
        KodiSeasonId = self.cursor.fetchone()

        if KodiSeasonId:
            return KodiSeasonId[0]

        return -1

    def get_season_number(self, KodiSeasonId):
        self.cursor.execute("SELECT season FROM seasons WHERE idSeason = ?", (KodiSeasonId,))
        SeasonNumber = self.cursor.fetchone()

        if SeasonNumber:
            return SeasonNumber[0]

        return None

    # episode


    def add_episode(self, KodiItemId, KodiFileId, Name, Overview, RatingId, Writers, PremiereDate, Poster, RunTimeTicks, Directors, ParentIndexNumber, IndexNumber, OriginalTitle, SortParentIndexNumber, SortIndexNumber, KodiFullPath, KodiPathId, Unique, KodiShowId, KodiSeasonId, Filename, DateCreated, KodiStackedFilename):
        self.cursor.execute("INSERT INTO episode(idEpisode, idFile, c00, c01, c03, c04, c05, c06, c09, c10, c12, c13, c14, c15, c16, c18, c19, c20, idShow, idSeason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (KodiItemId, KodiFileId, Name, Overview, RatingId, Writers, PremiereDate, Poster, RunTimeTicks, Directors, ParentIndexNumber, IndexNumber, OriginalTitle, SortParentIndexNumber, SortIndexNumber, KodiFullPath, KodiPathId, Unique, KodiShowId, KodiSeasonId))
        self.add_file(KodiPathId, Filename, DateCreated, KodiFileId, KodiStackedFilename)

    def update_episode(self, KodiItemId, KodiFileId, Name, Overview, RatingId, Writers, PremiereDate, Poster, RunTimeTicks, Directors, ParentIndexNumber, IndexNumber, OriginalTitle, SortParentIndexNumber, SortIndexNumber, Path, Filename, KodiPathId, Unique, KodiShowId, KodiSeasonId, KodiStackedFilename, DateCreated, KodiFullPath):
        self.cursor.execute("UPDATE episode SET idFile = ?, c00 = ?, c01 = ?, c03 = ?, c04 = ?, c05 = ?, c06 = ?, c09 = ?, c10 = ?, c12 = ?, c13 = ?, c14 = ?, c15 = ?, c16 = ?, c18 = ?, c19 = ?, c20 = ?, idShow = ?, idSeason = ? WHERE idEpisode = ?", (KodiFileId, Name, Overview, RatingId, Writers, PremiereDate, Poster, RunTimeTicks, Directors, ParentIndexNumber, IndexNumber, OriginalTitle, SortParentIndexNumber, SortIndexNumber, KodiFullPath, KodiPathId, Unique, KodiShowId, KodiSeasonId, KodiItemId))
        self.update_file(KodiFileId, DateCreated, Filename, KodiStackedFilename)
        self.cursor.execute("UPDATE path SET strPath = ? WHERE idPath = ?", (Path, KodiPathId))

    def create_entry_episode(self):
        self.cursor.execute("SELECT coalesce(max(idEpisode), 0) FROM episode")
        return self.cursor.fetchone()[0] + 1

    def delete_episode(self, KodiItemId, KodiFileId):
        self.cursor.execute("DELETE FROM uniqueid WHERE media_id = ? AND media_type = ?", (KodiItemId, "episode"))
        self.cursor.execute("DELETE FROM art WHERE media_id = ? AND media_type = ?", (KodiItemId, "episode"))
        self.cursor.execute("DELETE FROM streamdetails WHERE idFile = ?", (KodiFileId,))
        self.cursor.execute("DELETE FROM bookmark WHERE idFile = ?", (KodiFileId,))
        self.cursor.execute("DELETE FROM episode WHERE idEpisode = ?", (KodiItemId,))
        self.cursor.execute("DELETE FROM files WHERE idFile = ?", (KodiFileId,))

    def get_episode_metadata_for_listitem(self, KodiItemId, PathAndFilename):
        self.cursor.execute("SELECT c00, c01, c04, c05, c09, c10, c12, c13, c14, c15, c16, c20, userrating, playCount, lastPlayed, genre, studio, strPath, strTitle, strFileName, totalTimeInSeconds, resumeTimeInSeconds, rating, votes, rating_type, uniqueid_value, uniqueid_type, mpaa, dateAdded, idShow, idSeason FROM episode_view WHERE idEpisode = ?", (KodiItemId,))

        EpisodeData = self.cursor.fetchone()

        if not EpisodeData:
            return {}

        if not PathAndFilename:
            if EpisodeData[17].endswith('|redirect-limit=1000&failonerror=false'):
                PathAndFilename = f"{EpisodeData[17].replace('|redirect-limit=1000&failonerror=false', '')}{EpisodeData[19]}|redirect-limit=1000&failonerror=false"
            else:
                PathAndFilename = f"{EpisodeData[17]}{EpisodeData[19]}"

        People = self.get_people_artwork(KodiItemId, "episode")
        People += self.get_people_artwork(EpisodeData[29], "tvshow")
        Artwork = self.common_db.get_artwork(KodiItemId, "episode", "")
        Artwork.update(self.common_db.get_artwork(EpisodeData[29], "tvshow", "tvshow."))
        Artwork.update(self.common_db.get_artwork(EpisodeData[30], "season", "season."))

        # get Ratings
        self.cursor.execute("SELECT rating_type, rating, votes FROM rating WHERE media_id = ? AND media_type = ?", (KodiItemId, "episode"))
        Ratings = self.cursor.fetchall()

        # UniqueIds
        UniqueIds = self.get_UniqueIds(KodiItemId, "episode")
        return {'KodiMetadataMediatype': "episode", "KodiMetadataDBID": KodiItemId, 'KodiMetadataTitle': EpisodeData[0], 'KodiMetadataOverview': EpisodeData[1], 'KodiMetadataWriter': EpisodeData[2], 'KodiMetadataPremiereDate': EpisodeData[3], 'KodiMetadataDuration': EpisodeData[4], 'KodiMetadataDirector': EpisodeData[5], 'KodiMetadataParentIndexNumber': EpisodeData[6], 'KodiMetadataIndexNumber': EpisodeData[7], 'KodiMetadataOriginalTitle': EpisodeData[8], 'KodiMetadataSortParentIndexNumber': EpisodeData[9], 'KodiMetadataSortIndexNumber': EpisodeData[10], 'KodiMetadataUniqueIdLink': EpisodeData[11], 'KodiMetadataUserRating': EpisodeData[12], 'KodiMetadataPlaycount': EpisodeData[13], 'KodiMetadataLastplayed': EpisodeData[14], 'KodiMetadataSeriesName': EpisodeData[18], 'KodiMetadataGenre': EpisodeData[15], 'KodiMetadataStudioName': EpisodeData[16], 'KodiMetadataPath': EpisodeData[17], 'KodiMetadataPathandfilename': PathAndFilename, 'KodiMetadataProperties': {'TVShowDBID': EpisodeData[29], 'IsFolder': 'false', 'IsPlayable': 'true'}, 'KodiMetadataPeople': People, 'KodiMetadataArtwork': Artwork, 'KodiMetadataRunTimeTicks': EpisodeData[20], 'KodiMetadataPlaybackPositionTicks': EpisodeData[21], 'KodiMetadataRating': EpisodeData[22], 'KodiMetadataVotes': EpisodeData[23], 'KodiMetadataRatingType': EpisodeData[24], 'KodiMetadataUniqueIdValue': EpisodeData[25], 'KodiMetadataUniqueIdType': EpisodeData[26], 'KodiMetadataRatings': Ratings, 'KodiMetadataMPAA': EpisodeData[27], 'KodiMetadataDateCreated': EpisodeData[28], 'KodiMetadataUniqueIds': UniqueIds}

    # boxsets
    def add_boxset(self, strSet, strOverview):
        self.cursor.execute("SELECT coalesce(max(idSet), 0) FROM sets")
        set_id =  self.cursor.fetchone()[0] + 1

        if utils.DatabaseFiles["video-version"] >= 144:
            self.cursor.execute("INSERT INTO sets(idSet, strSet, strOverview, strOriginalSet) VALUES (?, ?, ?, ?)", (set_id, strSet, strOverview, strSet))
        else:
            self.cursor.execute("INSERT INTO sets(idSet, strSet, strOverview) VALUES (?, ?, ?)", (set_id, strSet, strOverview))

        return set_id

    def update_boxset(self, strSet, strOverview, idSet):
        if utils.DatabaseFiles["video-version"] >= 144:
            self.cursor.execute("UPDATE sets SET strSet = ?, strOverview = ?, strOriginalSet = ? WHERE idSet = ?", (strSet, strOverview, strSet, idSet))
        else:
            self.cursor.execute("UPDATE sets SET strSet = ?, strOverview = ? WHERE idSet = ?", (strSet, strOverview, idSet))

    def set_boxset(self, idSet, idMovie):
        self.cursor.execute("UPDATE movie SET idSet = ? WHERE idMovie = ?", (idSet, idMovie))

    def remove_from_boxset(self, idMovie):
        self.cursor.execute("UPDATE movie SET idSet = NULL WHERE idMovie = ?", (idMovie,))

    def delete_boxset(self, idSet):
        self.cursor.execute("DELETE FROM sets WHERE idSet = ?", (idSet,))

    # file
    def add_file(self, idPath, Filename, dateAdded, KodiFileId, KodiStackedFilename):
        if KodiStackedFilename:
            Filename = KodiStackedFilename

        self.cursor.execute("INSERT INTO files(idPath, strFilename, dateAdded, idFile) VALUES (?, ?, ?, ?)", (idPath, Filename, dateAdded, KodiFileId))

    def update_file(self, KodiFileId, dateAdded, Filename, KodiStackedFilename):
        if KodiStackedFilename:
            Filename = KodiStackedFilename

        if Filename:
            self.cursor.execute("UPDATE files SET strFilename = ?, dateAdded = ? WHERE idFile = ?", (Filename, dateAdded, KodiFileId))
        else:
            self.cursor.execute("UPDATE files SET dateAdded = ? WHERE idFile = ?", (dateAdded, KodiFileId))

    def create_entry_file(self):
        self.cursor.execute("SELECT coalesce(max(idFile), 0) FROM files")
        return self.cursor.fetchone()[0] + 1

    # video versions
    def get_add_videoversiontype(self, VersionName, ContentType):
        self.cursor.execute("SELECT id FROM videoversiontype WHERE name = ? AND itemType = ?", (VersionName, VideoversionTypes[ContentType]))
        Data = self.cursor.fetchone()

        if Data:
            return Data[0]

        self.cursor.execute("SELECT coalesce(max(id), 0) FROM videoversiontype")
        VideoVersionTypeId = self.cursor.fetchone()[0] + 1
        self.cursor.execute("INSERT OR REPLACE INTO videoversiontype(id, name, owner, itemType) VALUES (?, ?, ?, ?)", (VideoVersionTypeId, VersionName, 0, VideoversionTypes[ContentType]))
        return VideoVersionTypeId

    def delete_videoversion_by_KodiId_notKodiFileId_KodiType(self, KodiItemId, KodiFileId, KodiType):
        self.cursor.execute("SELECT idFile FROM videoversion WHERE idMedia = ? AND idFile != ? AND media_type = ?", (KodiItemId, KodiFileId, KodiType))
        KodiFileIdsRef = self.cursor.fetchall()
        self.cursor.execute("DELETE FROM videoversion WHERE idMedia = ? AND idFile != ? AND media_type = ?", (KodiItemId, KodiFileId, KodiType))
        SQLData = []

        for KodiFileIdRef in KodiFileIdsRef:
            SQLData.append((KodiFileIdRef[0],))

        if SQLData:
            self.cursor.executemany("DELETE FROM files WHERE idFile = ?", SQLData)

        del SQLData

    def get_KodiFileId_by_videoversion(self, KodiItemId, KodiType):
        self.cursor.execute("SELECT idFile FROM videoversion WHERE idMedia = ? AND media_type = ?", (KodiItemId, KodiType))
        return self.cursor.fetchall()

    def get_movie_bookmark_data(self, KodiItemId, Progress):
        # A grouped movie's metadata duration can belong to a different version.
        self.cursor.execute(
            """
            SELECT version.idFile, CASE WHEN :progress > 0 THEN COALESCE(
                (SELECT MAX(stream.iVideoDuration) FROM streamdetails AS stream
                 WHERE stream.idFile = version.idFile AND stream.iStreamType = 0
                   AND stream.iVideoDuration > :progress),
                (SELECT CAST(movie.c11 AS REAL) FROM movie
                 WHERE movie.idMovie = version.idMedia AND movie.idFile = version.idFile
                   AND CAST(movie.c11 AS REAL) > :progress AND version.itemType = :regular
                   AND NOT EXISTS (
                       SELECT 1 FROM videoversion AS sibling
                       WHERE sibling.idMedia = version.idMedia AND sibling.media_type = 'movie'
                         AND sibling.itemType = :regular AND sibling.idFile <> version.idFile
                   )), 0) ELSE 0 END
            FROM videoversion AS version
            WHERE version.idMedia = :movie AND version.media_type = 'movie'
        """, {"movie": KodiItemId, "progress": Progress or 0, "regular": VideoversionTypes["regular"]})
        return self.cursor.fetchall()


    # people
    def add_person(self, PersonName, ArtUrl):
        self.cursor.execute("SELECT coalesce(max(actor_id), 0) FROM actor")
        PersonId = self.cursor.fetchone()[0] + 1
        PersonNameMod = PersonName

        while True:
            try:
                self.cursor.execute("INSERT INTO actor(actor_id, name, art_urls) VALUES (?, ?, ?)", (PersonId, PersonNameMod, ArtUrl))
                break
            except Exception:
                PersonNameMod += " "

            if len(PersonNameMod) >= 255: # max 256 char
                return -1

        return PersonId

    def update_person(self, PersonId, PersonName, ArtUrl):
        PersonNameMod = PersonName

        while True:
            try:
                self.cursor.execute("UPDATE actor SET name = ?, art_urls = ? WHERE actor_id = ?", (PersonNameMod, ArtUrl, PersonId))
                break
            except Exception:
                PersonNameMod += " "

            if len(PersonNameMod) >= 255:
                return

    def delete_links_actors(self, Media_id, media_type):
        self.cursor.execute("DELETE FROM actor_link WHERE media_id = ? AND media_type = ?", (Media_id, media_type))

    def delete_links_director(self, Media_id, media_type):
        self.cursor.execute("DELETE FROM director_link WHERE media_id = ? AND media_type = ?", (Media_id, media_type))

    def delete_links_writer(self, Media_id, media_type):
        self.cursor.execute("DELETE FROM writer_link WHERE media_id = ? AND media_type = ?", (Media_id, media_type))

    def get_People(self, ActorId):
        MusicVideos = False
        Movies = False
        TVShows = False
        self.cursor.execute("SELECT name, art_urls FROM actor WHERE actor_id = ?", (ActorId,))
        Data = self.cursor.fetchone()

        if Data:
            self.cursor.execute("SELECT EXISTS(SELECT 1 FROM actor_link WHERE actor_id = ? AND media_type = ?)", (ActorId, "musicvideo"))

            if self.cursor.fetchone()[0]:
                MusicVideos = True
            else:
                self.cursor.execute("SELECT EXISTS(SELECT 1 FROM director_link WHERE actor_id = ? AND media_type = ?)", (ActorId, "musicvideo"))

                if self.cursor.fetchone()[0]:
                    MusicVideos = True
                else:
                    self.cursor.execute("SELECT EXISTS(SELECT 1 FROM writer_link WHERE actor_id = ? AND media_type = ?)", (ActorId, "musicvideo"))

                    if self.cursor.fetchone()[0]:
                        MusicVideos = True

            self.cursor.execute("SELECT EXISTS(SELECT 1 FROM actor_link WHERE actor_id = ? AND media_type = ?)", (ActorId, "movie"))

            if self.cursor.fetchone()[0]:
                Movies = True
            else:
                self.cursor.execute("SELECT EXISTS(SELECT 1 FROM director_link WHERE actor_id = ? AND media_type = ?)", (ActorId, "movie"))

                if self.cursor.fetchone()[0]:
                    Movies = True
                else:
                    self.cursor.execute("SELECT EXISTS(SELECT 1 FROM writer_link WHERE actor_id = ? AND media_type = ?)", (ActorId, "movie"))

                    if self.cursor.fetchone()[0]:
                        Movies = True

            self.cursor.execute("SELECT EXISTS(SELECT 1 FROM actor_link WHERE actor_id = ? AND media_type = ?)", (ActorId, "tvshow"))

            if self.cursor.fetchone()[0]:
                TVShows = True
            else:
                self.cursor.execute("SELECT EXISTS(SELECT 1 FROM director_link WHERE actor_id = ? AND media_type = ?)", (ActorId, "tvshow"))

                if self.cursor.fetchone()[0]:
                    TVShows = True
                else:
                    self.cursor.execute("SELECT EXISTS(SELECT 1 FROM writer_link WHERE actor_id = ? AND media_type = ?)", (ActorId, "tvshow"))

                    if self.cursor.fetchone()[0]:
                        TVShows = True

            return Data[0], Data[1], MusicVideos, Movies, TVShows

        return "", "", False, False, False

    def del_musicartist(self, ArtistId):
        self.delete_people_by_Id(ArtistId)

    def delete_people_by_Id(self, ActorId):
        self.cursor.execute("DELETE FROM art WHERE media_id = ? AND media_type = ?", (ActorId, "actor"))
        self.cursor.execute("DELETE FROM actor_link WHERE actor_id = ?", (ActorId,))
        self.cursor.execute("DELETE FROM director_link WHERE actor_id = ?", (ActorId,))
        self.cursor.execute("DELETE FROM writer_link WHERE actor_id = ?", (ActorId,))
        self.cursor.execute("DELETE FROM actor WHERE actor_id = ?", (ActorId,))

    def add_director_link(self, ActorId, MediaId, MediaType):
        self.cursor.execute("INSERT OR REPLACE INTO director_link(actor_id, media_id, media_type) VALUES (?, ?, ?)", (ActorId, MediaId, MediaType))

    def add_writer_link(self, ActorId, MediaId, MediaType):
        self.cursor.execute("INSERT OR REPLACE INTO writer_link(actor_id, media_id, media_type) VALUES (?, ?, ?)", (ActorId, MediaId, MediaType))

    def add_actor_link(self, ActorId, MediaId, MediaType, Role, Order):
        self.cursor.execute("INSERT OR REPLACE INTO actor_link(actor_id, media_id, media_type, role, cast_order) VALUES (?, ?, ?, ?, ?)", (ActorId, MediaId, MediaType, Role, Order))

    def get_people_artwork(self, KodiItemId, ContentType):
        People = ()
        PeopleCounter = 0
        self.cursor.execute("SELECT actor_id, role FROM actor_link WHERE media_id = ? AND media_type = ? ORDER BY cast_order", (KodiItemId, ContentType))
        ActorLinks = self.cursor.fetchall()

        for ActorLink in ActorLinks:
            self.cursor.execute("SELECT name, art_urls FROM actor WHERE actor_id = ?", (ActorLink[0],))
            Actor = self.cursor.fetchone()
            People += ((Actor[0], ActorLink[1], PeopleCounter, Actor[1]),)
            PeopleCounter += 1

        self.cursor.execute("SELECT actor_id FROM director_link WHERE media_id = ? and media_type = ?", (KodiItemId, ContentType))
        DirectorLinks = self.cursor.fetchall()

        for DirectorLink in DirectorLinks:
            self.cursor.execute("SELECT name, art_urls FROM actor WHERE actor_id = ?", (DirectorLink[0],))
            Actor = self.cursor.fetchone()
            People += ((Actor[0], "Director", PeopleCounter, Actor[1]),)
            PeopleCounter += 1

        return People

    # streams
    def add_missing_streams(self, KodiFileId, MediaSource):
        self.cursor.execute("SELECT EXISTS(SELECT 1 FROM streamdetails WHERE idFile = ?)", (KodiFileId,))
        if not self.cursor.fetchone()[0]:
            self.add_streams(KodiFileId, MediaSource['KodiStreams']['Video'], MediaSource['KodiStreams']['Audio'], MediaSource['KodiStreams']['Subtitle'], MediaSource['KodiRunTimeTicks'])

    def delete_streams(self, KodiFileId):
        self.cursor.execute("DELETE FROM streamdetails WHERE idFile = ?", (KodiFileId,))

    def add_streams(self, KodiFileId, videostream, audiostream, subtitlestream, runtime):
        #FLAG_NONE = 0x0000
        #FLAG_DEFAULT = 0x0001
        #FLAG_DUB = 0x0002
        #FLAG_ORIGINAL = 0x0004
        #FLAG_COMMENT = 0x0008
        #FLAG_LYRICS = 0x0010
        #FLAG_KARAOKE = 0x0020
        #FLAG_FORCED = 0x0040
        #FLAG_HEARING_IMPAIRED = 0x0080
        #FLAG_VISUAL_IMPAIRED = 0x0100
        SQLData = []

        if utils.DatabaseFiles["video-version"] >= 149:
            for track in videostream:
                Flags = 0x0000

                if track['default']:
                    Flags |= 0x0001

                if track['hearingimpaired']:
                    Flags |= 0x0080

                SQLData.append((KodiFileId, 0, track['codec'], track['aspect'], track['width'], track['height'], runtime, track['stereomode'], track['language'], track['hdrtype'], None, None, None, None, track['hdrdetail'], 40, 2, Flags))

            for track in audiostream:
                Flags = 0x0000

                if track['default']:
                    Flags |= 0x0001

                if track['hearingimpaired']:
                    Flags |= 0x0080

                SQLData.append((KodiFileId, 1, None, None, None, None, None, None, None, None, track['codec'], track['channels'], track['language'], None, None, 40, 2, Flags))

            for track in subtitlestream:
                Flags = 0x0000

                if track['forced']:
                    Flags |= 0x0040

                if track['default']:
                    Flags |= 0x0001

                SQLData.append((KodiFileId, 2, None, None, None, None, None, None, None, None, None, None, None, track['language'], None, 40, 2, Flags))
        elif utils.DatabaseFiles["video-version"] >= 148:
            for track in videostream:
                SQLData.append((KodiFileId, 0, track['codec'], track['aspect'], track['width'], track['height'], runtime, track['stereomode'], track['language'], track['hdrtype'], None, None, None, None, track['hdrdetail'], 40, 2))

            for track in audiostream:
                SQLData.append((KodiFileId, 1, None, None, None, None, None, None, None, None, track['codec'], track['channels'], track['language'], None, None, 40, 2))

            for track in subtitlestream:
                if track['external'] == "0":
                    SQLData.append((KodiFileId, 2, None, None, None, None, None, None, None, None, None, None, None, track['language'], None, 40, 2))
        elif utils.DatabaseFiles["video-version"] >= 144:
            for track in videostream:
                SQLData.append((KodiFileId, 0, track['codec'], track['aspect'], track['width'], track['height'], runtime, track['stereomode'], track['language'], track['hdrtype'], None, None, None, None, track['hdrdetail']))

            for track in audiostream:
                SQLData.append((KodiFileId, 1, None, None, None, None, None, None, None, None, track['codec'], track['channels'], track['language'], None, None))

            for track in subtitlestream:
                if track['external'] == "0":
                    SQLData.append((KodiFileId, 2, None, None, None, None, None, None, None, None, None, None, None, track['language'], None))
        else:
            for track in videostream:
                SQLData.append((KodiFileId, 0, track['codec'], track['aspect'], track['width'], track['height'], runtime, track['stereomode'], track['language'], track['hdrtype'], None, None, None, None))

            for track in audiostream:
                SQLData.append((KodiFileId, 1, None, None, None, None, None, None, None, None, track['codec'], track['channels'], track['language'], None))

            for track in subtitlestream:
                if track['external'] == "0":
                    SQLData.append((KodiFileId, 2, None, None, None, None, None, None, None, None, None, None, None, track['language']))

        if SQLData:
            self.cursor.execute("DELETE FROM streamdetails WHERE idFile = ?", (KodiFileId,))

            if utils.DatabaseFiles["video-version"] >= 149:
                self.cursor.executemany("INSERT INTO streamdetails(idFile, iStreamType, strVideoCodec, fVideoAspect, iVideoWidth, iVideoHeight, iVideoDuration, strStereoMode, strVideoLanguage, strHdrType, strAudioCodec, iAudioChannels, strAudioLanguage, strSubtitleLanguage, strHdrDetail, iSource, iVersion, iFlags) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", SQLData)
            elif utils.DatabaseFiles["video-version"] >= 148:
                self.cursor.executemany("INSERT INTO streamdetails(idFile, iStreamType, strVideoCodec, fVideoAspect, iVideoWidth, iVideoHeight, iVideoDuration, strStereoMode, strVideoLanguage, strHdrType, strAudioCodec, iAudioChannels, strAudioLanguage, strSubtitleLanguage, strHdrDetail, iSource, iVersion) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", SQLData)
            elif utils.DatabaseFiles["video-version"] >= 144:
                self.cursor.executemany("INSERT INTO streamdetails(idFile, iStreamType, strVideoCodec, fVideoAspect, iVideoWidth, iVideoHeight, iVideoDuration, strStereoMode, strVideoLanguage, strHdrType, strAudioCodec, iAudioChannels, strAudioLanguage, strSubtitleLanguage, strHdrDetail) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", SQLData)
            else:
                self.cursor.executemany("INSERT INTO streamdetails(idFile, iStreamType, strVideoCodec, fVideoAspect, iVideoWidth, iVideoHeight, iVideoDuration, strStereoMode, strVideoLanguage, strHdrType, strAudioCodec, iAudioChannels, strAudioLanguage, strSubtitleLanguage) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", SQLData)

        del SQLData

    # stacked times
    def delete_stacktimes(self, KodiFileId):
        self.cursor.execute("DELETE FROM stacktimes WHERE idFile = ?", (KodiFileId,))

    def add_stacktimes(self, idFile, times):
        self.cursor.execute("INSERT OR REPLACE INTO stacktimes(idFile, times) VALUES (?, ?)", (idFile, times))

    # tags
    def get_add_tag(self, TagName):
        self.cursor.execute("SELECT tag_id FROM tag WHERE name = ?", (TagName,))
        Data = self.cursor.fetchone()

        if Data:
            return Data[0]

        self.cursor.execute("SELECT coalesce(max(tag_id), 0) FROM tag")
        TagId = self.cursor.fetchone()[0] + 1
        self.cursor.execute("INSERT OR REPLACE INTO tag(tag_id, name) VALUES (?, ?)", (TagId, TagName))
        return TagId

    def update_tag(self, TagName, TagId):
        while True:
            try:
                self.cursor.execute("UPDATE tag SET name = ? WHERE tag_id = ?", (TagName, TagId))
                break
            except Exception:
                TagName += " "

            if len(TagName) >= 255:
                return

    def add_tag_link(self, TagId, MediaId, MediaType):
        self.cursor.execute("INSERT OR REPLACE INTO tag_link(tag_id, media_id, media_type) VALUES (?, ?, ?)", (TagId, MediaId, MediaType))

    def delete_library_links_tags(self, MediaId, MediaType, LibraryName):
        self.cursor.execute("SELECT tag_id FROM tag WHERE name = ?", (f"{LibraryName} (Library)",))
        TagId = self.cursor.fetchone()

        if TagId:
            self.cursor.execute("DELETE FROM tag_link WHERE tag_id = ? AND media_id = ? AND media_type = ?", (TagId[0], MediaId, MediaType))

    def delete_links_tags(self, MediaId, MediaType, KodiLibraryTagIds, All):
        if KodiLibraryTagIds:
            KodiLibraryTagIdsArray = ()

            for KodiLibraryTagId in KodiLibraryTagIds:
                KodiLibraryTagIdsArray += (KodiLibraryTagId[0], )

            Param = ",".join(len(KodiLibraryTagIdsArray) * ["?"]  )
            self.cursor.execute(f"DELETE FROM tag_link WHERE media_id = ? AND media_type = ? AND tag_id NOT IN ({Param})", (MediaId, MediaType) + KodiLibraryTagIdsArray)
        elif All:
            self.cursor.execute("DELETE FROM tag_link WHERE media_id = ? AND media_type = ?", (MediaId, MediaType))
        else: # Keep favorites tag
            self.cursor.execute("SELECT tag_id FROM tag_link WHERE media_id = ? AND media_type = ?", (MediaId, MediaType))
            TagIds = self.cursor.fetchall()

            for TagId in TagIds:
                self.cursor.execute("SELECT EXISTS(SELECT 1 FROM tag WHERE tag_id = ? AND name NOT LIKE ?)", (TagId[0], "% (Favorites)"))

                if self.cursor.fetchone()[0]:
                    self.cursor.execute("DELETE FROM tag_link WHERE tag_id = ? AND media_id = ? AND media_type = ?", (TagId[0], MediaId, MediaType))


    def delete_tag_by_Id(self, TagId):
        TagName = ""
        self.cursor.execute("SELECT name FROM tag WHERE tag_id = ?", (TagId,))
        Data = self.cursor.fetchone()

        if Data:
            TagName = Data[0]

        self.cursor.execute("DELETE FROM tag WHERE tag_id = ?", (TagId,))
        self.cursor.execute("DELETE FROM tag_link WHERE tag_id = ?", (TagId,))
        return TagName

    def add_link_tag(self, TagId, KodiItemId, KodiType):
        self.cursor.execute("INSERT OR REPLACE INTO tag_link(tag_id, media_id, media_type) VALUES (?, ?, ?)", (TagId, KodiItemId, KodiType)) # IGNORE required for stacked content

    def set_Favorite_Tag(self, IsFavorite, KodiItemId, KodiType):
        if KodiType == "tvshow":
            TagName = "TVShows (Favorites)"
        else:
            TagName = f"{KodiType[:1].upper() + KodiType[1:]}s (Favorites)"

        self.cursor.execute("SELECT tag_id FROM tag WHERE name = ?", (TagName,))
        Data = self.cursor.fetchone()

        if Data:
            TagId = Data[0]
        else:
            self.cursor.execute("SELECT coalesce(max(tag_id), 0) FROM tag")
            TagId = self.cursor.fetchone()[0] + 1
            self.cursor.execute("INSERT INTO tag(tag_id, name) VALUES (?, ?)", (TagId, TagName))

        if IsFavorite:
            self.add_link_tag(TagId, KodiItemId, KodiType)
        else:
            self.cursor.execute("DELETE FROM tag_link WHERE tag_id = ? AND media_type = ? AND media_id = ?", (TagId, KodiType, KodiItemId))

    def get_Tags(self, KodiItemId, KodiType):
        self.cursor.execute("SELECT tag_id FROM tag_link WHERE media_id = ? AND media_type = ?", (KodiItemId, KodiType))
        TagIds = self.cursor.fetchall()
        Tags = ()

        for Row in TagIds:
            self.cursor.execute("SELECT name FROM tag WHERE tag_id = ?", (Row[0],))
            TagData = self.cursor.fetchone()

            if TagData:
                Tags += (TagData[0],)

        return Tags

    # genres
    def get_genre_name(self, GenreId):
        self.cursor.execute("SELECT name FROM genre WHERE genre_id = ?", (GenreId,))
        Row = self.cursor.fetchone()
        return Row[0] if Row else ""

    def get_add_genre(self, GenreName):
        self.cursor.execute("SELECT genre_id FROM genre WHERE name = ?", (GenreName,))
        Data = self.cursor.fetchone()

        if Data:
            return Data[0]

        self.cursor.execute("SELECT coalesce(max(genre_id), 0) FROM genre")
        GenreId = self.cursor.fetchone()[0] + 1
        self.cursor.execute("INSERT INTO genre(genre_id, name) VALUES (?, ?)", (GenreId, GenreName))
        return GenreId

    def update_genre(self, GenreName, GenreId):
        self.cursor.execute("UPDATE OR IGNORE genre SET name = ? WHERE genre_id = ?", (GenreName, GenreId))

    def add_genre_link(self, GenreId, MediaId, MediaType):
        self.cursor.execute("INSERT OR REPLACE INTO genre_link(genre_id, media_id, media_type) VALUES (?, ?, ?)", (GenreId, MediaId, MediaType))

    def delete_links_genres(self, Media_id, media_type):
        self.cursor.execute("DELETE FROM genre_link WHERE media_id = ? AND media_type = ?", (Media_id, media_type))


    def delete_genre_by_Id(self, GenreId):
        GenreName = ""
        self.cursor.execute("SELECT name FROM genre WHERE genre_id = ?", (GenreId,))
        Data = self.cursor.fetchone()

        if Data:
            GenreName = Data[0]

        self.cursor.execute("DELETE FROM genre_link WHERE genre_id = ?", (GenreId,))
        self.cursor.execute("DELETE FROM genre WHERE genre_id = ?", (GenreId,))
        return GenreName

    # studios
    def get_add_studio(self, StudioName):
        self.cursor.execute("SELECT studio_id FROM studio WHERE name = ?", (StudioName,))
        Data = self.cursor.fetchone()

        if Data:
            return Data[0]

        self.cursor.execute("SELECT coalesce(max(studio_id), 0) FROM studio")
        StudioId = self.cursor.fetchone()[0] + 1
        self.cursor.execute("INSERT OR REPLACE INTO studio(studio_id, name) VALUES (?, ?)", (StudioId, StudioName))
        return StudioId

    def update_studio(self, StudioName, StudioId):
        self.cursor.execute("UPDATE OR IGNORE studio SET name = ? WHERE studio_id = ?", (StudioName, StudioId))

    def add_studio_link(self, GenreId, MediaId, MediaType):
        self.cursor.execute("INSERT OR REPLACE INTO studio_link(studio_id, media_id, media_type) VALUES (?, ?, ?)", (GenreId, MediaId, MediaType))

    def delete_links_studios(self, Media_id, media_type):
        self.cursor.execute("DELETE FROM studio_link WHERE media_id = ? AND media_type = ?", (Media_id, media_type))

    def delete_studio_by_Id(self, StudioId):
        StudioName = ""
        self.cursor.execute("SELECT name FROM studio WHERE studio_id = ?", (StudioId,))
        Data = self.cursor.fetchone()

        if Data:
            StudioName = Data[0]

        self.cursor.execute("DELETE FROM studio_link WHERE studio_id = ?", (StudioId,))
        self.cursor.execute("DELETE FROM studio WHERE studio_id = ?", (StudioId,))
        return StudioName


    # ratings
    def delete_ratings(self, Media_id, media_type, All=True):
        if All:
            self.cursor.execute("DELETE FROM rating WHERE media_id = ? AND media_type = ?", (Media_id, media_type))
        else:
            self.cursor.execute("DELETE FROM rating WHERE media_id = ? AND media_type = ? AND rating_type = ?", (Media_id, media_type, "default"))

    def add_ratings(self, KodiItemId, media_type, rating_type, Rating):
        if Rating:
            self.cursor.execute("SELECT coalesce(max(rating_id), 0) FROM rating")
            rating_id = self.cursor.fetchone()[0] + 1
            self.cursor.execute("INSERT INTO rating(rating_id, media_id, media_type, rating_type, rating) VALUES (?, ?, ?, ?, ?)", (rating_id, KodiItemId, media_type, rating_type, Rating))
            return rating_id

        return None

    # uniqueid
    def delete_uniqueids(self, Media_id, media_type):
        self.cursor.execute("DELETE FROM uniqueid WHERE media_id = ? AND media_type = ?", (Media_id, media_type))

    def add_uniqueids(self, KodiItemId, ProviderIds, MediaId, DefaulId):
        SQLData = []
        SQLData1 = ()

        for Provider, Value in list(ProviderIds.items()):
            if not Value:
                continue

            Provider = Provider.lower()

            if Provider in ("facebook", "instagram", "official website", "x (twitter)", "twitter", "x", "fan site", "wikipedia"):
                continue

            if Provider == DefaulId:
                SQLData1 = (KodiItemId, MediaId, Value, Provider)
            else:
                SQLData.append((KodiItemId, MediaId, Value, Provider))

        if SQLData1:
            self.cursor.execute("SELECT coalesce(max(uniqueid_id), 0) FROM uniqueid")
            UniqueId = self.cursor.fetchone()[0] + 1
            self.cursor.execute("INSERT INTO uniqueid(uniqueid_id, media_id, media_type, value, type) VALUES (?, ?, ?, ?, ?)", (UniqueId,) + SQLData1)
        else:
            UniqueId = None

        if SQLData:
            self.cursor.executemany("INSERT INTO uniqueid(media_id, media_type, value, type) VALUES (?, ?, ?, ?)", SQLData)

        del SQLData
        del SQLData1
        return UniqueId

    def get_movie_tmdb_ids(self):
        self.cursor.execute("SELECT media_id, value FROM uniqueid WHERE media_type = 'movie' AND type = 'tmdb' AND value IS NOT NULL")
        TmdbIds = {}
        for KodiId, TmdbId in self.cursor:
            TmdbId = TmdbId.strip()
            if TmdbId.isascii() and TmdbId.isdecimal() and int(TmdbId) > 0:
                TmdbIds[KodiId] = str(int(TmdbId))
        return TmdbIds

    def get_UniqueIds(self, KodiItemId, KodiType):
        self.cursor.execute("SELECT type, value FROM uniqueid WHERE media_id = ? AND media_type = ?", (KodiItemId, KodiType))
        UniqueIdData = self.cursor.fetchall()
        UniqueIds = {}

        for Row in UniqueIdData:
            UniqueIds[Row[0]] = Row[1]

        return UniqueIds

    # bookmarks

    def delete_bookmark(self, KodiFileId, BookmarkType):
        self.cursor.execute("DELETE FROM bookmark WHERE idFile = ? AND type = ?", (KodiFileId, BookmarkType))

    def add_bookmarks(self, KodiFileId, RunTimeTicks, KodiChapters):
        SQLData = []

        for StartPositionTicks, Image in list(KodiChapters.items()):
            SQLData.append((KodiFileId, StartPositionTicks, RunTimeTicks, Image, "VideoPlayer", 0))

        if SQLData:
            self.cursor.executemany("INSERT INTO bookmark(idFile, timeInSeconds, totalTimeInSeconds, thumbNailImage, player, type) VALUES (?, ?, ?, ?, ?, ?)", SQLData)

        del SQLData

    def delete_movie_resume_bookmarks(self, KodiItemId):
        self.cursor.execute(
            "DELETE FROM bookmark WHERE type = 1 AND idFile IN "
            "(SELECT idFile FROM videoversion WHERE idMedia = ? AND media_type = 'movie' AND itemType = ?)",
            (KodiItemId, VideoversionTypes["regular"]))
        return self.cursor.rowcount > 0

    def fill_resume_bookmark_duration(self, KodiFileId, Runtime):
        if Runtime and Runtime > 0:
            self.cursor.execute(
                "UPDATE bookmark SET totalTimeInSeconds = ? WHERE idFile = ? AND type = 1 "
                "AND COALESCE(totalTimeInSeconds, 0) <= 0 AND timeInSeconds > 0 AND timeInSeconds < ?",
                (Runtime, KodiFileId, Runtime))

    def update_bookmark_playstate(self, KodiFileId, playcount=_UNCHANGED, date_played=_UNCHANGED,
                                  Progress=_UNCHANGED, Runtime=None, *, MarkPlayed=False):
        Update = False

        if Progress is not self._UNCHANGED:
            self.cursor.execute("SELECT timeInSeconds, totalTimeInSeconds FROM bookmark WHERE idFile = ? AND type = 1", (KodiFileId,))
            Data = self.cursor.fetchone()
            if Data:
                if not Progress:
                    self.cursor.execute("DELETE FROM bookmark WHERE idFile = ? AND type = 1", (KodiFileId,))
                    Update = True
                elif Data[0] != Progress or (Runtime and (Data[1] or 0) <= 0):
                    self.cursor.execute("UPDATE bookmark SET timeInSeconds = ?, totalTimeInSeconds = ? WHERE idFile = ? AND type = 1",
                                        (Progress, Runtime or Data[1], KodiFileId))
                    Update = True
            elif Progress:
                self.cursor.execute("INSERT INTO bookmark(idFile, timeInSeconds, totalTimeInSeconds, player, type) VALUES (?, ?, ?, ?, 1)", (KodiFileId, Progress, Runtime, "VideoPlayer"))
                Update = True

        if playcount is self._UNCHANGED and date_played is self._UNCHANGED and not MarkPlayed:
            return Update

        # Update playcounter and last played date
        self.cursor.execute("SELECT playCount, lastPlayed FROM files WHERE idFile = ?", (KodiFileId,))
        Data = self.cursor.fetchone()

        if Data:
            CurrentPlayCount, CurrentLastPlayed = Data
            if playcount is self._UNCHANGED:
                playcount = (CurrentPlayCount or 1) if MarkPlayed else CurrentPlayCount
            if date_played is self._UNCHANGED:
                date_played = CurrentLastPlayed
            if (playcount, date_played) != Data:
                self.cursor.execute("UPDATE files SET playCount = ?, lastPlayed = ? WHERE idFile = ?", (playcount, date_played, KodiFileId))

            if (CurrentPlayCount != playcount) and ((CurrentPlayCount and playcount and playcount -1 != CurrentPlayCount) or (not playcount and CurrentPlayCount) or (not CurrentPlayCount and playcount)):
                Update = True
        else:
            xbmc.log(f"EMBY.database.video_db: update_bookmark_playstate, idFile not found {KodiFileId}", xbmc.LOGERROR)

        return Update

    # countries
    def delete_links_countries(self, Media_id, media_type):
        self.cursor.execute("DELETE FROM country_link WHERE media_id = ? AND media_type = ?", (Media_id, media_type))

    def add_countries_and_links(self, ProductionLocations, media_id, media_type):
        SQLData = []

        for CountryName in ProductionLocations:
            self.cursor.execute("SELECT country_id FROM country WHERE name = ?", (CountryName,))
            Data = self.cursor.fetchone()

            if Data:
                CountryId = Data[0]
            else:
                self.cursor.execute("SELECT coalesce(max(country_id), 0) FROM country")
                CountryId = self.cursor.fetchone()[0] + 1
                self.cursor.execute("INSERT INTO country(country_id, name) VALUES (?, ?)", (CountryId, CountryName))

            SQLData.append((CountryId, media_id, media_type))

        if SQLData:
            self.cursor.executemany("INSERT OR REPLACE INTO country_link(country_id, media_id, media_type) VALUES (?, ?, ?)", SQLData)

        del SQLData

    # settings
    def get_FileSettings(self, KodiFileId):
        self.cursor.execute("SELECT idFile, Deinterlace, ViewMode, ZoomAmount, PixelRatio, VerticalShift, AudioStream, SubtitleStream, SubtitleDelay, SubtitlesOn, Brightness, Contrast, Gamma, VolumeAmplification, AudioDelay, ResumeTime, Sharpness, NoiseReduction, NonLinStretch, PostProcess, ScalingMethod, StereoMode, StereoInvert, VideoStream, TonemapMethod, TonemapParam, Orientation, CenterMixLevel FROM settings WHERE idFile = ?", (KodiFileId,))
        return self.cursor.fetchone()


    def get_Progress(self, KodiFileId):
        self.cursor.execute("SELECT playCount, lastPlayed FROM files WHERE idFile = ?", (KodiFileId,))
        FileInfo = self.cursor.fetchone()

        if FileInfo:
            self.cursor.execute("SELECT timeInSeconds FROM bookmark WHERE idFile = ? AND type = ?", (KodiFileId, 1))
            Progress = self.cursor.fetchone()

            if Progress:
                return True, Progress[0], FileInfo[0], FileInfo[1]

            return True, 0, FileInfo[0], FileInfo[1]

        return False, None, None, None

    # Path
    def delete_path(self, Path):
        self.cursor.execute("DELETE FROM path WHERE strPath = ?", (Path,))


    def get_add_path(self, Path, MediaType, LinkId=None):
        self.cursor.execute("SELECT idPath FROM path WHERE strPath = ?", (Path,))
        Data = self.cursor.fetchone()

        if Data:
            return Data[0]

        self.cursor.execute("SELECT coalesce(max(idPath), 0) FROM path")
        KodiPathId = self.cursor.fetchone()[0] + 1

        if MediaType:
            self.cursor.execute("INSERT INTO path(idPath, strPath, strContent, strScraper, noUpdate, idParentPath) VALUES (?, ?, ?, ?, ?, ?)", (KodiPathId, Path, MediaType, 'metadata.local', 1, LinkId))
        else:
            self.cursor.execute("INSERT INTO path(idPath, strPath, strContent, strScraper, noUpdate, idParentPath) VALUES (?, ?, ?, ?, ?, ?)", (KodiPathId, Path, MediaType, None, 1, LinkId))

        return KodiPathId
