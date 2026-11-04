from helper import utils
from . import common

class Studio:
    def __init__(self, Library, SQLs):
        self.Library = Library
        self.SQLs = SQLs

    def update_SQLs(self, SQLs): # When paused, databases are closed and re-opened -> Update database
        self.SQLs = SQLs

    def change(self, Item, IncrementalSync):
        if not common.load_ExistingItem(Item, self.Library, self.SQLs["emby"], "Studio"):
            return False

        if not Item['UpdateItem'] and not Item.get('StudioForSeries'):
            return False

        Tags = Item.get('ImageTags') or {}
        if not Tags.get('Primary') and not Tags.get('Thumb'):
            if Item['KodiItemId']:
                Record = self.SQLs["emby"].get_item_by_id(Item['Id'], "Studio")
                Item['KodiArtwork'] = {'favourite': Record[3]}
                self.remove(dict(Item, LibraryId=""), IncrementalSync)
            # Keep only an internal negative-cache row, never a Kodi studio or icon.
            self.SQLs["emby"].add_reference_studio(Item['Id'], Item['LibraryId'], None, None)
            return False

        common.set_primary_artwork(Item, self.Library.ServerData['ServerId'])
        PreviousArtwork = None

        if Item['KodiItemId']: # existing item
            if Item['Name'] == "--NO INFO--": # Skip injected items updates
                self.SQLs["emby"].update_EmbyLibraryMapping(Item['Id'], Item['LibraryId'])
                return False

            PreviousArtwork = self.SQLs["emby"].get_item_by_id(Item['Id'], "Studio")[3]
            self.SQLs["video"].update_studio(Item['Name'], Item['KodiItemId'])
            self.SQLs["emby"].update_reference_studio(Item['Id'], Item['KodiArtwork']['favourite'], Item['LibraryId'])

        else:
            Item['KodiItemId'] = self.SQLs["video"].get_add_studio(Item['Name'])
            self.SQLs["emby"].add_reference_studio(Item['Id'], Item['LibraryId'], Item['KodiItemId'], Item['KodiArtwork']['favourite'])

        # Register the source URL only; Kodi fetches/caches the image when it is displayed.
        if PreviousArtwork != Item['KodiArtwork']['favourite']:
            self.SQLs["video"].common_db.delete_artwork(Item['KodiItemId'], "studio")
            self.SQLs["video"].common_db.add_artwork(
                {'thumb': Item['KodiArtwork']['favourite']}, Item['KodiItemId'], "studio")

        return not Item['UpdateItem']

    def remove(self, Item, IncrementalSync):
        Delete = self.SQLs["emby"].remove_item(Item['Id'], "Studio", Item['LibraryId'])

        if Delete:
            if not common.verify_KodiIds(Item, IncrementalSync, False):
                return

            self.SQLs["video"].common_db.delete_artwork(Item['KodiItemId'], "studio")
            self.SQLs["video"].delete_studio_by_Id(Item['KodiItemId'])
