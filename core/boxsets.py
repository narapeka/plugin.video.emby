from helper import utils
from . import common


class BoxSets:
    def __init__(self, Library, SQLs):
        self.Library = Library
        self.SQLs = SQLs

    def update_SQLs(self, SQLs): # When paused, databases are closed and re-opened -> Update database
        self.SQLs = SQLs

    def change(self, Item, IncrementalSync):
        if not common.load_ExistingItem(Item, self.Library, self.SQLs["emby"], "BoxSet"):
            return False

        BoxSetKodiParentIds = ()

        # Query assigned content for collections
        ContentsAssignedToBoxset = []

        for ContentAssignedToBoxset in self.Library.API.get_Items(Item['Id'], ("Video", "Movie"), True, {'GroupItemsIntoCollections': True, "Fields": "PresentationUniqueKey"}, "", None, False):
            ContentsAssignedToBoxset.append(ContentAssignedToBoxset)


        # Boxsets
        common.set_overview(Item)

        if Item['UpdateItem']:
            self.SQLs["video"].common_db.delete_artwork(Item['KodiItemId'], "set")
            self.SQLs["video"].update_boxset(Item['Name'], Item['Overview'], Item['KodiItemId'])
        else:
            Item['KodiItemId'] = self.SQLs["video"].add_boxset(Item['Name'], Item['Overview'])

        if Item['KodiParentId']:
            CurrentBoxSetContent = Item['KodiParentId'].split(",")
        else:
            CurrentBoxSetContent = []


        # Assign boxsets
        for ContentAssignedToBoxset in ContentsAssignedToBoxset:
            if ContentAssignedToBoxset['Type'] not in ("Movie", "Video"):
                continue

            common.set_PresentationUniqueKey(ContentAssignedToBoxset)
            ContentItemKodiId = self.SQLs["emby"].get_KodiId_by_EmbyPresentationKey(ContentAssignedToBoxset['Type'], ContentAssignedToBoxset['PresentationUniqueKey'])

            if ContentItemKodiId:
                if str(ContentItemKodiId) in CurrentBoxSetContent:
                    CurrentBoxSetContent.remove(str(ContentItemKodiId))

                self.SQLs["video"].set_boxset(Item['KodiItemId'], ContentItemKodiId) # assign boxset to movie
                BoxSetKodiParentIds += (str(ContentItemKodiId),)


        # Delete remove content from boxsets
        for KodiContentId in CurrentBoxSetContent:
            self.SQLs["video"].remove_from_boxset(KodiContentId)

        common.set_KodiArtwork(Item, self.Library.ServerData['ServerId'], False)

        self.SQLs["video"].common_db.add_artwork(Item['KodiArtwork'], Item['KodiItemId'], "set")
        Item['KodiParentId'] = ",".join(BoxSetKodiParentIds)
        self.SQLs["emby"].add_reference_boxset(Item['Id'], Item['LibraryId'], Item['KodiItemId'], Item['KodiParentId'])

        return True

    # This updates: Favorite, LastPlayedDate, PlaybackPositionTicks
    def userdata(self, Item, IncrementalSync, UpdateKodiFavorite):
        if not common.verify_KodiIds(Item, IncrementalSync, False):
            return False

        if not common.set_Favorite(Item):
            return False

        if UpdateKodiFavorite:
            self.set_favorite(Item['IsFavorite'], Item)

        return False

    def remove(self, Item, IncrementalSync):

        Deleted = self.SQLs["emby"].remove_item(Item['Id'], "BoxSet", Item['LibraryId'])

        if Deleted:
            if not common.verify_KodiIds(Item, IncrementalSync, False):
                return

            for KodiParentId in self.SQLs["emby"].get_KodiParentIds(Item['Id'], "BoxSet"):
                self.SQLs["video"].remove_from_boxset(KodiParentId)

            self.SQLs["video"].common_db.delete_artwork(Item['KodiItemId'], "set")
            self.set_favorite(False, Item)
            self.SQLs["video"].delete_boxset(Item['KodiItemId'])

    def set_favorite(self, IsFavorite, Item):
        common.validate_FavoriteImage(Item)
        self.SQLs["emby"].update_favourite(IsFavorite, Item['Id'], "BoxSet")

        if IsFavorite and not Item['KodiArtwork']['favourite'] or 'Name' not in Item:
            _, Item['KodiArtwork']['favourite'], Item['Name'] = self.SQLs["video"].get_favoriteData(None, Item['KodiItemId'], "set")

        utils.FavoriteQueue.put((((Item['KodiArtwork']['favourite'] or ""), IsFavorite, f"videodb://movies/sets/{Item['KodiItemId']}/", Item['Name'].replace('"', "'"), "window", 10025),))
