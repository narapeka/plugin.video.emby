from . import common

class Tag:
    def __init__(self, Library, SQLs):
        self.Library = Library
        self.SQLs = SQLs

    def update_SQLs(self, SQLs): # When paused, databases are closed and re-opened -> Update database
        self.SQLs = SQLs

    def change(self, Item, IncrementalSync):
        if not common.load_ExistingItem(Item, self.Library, self.SQLs["emby"], "Tag"):
            return False

        common.set_primary_artwork(Item, self.Library.ServerData['ServerId'])

        if Item['KodiItemId']: # existing item
            if Item['Name'] == "--NO INFO--": # Skip injected items updates
                self.SQLs["emby"].update_EmbyLibraryMapping(Item['Id'], Item['LibraryId'])
                return False

            self.SQLs["video"].update_tag(Item['Name'], Item['KodiItemId'])
            self.SQLs["emby"].update_reference_tag(Item['Id'], Item.get('Memo', None), Item['KodiArtwork']['favourite'], Item['LibraryId'])

        else:
            Item['KodiItemId'] = self.SQLs["video"].get_add_tag(Item['Name'])
            self.SQLs["emby"].add_reference_tag(Item['Id'], Item['LibraryId'], Item['KodiItemId'], Item.get('Memo', None), Item['KodiArtwork']['favourite'])

        return not Item['UpdateItem']

    def remove(self, Item, IncrementalSync):
        Delete = self.SQLs["emby"].remove_item(Item['Id'], "Tag", Item['LibraryId'])

        if Delete:
            if not common.verify_KodiIds(Item, IncrementalSync, False):
                return

            self.SQLs["video"].delete_tag_by_Id(Item['KodiItemId'])
