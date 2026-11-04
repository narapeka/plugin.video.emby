from helper import utils, copy
from . import common

KodiDBs = ("music", "video")

class MusicGenre:
    def __init__(self, Library, SQLs):
        self.Library = Library
        self.SQLs = SQLs
        self.KodiDBMapping = ("music", "video") # Can be updated via library.py (worker_update)

    def update_SQLs(self, SQLs): # When paused, databases are closed and re-opened -> Update database
        self.SQLs = SQLs

    def change(self, Item, IncrementalSync):
        if not common.load_ExistingItem(Item, self.Library, self.SQLs["emby"], "MusicGenre"):
            return False

        # Load Arrays
        KodiItemIds = common.get_Ids_MultiContentUnique(Item['KodiItemId'])
        LibraryIds = common.get_Ids_MultiContent(Item['LibraryIds'])

        # Load additional data
        LibrarySyncedKodiDBs = self.Library.LibrarySyncedKodiDBs.get(f"{Item['LibraryId']}MusicGenre", "video,music")
        NewItem = False
        common.set_primary_artwork(Item, self.Library.ServerData['ServerId'])

        # Update all existing Kodi musicgenres
        if Item['Name'] != "--NO INFO--": # update not injected items updates
            for Index in range(2):
                if KodiItemIds[Index] and KodiDBs[Index] in self.SQLs and self.SQLs[KodiDBs[Index]]: # Update
                    UpdateItem = copy.Object(Item)
                    UpdateKodiItemIdCurrent = KodiItemIds[Index]
                    PreviousName = self.SQLs[KodiDBs[Index]].get_genre_name(UpdateKodiItemIdCurrent)
                    self.SQLs[KodiDBs[Index]].update_genre(UpdateItem['Name'], UpdateKodiItemIdCurrent)

                    for LibraryId in LibraryIds[Index]:
                        if PreviousName != Item['Name']:
                            self.Library.Views.delete_musicgenre_node(LibraryId, KodiDBs[Index], Item['Id'], PreviousName)
                        self.Library.Views.update_musicgenre_node(LibraryId, KodiDBs[Index], Item['Id'], Item['Name'], Item['KodiArtwork']['favourite'])
                        UpdateItem['LibraryId'] = LibraryId
                        self.SQLs["emby"].update_EmbyLibraryMapping(UpdateItem['Id'], UpdateItem['LibraryId'])
                        self.SQLs["emby"].update_reference_musicgenre(UpdateItem['Id'], UpdateItem['KodiArtwork']['favourite'], UpdateItem['LibraryId'])

                    del UpdateItem

        # New library (insert new Kodi record)
        for Index in range(2):
            if KodiDBs[Index] in self.KodiDBMapping and LibrarySyncedKodiDBs in (KodiDBs[Index], "video,music") and Item['LibraryId'] not in LibraryIds[Index] and KodiDBs[Index] in self.SQLs and self.SQLs[KodiDBs[Index]]:
                Item['LibraryIds'] = common.add_Ids_MultiContent(LibraryIds, Item['LibraryId'], Index)
                KodiItemIdCurrent = str(self.SQLs[KodiDBs[Index]].get_add_genre(Item['Name']))
                Item['KodiItemId'] = common.add_Ids_MultiContentUnique(KodiItemIds, Index, KodiItemIdCurrent)
                self.Library.Views.update_musicgenre_node(Item['LibraryId'], KodiDBs[Index], Item['Id'], Item['Name'], Item['KodiArtwork']['favourite'])
                NewItem = True

        if NewItem:
            self.SQLs["emby"].add_reference_musicgenre(Item['Id'], Item['LibraryId'], Item['KodiItemId'], Item['KodiArtwork']['favourite'], Item['LibraryIds'])

        return not Item['UpdateItem']

    def remove(self, Item, IncrementalSync):
        Item['LibraryIds'], Item['KodiItemId'], _, _ = self.SQLs["emby"].get_KodiIds_LibraryIds_from_ContentItem(Item['Id'], "MusicGenre") # (Re)Load LibraryIds, KodiItemId as refreences could be modify data after collecting

        if not Item['LibraryIds']:
            return

        Deleted = self.SQLs["emby"].remove_item(Item['Id'], "MusicGenre", Item['LibraryId'])
        KodiItemIds = common.get_Ids_MultiContentUnique(Item['KodiItemId'])
        LibrarySyncedKodiDBs = self.Library.LibrarySyncedKodiDBs.get(f"{Item['LibraryId']}MusicGenre", "video,music")
        KodiDBsUpdate = LibrarySyncedKodiDBs.split(",")
        LibraryIds = common.get_Ids_MultiContent(Item['LibraryIds'])

        for KodiDBUpdate in KodiDBsUpdate:
            IndexDatabase = KodiDBs.index(KodiDBUpdate)

            if KodiDBs[IndexDatabase] not in self.SQLs or not self.SQLs[KodiDBs[IndexDatabase]]:
                continue

            if Item['LibraryId'] in LibraryIds[IndexDatabase]:
                Name = self.SQLs[KodiDBUpdate].get_genre_name(KodiItemIds[IndexDatabase])
                self.Library.Views.delete_musicgenre_node(Item['LibraryId'], KodiDBUpdate, Item['Id'], Name)
                LibraryIdsUpdated, _ = common.del_Ids_MultiContent(LibraryIds, Item['LibraryId'], IndexDatabase)

                if not LibraryIds[IndexDatabase]:
                    KodiItemIdCurrent = KodiItemIds[IndexDatabase]
                    self.del_Genre(Item, KodiDBs[IndexDatabase], KodiItemIdCurrent, IncrementalSync)
                    Item['KodiItemId'] = common.del_Ids_MultiContentUnique(KodiItemIds, IndexDatabase)

                Item['LibraryIds'] = LibraryIdsUpdated

        if not Deleted:
            self.SQLs['emby'].update_references(Item['Id'], Item['KodiItemId'], "MusicGenre", Item['LibraryIds'])

    def del_Genre(self, Item, KodiDB, KodiItemId, IncrementalSync):
        self.SQLs[KodiDB].delete_genre_by_Id(KodiItemId)
