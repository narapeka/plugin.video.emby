from helper import utils

class CommonDatabase:
    def __init__(self, cursor):
        self.cursor = cursor


    # reset
    def delete_tables(self, DatabaseName):
        utils.create_ProgressBar("delete_tables", utils.Translate(33199), f"{utils.Translate(33415)}-{DatabaseName} {utils.Translate(33416)}")

        # Temporay remove triggers
        self.cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger'")
        Triggers = self.cursor.fetchall()

        for Trigger in Triggers:
            self.cursor.execute(f"DROP TRIGGER {Trigger[0]}")

        # Temporay remove Indices
        self.cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='index'")
        Indexs = self.cursor.fetchall()

        for Index in Indexs:
            if not Index[0].startswith("sqlite_autoindex"):
                self.cursor.execute(f"DROP INDEX {Index[0]}")

        # Delete tables
        self.cursor.execute("SELECT tbl_name FROM sqlite_master WHERE type='table'")
        Tables = self.cursor.fetchall()
        Counter = 0

        if Tables:
            Increment = 100.0 / len(Tables)

            for Table in Tables:
                Counter += 1
                utils.update_ProgressBar("delete_tables", Counter * Increment, utils.Translate(33199), f"{utils.Translate(33415)}-{DatabaseName} {utils.Translate(33416)}: {Table[0]}")

                if Table[0] not in ('version', 'versiontagscan', 'videoversiontype'):
                    self.cursor.execute(f"DELETE FROM {Table[0]}")

        # reading triggers
        for Trigger in Triggers:
            self.cursor.execute(Trigger[1])

        # reading index
        for Index in Indexs:
            if not Index[0].startswith("sqlite_autoindex"):
                self.cursor.execute(Index[1])

        utils.close_ProgressBar("delete_tables")

    # artwork
    def delete_artwork(self, KodiId, KodiType):
        with utils.SafeLock(utils.ArtworkDeleteLock):
            self.cursor.execute("SELECT DISTINCT url FROM art WHERE media_id = ? AND media_type = ?", (KodiId, KodiType))
            utils.ArtworkDelete.update(row[0] for row in self.cursor)

        self.cursor.execute("DELETE FROM art WHERE media_id = ? AND media_type = ?", (KodiId, KodiType))


    def add_artwork(self, KodiArtworks, KodiId, KodiType):
        SQLData = []

        for ArtworkId, ImagePath in list(KodiArtworks.items()):
            if ArtworkId != "fanart":
                if ImagePath:
                    SQLData.append((KodiId, KodiType, ArtworkId, ImagePath))
            else:
                for ArtworkFanArtId, ImageFanArtPath in list(KodiArtworks['fanart'].items()):
                    SQLData.append((KodiId, KodiType, ArtworkFanArtId, ImageFanArtPath))

        if SQLData:
            self.cursor.executemany("INSERT INTO art(media_id, media_type, type, url) VALUES (?, ?, ?, ?)", SQLData)

        del SQLData

    def get_artwork(self, KodiItemId, ContentType, PrefixKey):
        if not KodiItemId:
            return {}

        Artwork = {}
        self.cursor.execute("SELECT type, url FROM art WHERE media_id = ? AND media_type = ?", (KodiItemId, ContentType))
        ArtworksData = self.cursor.fetchall()

        for ArtworkData in ArtworksData:
            Artwork[f"{PrefixKey}{ArtworkData[0]}"] = ArtworkData[1]

        return Artwork
