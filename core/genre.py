from helper import utils
from . import common

class Genre:
    def __init__(self, Library, SQLs):
        self.Library = Library
        self.SQLs = SQLs

    def update_SQLs(self, SQLs): # When paused, databases are closed and re-opened -> Update database
        self.SQLs = SQLs

    def change(self, Item, IncrementalSync):
        if not common.load_ExistingItem(Item, self.Library, self.SQLs["emby"], "Genre"):
            return False

        common.set_primary_artwork(Item, self.Library.ServerData['ServerId'])

        if Item['KodiItemId']: # existing item
            if Item['Name'] == "--NO INFO--": # Skip injected items updates
                self.SQLs["emby"].update_EmbyLibraryMapping(Item['Id'], Item['LibraryId'])
                return False

            self.SQLs["video"].update_genre(Item['Name'], Item['KodiItemId'])
            self.SQLs["emby"].update_reference_genre(Item['Id'], Item['KodiArtwork']['favourite'], Item['LibraryId'])

        else:
            Item['KodiItemId'] = self.SQLs["video"].get_add_genre(Item['Name'])
            self.SQLs["emby"].add_reference_genre(Item['Id'], Item['LibraryId'], Item['KodiItemId'], Item['KodiArtwork']['favourite'])

        return not Item['UpdateItem']

    def remove(self, Item, IncrementalSync):
        Delete = self.SQLs["emby"].remove_item(Item['Id'], "Genre", Item['LibraryId'])

        if Delete:
            if not common.verify_KodiIds(Item, IncrementalSync, False):
                return

            self.SQLs["video"].delete_genre_by_Id(Item['KodiItemId'])
