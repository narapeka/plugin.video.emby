from helper import utils
from . import common, series


class Season:
    def __init__(self, Library, SQLs):
        self.Library = Library
        self.SQLs = SQLs
        self.SeriesObject = series.Series(Library, SQLs)

    def update_SQLs(self, SQLs): # When paused, databases are closed and re-opened -> Update database
        self.SQLs = SQLs
        self.SeriesObject.update_SQLs(self.SQLs)

    def change(self, Item, IncrementalSync):
        if 'Name' not in Item:
            return False

        if not common.load_ExistingItem(Item, self.Library, self.SQLs["emby"], "Season"):
            return False

        common.set_PresentationUniqueKey(Item)
        common.set_overview(Item)
        ExistingParents = {}
        common.set_ItemsDependencies(Item, self.SQLs, self.SeriesObject, self.Library,
                                    "Series", IncrementalSync, Item['LibraryId'],
                                    ExistingParents=ExistingParents)
        common.set_KodiArtwork(Item, self.Library.ServerData['ServerId'], False)

        Item['IndexNumber'] = Item.get('IndexNumber', 0)
        Item['SeriesName'] = Item.get('SeriesName', "")
        if "Series" in ExistingParents:
            Item['KodiParentId'] = ExistingParents["Series"][1]
        else:
            Item['KodiParentId'] = self.SQLs["emby"].get_KodiId_by_EmbyId_EmbyType(
                Item['SeriesId'], "Series")

        if not Item['UpdateItem']:
            StackedKodiId = self.SQLs["emby"].get_KodiId_by_EmbyPresentationKey("Season", Item['PresentationUniqueKey'])

            if StackedKodiId:
                Item['KodiItemId'] = StackedKodiId
                self.SQLs["emby"].add_reference_season(Item['Id'], Item['LibraryId'], Item['KodiItemId'], Item['KodiParentId'], Item['PresentationUniqueKey'])

                return False

            Item['KodiItemId'] = self.SQLs["video"].create_entry_season()
        else:
            self.SQLs["video"].common_db.delete_artwork(Item['KodiItemId'], "season")

        self.SQLs["video"].common_db.add_artwork(Item['KodiArtwork'], Item['KodiItemId'], "season")

        if Item['UpdateItem']:
            if Item['Name'] == "--NO INFO--": # Skip injected items updates
                return False

            self.SQLs["video"].update_season(Item['KodiParentId'], Item['IndexNumber'], Item['Name'], Item['KodiItemId'], Item['Overview'])
            self.SQLs["emby"].update_reference_generic(Item['Id'], Item['LibraryId'])

        else:
            self.SQLs["video"].add_season(Item['KodiItemId'], Item['KodiParentId'], Item['IndexNumber'], Item['Name'], Item['Overview'])
            self.SQLs["emby"].add_reference_season(Item['Id'], Item['LibraryId'], Item['KodiItemId'], Item['KodiParentId'], Item['PresentationUniqueKey'])

        return not Item['UpdateItem']

    # This updates: Favorite, LastPlayedDate, PlaybackPositionTicks
    def userdata(self, Item, IncrementalSync, UpdateKodiFavorite):
        if not common.verify_KodiIds(Item, IncrementalSync, False):
            return False

        common.set_Favorite(Item)

        if UpdateKodiFavorite:
            self.set_favorite(Item['IsFavorite'], Item)

        self.SQLs["emby"].update_favourite(Item['IsFavorite'], Item['Id'], "Season")

        return False

    # Remove showid, fileid, pathid, emby reference.
    # There's no episodes left, delete show and any possible remaining seasons
    def remove(self, Item, IncrementalSync):
        Delete = self.SQLs["emby"].remove_item(Item['Id'], "Season", Item['LibraryId'])

        if Delete:
            if not common.verify_KodiIds(Item, IncrementalSync, False):
                return

            self.set_favorite(False, Item)
            SubcontentKodiIds = self.SQLs["video"].delete_season(Item['KodiItemId'])

            for KodiId, EmbyType in SubcontentKodiIds:
                self.SQLs["emby"].remove_item_by_KodiId(KodiId, EmbyType, Item['LibraryId'])

    def set_favorite(self, IsFavorite, Item):
        common.validate_FavoriteImage(Item)

        if IsFavorite and not Item['KodiArtwork']['favourite'] or "Name" not in Item or "IndexNumber" not in Item:
            Item['KodiArtwork']['favourite'], Item['Name'], Item['IndexNumber'] = self.SQLs["video"].get_FavoriteSubcontent(Item['KodiItemId'], "season")

        if Item['Name']:
            utils.FavoriteQueue.put((((Item['KodiArtwork']['favourite'] or ""), IsFavorite, f"videodb://tvshows/titles/{Item['KodiParentId']}/{Item['IndexNumber']}/", Item['Name'].replace('"', "'"), "window", 10025),))
