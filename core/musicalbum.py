from helper import utils, copy
from . import common, musicartist


class MusicAlbum:
    def __init__(self, Library, SQLs):
        self.Library = Library
        self.SQLs = SQLs.copy()
        self.SQLs['video'] = None
        self.MusicArtistObject = musicartist.MusicArtist(Library, self.SQLs)

    def update_SQLs(self, SQLs): # When paused, databases are closed and re-opened -> Update database
        self.SQLs = SQLs.copy()
        self.SQLs['video'] = None
        self.MusicArtistObject.update_SQLs(self.SQLs)

    def change(self, Item, IncrementalSync):
        if not common.load_ExistingItem(Item, self.Library, self.SQLs["emby"], "MusicAlbum"):
            return False

        common.set_MetaItems(Item, self.SQLs, None, self.Library, "Studio", 'Studios', "", IncrementalSync, None)
        common.set_RunTimeTicks(Item)
        common.set_common(Item, self.Library.ServerData['ServerId'], False, IncrementalSync)

        if 'Genres' in Item:
            KodiMusicGenre = " / ".join(Item['Genres'])
        else:
            KodiMusicGenre = ""

        # Detect compilations
        Compilation = 0

        if Item.get('AlbumArtist', "").lower() in ("various artists", "various", "various items", "soundtrack", "xvarious artistsx"):
            Compilation = 1

        # Load Arrays
        LibraryIds = common.get_Ids_SingleContent(Item['LibraryIds'])
        KodiItemIds = common.get_Ids_SingleContent(Item['KodiItemId'])

        # Update all existing Kodi Albums
        for Index, LibraryId in enumerate(LibraryIds):
            if Item['Name'] == "--NO INFO--": # Skip injected items updates
                return False

            UpdateItem = copy.Object(Item)
            UpdateKodiItemIdCurrent = KodiItemIds[Index]
            UpdateItem['LibraryId'] = LibraryId
            EmbyMusicArtistIds = self.set_metadata(UpdateItem, IncrementalSync)
            self.SQLs["music"].common_db.delete_artwork(UpdateKodiItemIdCurrent, "album")
            self.SQLs["music"].delete_link_album_artist(UpdateKodiItemIdCurrent)
            self.SQLs["music"].update_album(UpdateKodiItemIdCurrent, UpdateItem['Name'], UpdateItem['AlbumArtistsName'], UpdateItem['KodiProductionYear'], UpdateItem['KodiPremiereDate'], KodiMusicGenre, UpdateItem['Overview'], UpdateItem['KodiArtwork']['thumb'], UpdateItem['CommunityRating'], UpdateItem['KodiLastScraped'], UpdateItem['KodiDateCreated'], UpdateItem['ProviderIds']['MusicBrainzAlbum'], UpdateItem['ProviderIds']['MusicBrainzReleaseGroup'], Compilation, UpdateItem['Studio'], UpdateItem['KodiRunTimeTicks'], UpdateItem['AlbumArtistsSortName'])
            common.set_MusicArtist_links(UpdateKodiItemIdCurrent, self.SQLs, UpdateItem["AlbumArtists"], UpdateItem['LibraryId'], None)
            self.SQLs["music"].common_db.add_artwork(UpdateItem['KodiArtwork'], UpdateKodiItemIdCurrent, "album")
            common.remove_old_EmbyMusicArtist(self.SQLs["emby"], UpdateItem['Id'], UpdateItem['LibraryId'], EmbyMusicArtistIds, self.MusicArtistObject, IncrementalSync)
            self.SQLs["emby"].update_reference_musicalbum(UpdateItem['Id'], UpdateItem['LibraryId'], EmbyMusicArtistIds)

            del UpdateItem

        # New library (insert new Kodi record)
        if Item['LibraryId'] not in LibraryIds:
            EmbyMusicArtistIds = self.set_metadata(Item, IncrementalSync)
            KodiItemIdCurrent = self.SQLs["music"].add_album(Item['Name'], Item['AlbumArtistsName'], Item['KodiProductionYear'], Item['KodiPremiereDate'], KodiMusicGenre, Item['Overview'], Item['KodiArtwork']['thumb'], Item['CommunityRating'], Item['KodiLastScraped'], Item['KodiDateCreated'], Item['ProviderIds']['MusicBrainzAlbum'], Item['ProviderIds']['MusicBrainzReleaseGroup'], Compilation, Item['Studio'], Item['KodiRunTimeTicks'], Item['AlbumArtistsSortName'], Item['LibraryId'])
            Item['LibraryIds'] = common.add_Ids_SingleContent(LibraryIds, Item['LibraryId'])
            Item['KodiItemId'] = common.add_Ids_SingleContent(KodiItemIds, KodiItemIdCurrent)
            self.SQLs["emby"].add_reference_musicalbum(Item['Id'], Item['LibraryId'], KodiItemIds, LibraryIds, EmbyMusicArtistIds)
            common.set_MusicArtist_links(KodiItemIdCurrent, self.SQLs, Item["AlbumArtists"], Item['LibraryId'], None)
            self.SQLs["music"].common_db.add_artwork(Item['KodiArtwork'], KodiItemIdCurrent, "album")

        return not Item['UpdateItem']

    def set_metadata(self, Item, IncrementalSync):
        common.set_MetaItems(Item, self.SQLs, self.MusicArtistObject, self.Library, "MusicArtist", "AlbumArtists", "music", IncrementalSync, Item['LibraryId'])
        EmbyMusicArtistIds = common.get_Artist_Ids(Item, False, True, False)
        common.get_MusicArtistInfos(Item, "AlbumArtists", self.SQLs)
        return EmbyMusicArtistIds

    def userdata(self, Item, IncrementalSync, UpdateKodiFavorite):
        if not common.verify_KodiIds(Item, IncrementalSync, False):
            return False

        if not common.set_Favorite(Item):
            return False
        self.SQLs["emby"].update_favourite(Item['IsFavorite'], Item['Id'], "MusicAlbum")

        if UpdateKodiFavorite:
            self.set_favorite(Item['IsFavorite'], Item)

        return True

    def remove(self, Item, IncrementalSync):
        Item['LibraryId'] = str(Item['LibraryId'])
        Item['LibraryIds'], Item['KodiItemId'], _, _ = self.SQLs["emby"].get_KodiIds_LibraryIds_from_ContentItem(Item['Id'], "MusicAlbum") # (Re)Load LibraryIds, KodiItemId as references could be modify data after collecting

        if not Item['LibraryIds']:
            return

        Links = self.SQLs['emby'].get_Links(Item['Id'], Item['LibraryId'])
        Deleted = self.SQLs["emby"].remove_item(Item['Id'], "MusicAlbum", Item['LibraryId'])
        common.delete_MusicArtist_Links(Item['LibraryId'], Links, self.MusicArtistObject, IncrementalSync, self.SQLs["emby"])
        LibraryIds = common.get_Ids_SingleContent(Item['LibraryIds'])

        if Item['LibraryId'] not in LibraryIds:
            return

        KodiItemIds = common.get_Ids_SingleContent(Item['KodiItemId'])
        Index = LibraryIds.index(Item['LibraryId'])
        KodiItemIdCurrent = KodiItemIds[Index]
        self.set_favorite(False, Item)
        Item['KodiItemId'] = common.del_Ids_SingleContent(KodiItemIds, KodiItemIdCurrent)
        Item['LibraryIds'] = common.del_Ids_SingleContent(LibraryIds, Item['LibraryId'])
        self.SQLs["music"].delete_album(KodiItemIdCurrent)

        if not Deleted:
            self.SQLs['emby'].update_references(Item['Id'], Item['KodiItemId'], "MusicAlbum", Item['LibraryIds'])

    def set_favorite(self, IsFavorite, Item):
        common.validate_FavoriteImage(Item)
        KodiItemIds = common.get_Ids_SingleContent(Item['KodiItemId'])
        LibraryIds = common.get_Ids_SingleContent(Item.get('LibraryIds', ""))

        for Index, KodiItemId in enumerate(KodiItemIds):
            if LibraryIds[Index] and LibraryIds[Index] in self.Library.LibrarySyncedContent and "Playlist" in self.Library.LibrarySyncedContent[LibraryIds[Index]]: # Skip playlist subcontent
                continue

            if IsFavorite and not Item['KodiArtwork']['favourite'] or "Name" not in Item:
                Item['KodiArtwork']['favourite'], Item['Name'] = self.SQLs["music"].get_FavoriteSubcontent(KodiItemId, "album")

            utils.FavoriteQueue.put((((Item['KodiArtwork']['favourite'] or ""), IsFavorite, f"musicdb://albums/{KodiItemId}/", Item['Name'].replace('"', "'"), "window", 10502),))
