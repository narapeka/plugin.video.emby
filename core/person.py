from . import common

class Person:
    def __init__(self, Library, SQLs):
        self.Library = Library
        self.SQLs = SQLs

    def update_SQLs(self, SQLs): # When paused, databases are closed and re-opened -> Update database
        self.SQLs = SQLs

    def change(self, Item, IncrementalSync):
        Item['LibraryId'] = "999999999"

        if not common.load_ExistingItem(Item, self.Library, self.SQLs["emby"], "Person"):
            return False

        # New people must be selected by a synced work, not by a global/person event.
        if not Item['KodiItemId'] and not Item.get('PersonForItem'):
            return False

        common.set_primary_artwork(Item, self.Library.ServerData['ServerId'])
        common.set_KodiArtwork(Item, self.Library.ServerData['ServerId'], False)

        ArtworkChanged = True

        if Item['KodiItemId']: # existing item
            Artwork = {Key: Value for Key, Value in Item['KodiArtwork'].items()
                       if Key != "fanart" and Value}
            Artwork.update(Item['KodiArtwork']['fanart'])
            ArtworkChanged = Artwork != self.SQLs["video"].common_db.get_artwork(
                Item['KodiItemId'], "actor", "")

            if ArtworkChanged:
                self.SQLs["video"].common_db.delete_artwork(Item['KodiItemId'], "actor")

            self.SQLs["video"].update_person(Item['KodiItemId'], Item['Name'], Item['KodiArtwork']['favourite'])

        else:
            Item['KodiItemId'] = self.SQLs["video"].add_person(Item['Name'], Item['KodiArtwork']['favourite'])
            self.SQLs["emby"].add_reference_metadata(Item['Id'], Item['LibraryId'], "Person", Item['KodiItemId'])

        if ArtworkChanged:
            self.SQLs["video"].common_db.add_artwork(Item['KodiArtwork'], Item['KodiItemId'], "actor")

        return not Item['UpdateItem']

    def remove(self, Item, IncrementalSync):
        Delete = self.SQLs["emby"].remove_item(Item['Id'], "Person", Item['LibraryId'])

        if Delete:
            if not common.verify_KodiIds(Item, IncrementalSync, False):
                return

            self.SQLs["video"].delete_people_by_Id(Item['KodiItemId'])
