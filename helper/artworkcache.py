from database import dbio
from . import utils


def delete_artworkcache_watchdog():
    while True:
        if utils.sleep(1):
            return

        delete_artworkcache()

def delete_artworkcache():
    with utils.SafeLock(utils.ArtworkDeleteLock):
        if utils.ArtworkDelete:
            SQLs = {}
            dbio.DBOpenRW("texture", "artwork_cache", SQLs)
            Urls = list(utils.ArtworkDelete)

            for Index in range(0, len(Urls), 500):
                Chunk = Urls[Index:Index + 500]
                CachedUrls = SQLs['texture'].delete_textures(Chunk)

                for CachedUrl in CachedUrls:
                    Path = f"{utils.FolderUserdataThumbnails}{CachedUrl[0]}"
                    utils.delFile(Path)
                    utils.delFile(f"{Path.rsplit('.', 1)[0]}.dds")

            dbio.DBCloseRW("texture", "artwork_cache", SQLs)
            utils.ArtworkDelete.clear()
