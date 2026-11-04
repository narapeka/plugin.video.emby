from urllib.parse import urlencode

from emby.views import PLUGIN_PATH
from helper import utils
from . import common, audio, musicvideo, tag


class Playlist:
    def __init__(self, Library, SQLs):
        self.Library = Library
        self.SQLs = SQLs
        self.TagObject = tag.Tag(Library, SQLs)
        self.AudioObject = audio.Audio(Library, SQLs)
        self.MusicVideoObject = musicvideo.MusicVideo(Library, SQLs)

    def update_SQLs(self, SQLs): # When paused, databases are closed and re-opened -> Update database
        self.SQLs = SQLs
        self.TagObject.update_SQLs(self.SQLs)
        self.AudioObject.update_SQLs(self.SQLs)
        self.MusicVideoObject.update_SQLs(self.SQLs)

    def change(self, Item, IncrementalSync):
        if not common.load_ExistingItem(Item, self.Library, self.SQLs["emby"], "Playlist"):
            return False

        common.set_primary_artwork(Item, self.Library.ServerData['ServerId'])
        ItemFilename = utils.valid_Filename(Item['Name'])
        utils.delFile(f"{utils.PlaylistPathMusic}emby_{ItemFilename}_audio.m3u")
        utils.delFile(f"{utils.PlaylistPathVideo}emby_{ItemFilename}_video.m3u")
        TrackNumber = {"Audio": 0, "MusicVideo": 0}
        M3UPlaylist = {"Audio": "", "Video": ""}
        KodiPlaylistId = {"Audio": "", "Video": ""}
        EmbyRemoveIds = set()
        EmbyLinkedId = {"Audio": (), "Video": (), "Movie": (), "Episode": (), "MusicVideo": ()}
        PlaylistItems = self.Library.API.get_Items(Item['Id'], ("Audio", "Video", "Movie", "Episode", "MusicVideo"), False, {}, "", None, True)

        # Get previously links EmbyItemIds
        if Item['UpdateItem']:
            for Index in range(5):
                EmbyExistingIds = Item['EmbyLinkedId'].split(";")

                if EmbyExistingIds[Index]:
                    EmbyRemoveIds = EmbyRemoveIds.union(EmbyExistingIds[Index].split(","))

        for PlaylistItem in PlaylistItems:
            common.set_RunTimeTicks(PlaylistItem)
            common.set_streams(PlaylistItem)
            PlaylistItemType = PlaylistItem.get('Type', "")

            if not PlaylistItemType:
                continue

            EmbyLinkedId[PlaylistItemType] += (str(PlaylistItem['Id']),)

            if str(PlaylistItem['Id']) in EmbyRemoveIds:
                EmbyRemoveIds.remove(str(PlaylistItem['Id']))

            PlaylistItem['ParentIndexNumber'] = 0
            PlaylistItem['LibraryId'] = Item['LibraryId']
            common.set_common(PlaylistItem, self.Library.ServerData['ServerId'], True, IncrementalSync)

            if PlaylistItemType == "Audio":
                common.set_path_filename(PlaylistItem, self.Library.ServerData['ServerId'], None)
                TrackNumber["Audio"] += 1
                PlaylistItem['IndexNumber'] = TrackNumber["Audio"]
                self.AudioObject.change(PlaylistItem, IncrementalSync, Item['Id'])

                if "KodiItemIdNew" in PlaylistItem:
                    self.SQLs["music"].add_song_tag(PlaylistItem['KodiItemIdNew'], f"EmbyPlaylistId-{Item['Id']}")

                M3UPlaylist["Audio"] += f"#EXTINF:-1,{PlaylistItem['Name']}\n"
                M3UPlaylist["Audio"] += f"{PlaylistItem['KodiFullPath']}\n"
            elif PlaylistItemType == "MusicVideo":
                TrackNumber["MusicVideo"] += 1
                PlaylistItem['IndexNumber'] = TrackNumber["MusicVideo"]
                PlaylistTag = {"LibraryId": PlaylistItem["LibraryId"], "Type": "Tag", "Id": f"{utils.MappingIds['Tag']}{Item['Id']}", "Name": Item['Name'], "Memo": "playlist", 'ImageTags': Item.get('ImageTags', [])}
                self.TagObject.change(PlaylistTag, False)
                self.MusicVideoObject.change(PlaylistItem, IncrementalSync, PlaylistTag)
                common.set_RunTimeTicks(PlaylistItem)
                common.set_streams(PlaylistItem)
                common.set_path_filename(PlaylistItem, self.Library.ServerData['ServerId'], None)
                M3UPlaylist["Video"] += f"#EXTINF:-1,{PlaylistItem['Name']}\n"
                M3UPlaylist["Video"] += f"{PlaylistItem['KodiFullPath']}\n"

        if M3UPlaylist["Audio"]:
            M3UData = f'#EXTCPlayListM3U::M3U\n{M3UPlaylist["Audio"]}'
            KodiPlaylistId["Audio"] = f"emby_{ItemFilename}_audio"
            utils.mkDir(utils.PlaylistPathMusic)
            utils.writeFile(f'{utils.PlaylistPathMusic}{KodiPlaylistId["Audio"]}.m3u', M3UData.encode("utf-8"))

        if M3UPlaylist["Video"]:
            M3UData = f'#EXTCPlayListM3U::M3U\n{M3UPlaylist["Video"]}'
            KodiPlaylistId["Video"] = f"emby_{ItemFilename}_video"
            utils.mkDir(utils.PlaylistPathVideo)
            utils.writeFile(f'{utils.PlaylistPathVideo}{KodiPlaylistId["Video"]}.m3u', M3UData.encode("utf-8"))

        EmbyLinkedId["Audio"] = ",".join(EmbyLinkedId["Audio"])
        EmbyLinkedId["Video"] = ",".join(EmbyLinkedId["Video"])
        EmbyLinkedId["Movie"] = ",".join(EmbyLinkedId["Movie"])
        EmbyLinkedId["Episode"] = ",".join(EmbyLinkedId["Episode"])
        EmbyLinkedId["MusicVideo"] = ",".join(EmbyLinkedId["MusicVideo"])
        Item['KodiItemId'] = f'{KodiPlaylistId["Audio"]};{KodiPlaylistId["Video"]}'
        Item['EmbyLinkedId'] = f'{EmbyLinkedId["Audio"]};{EmbyLinkedId["Video"]};{EmbyLinkedId["Movie"]};{EmbyLinkedId["Episode"]};{EmbyLinkedId["MusicVideo"]}'
        self.SQLs["emby"].add_reference_playlist(Item['Id'], Item['LibraryId'], Item['KodiItemId'], Item['KodiArtwork']['favourite'], Item['EmbyLinkedId'], Item['Name'])
        self.Library.Views.update_playlist_nodes(Item['Id'], Item['Name'], Item['KodiArtwork']['favourite'], Item['EmbyLinkedId'])

        if EmbyRemoveIds:
            for EmbyRemoveId in EmbyRemoveIds:
                self.SQLs["emby"].add_RemoveItem(EmbyRemoveId, Item['LibraryId'])

        return False

    def remove(self, Item, IncrementalSync):
        if not common.verify_KodiIds(Item, IncrementalSync, False):
            return

        self.set_favorite(False, Item)
        self.Library.Views.delete_playlist_nodes(Item['Id'])
        KodiItemIds = Item['KodiItemId'].split(";")

        if KodiItemIds[0]: # Audio
            utils.delFile(f"{utils.PlaylistPathMusic}{KodiItemIds[0]}.m3u")

        if KodiItemIds[1]: # Video
            utils.delFile(f"{utils.PlaylistPathVideo}{KodiItemIds[1]}.m3u")
            TagId = f"{utils.MappingIds['Tag']}{Item['Id']}"
            TagKodiId = self.SQLs["emby"].get_KodiId_by_EmbyId_EmbyType(TagId, "Tag")
            self.TagObject.remove({'Id': TagId, 'KodiItemId': TagKodiId, "LibraryId": Item['LibraryId']}, IncrementalSync)

        self.SQLs["emby"].remove_item(Item['Id'], "Playlist", Item['LibraryId'])

    def userdata(self, Item, IncrementalSync, UpdateKodiFavorite):
        common.set_Favorite(Item)

        if UpdateKodiFavorite:
            self.set_favorite(Item['IsFavorite'], Item)

        self.SQLs["emby"].update_favourite(Item['IsFavorite'], Item['Id'], "Playlist")

        return False

    def set_favorite(self, IsFavorite, Item):
        common.validate_FavoriteImage(Item)
        KodiItemIds = Item['KodiItemId'].split(";")
        EmbyLinkedIds = Item['EmbyLinkedId'].split(";")

        if IsFavorite and not Item['KodiArtwork']['favourite'] and self.SQLs.get("emby"):
            Item['KodiArtwork']['favourite'] = self.SQLs["emby"].get_item_by_id(Item['Id'], "Playlist")[3]

        if EmbyLinkedIds[0]: # Audio
            utils.FavoriteQueue.put((((Item['KodiArtwork']['favourite'] or ""), IsFavorite, f"{utils.PlaylistPathMusic}{KodiItemIds[0]}.m3u", Item['Name'].replace('"', "'"), "window", 10502),))

        if EmbyLinkedIds[4]: # Musicvideo
            utils.FavoriteQueue.put((((Item['KodiArtwork']['favourite'] or ""), IsFavorite, f"{utils.PlaylistPathVideo}{KodiItemIds[1]}.m3u", Item['Name'].replace('"', "'"), "window", 10025),))

        if EmbyLinkedIds[1] or EmbyLinkedIds[2] or EmbyLinkedIds[3]: # Mixed videos
            Params = urlencode({"mode": "playlist", "mediatype": "video",
                                "server": self.Library.ServerData["ServerId"], "playlistid": Item["Id"]})
            utils.FavoriteQueue.put((((Item['KodiArtwork']['favourite'] or ""), IsFavorite, PLUGIN_PATH + Params, Item['Name'].replace('"', "'"), "window", 10025),))
