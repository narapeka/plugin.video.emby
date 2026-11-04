import xbmc
from . import common_db

class TextureDatabase:
    def __init__(self, cursor):
        self.cursor = cursor
        self.common_db = common_db.CommonDatabase(cursor)

    def add_Index(self):
        try: # xbox issue
            self.cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_texture_imagehash'")
            IndexTest = self.cursor.fetchone()

            if not IndexTest:
                self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_texture_cachedurl on texture (cachedurl)")
                self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_texture_imagehash on texture (imagehash)")
                self.cursor.execute("ANALYZE")
        except Exception as Error:
            xbmc.log(f"EMBY.database.texture_db: Database add index error: {Error}", xbmc.LOGERROR)

    def delete_Index(self):
        try: # xbox issue
            self.cursor.execute("DROP INDEX IF EXISTS idx_texture_cachedurl")
            self.cursor.execute("DROP INDEX IF EXISTS idx_texture_imagehash")
            self.cursor.execute("ANALYZE")
        except Exception as Error:
            xbmc.log(f"EMBY.database.texture_db: Database delete index error: {Error}", xbmc.LOGERROR)

    def delete_textures(self, Urls):
        Placeholders = ",".join("?" * len(Urls))
        self.cursor.execute(f"SELECT cachedurl FROM texture WHERE url IN ({Placeholders})", Urls)
        CachedUrls = self.cursor.fetchall()
        self.cursor.execute(f"DELETE FROM texture WHERE url IN ({Placeholders})", Urls)
        return CachedUrls

    def clear_cache(self):
        self.cursor.execute("DELETE FROM sizes")
        self.cursor.execute("DELETE FROM texture")
        self.cursor.execute("DELETE FROM path")
