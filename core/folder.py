import json
from helper import copy

class Folder:
    def __init__(self, SQLs):
        self.SQLs = SQLs

    def update_SQLs(self, SQLs): # When paused, databases are closed and re-opened -> Update database
        self.SQLs = SQLs

    def change(self, Item, IncrementalSync):
        EmbyItem = copy.Object(Item)

        if 'Path' in Item and Item['Path']:
            if Item['Path'].find("/") >= 0: # Linux
                Path = f"{Item['Path']}/"
            else: # Windows
                Path = f"{Item['Path']}\\"
        else:
            Path = None

        self.SQLs["emby"].add_reference_folder(Item['Id'], Item['LibraryId'], Path, json.dumps(EmbyItem))
        del EmbyItem

        return True

    def remove(self, Item, IncrementalSync):
        self.SQLs["emby"].remove_item(Item['Id'], "Folder", Item['LibraryId'])

    def userdata(self, Item, IncrementalSync, _UpdateKodiFavorite):

        return False
