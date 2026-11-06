from urllib.parse import urlencode

from emby.views import PLUGIN_PATH
from helper import utils, paging
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
        ItemFilename = utils.valid_Filename(f"{self.Library.ServerData['ServerId']}_{Item['Id']}")
        TrackNumber = {"Audio": 0, "MusicVideo": 0}
        M3UPlaylist = {"Audio": "", "Video": ""}
        KodiPlaylistId = {"Audio": "", "Video": ""}
        EmbyLinkedId = {"Audio": [], "Video": [], "Movie": [], "Episode": [], "MusicVideo": []}
        VideoOrder = []
        # Fetch every page before altering existing files or membership.
        Query = {"PlaylistItems": True}
        if Item.get('MediaType') == "Audio":
            Query['Limit'] = paging.get_limit("Audio")
        PlaylistItems = list(self.Library.API.get_Items(Item['Id'], tuple(EmbyLinkedId), False, Query, "", None, True))
        PreviousMembers = self.synced_members(Item['EmbyLinkedId'])
        PreviousAudio = set(filter(None, (Item['EmbyLinkedId'] or "").partition(";")[0].split(",")))

        for PlaylistItem in PlaylistItems:
            PlaylistItemType = PlaylistItem['Type']
            PlaylistItemId = str(PlaylistItem['Id'])
            EmbyLinkedId[PlaylistItemType].append(PlaylistItemId)
            if PlaylistItemType != "Audio":
                VideoOrder.append(PlaylistItemId)
            if PlaylistItemType not in ("Audio", "MusicVideo"):
                continue

            common.set_RunTimeTicks(PlaylistItem)
            common.set_streams(PlaylistItem)
            PlaylistItem['ParentIndexNumber'] = 0
            PlaylistItem['LibraryId'] = Item['LibraryId']
            common.set_common(PlaylistItem, self.Library.ServerData['ServerId'], True, IncrementalSync)

            if PlaylistItemType == "Audio":
                common.set_path_filename(PlaylistItem, self.Library.ServerData['ServerId'], None)
                TrackNumber["Audio"] += 1
                PlaylistItem['IndexNumber'] = TrackNumber["Audio"]
                self.AudioObject.change(PlaylistItem, IncrementalSync, Item['Id'])

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
            self.SQLs["emby"].write_playlist_file(f'{utils.PlaylistPathMusic}{KodiPlaylistId["Audio"]}.m3u', M3UData.encode("utf-8"))

        if M3UPlaylist["Video"]:
            M3UData = f'#EXTCPlayListM3U::M3U\n{M3UPlaylist["Video"]}'
            KodiPlaylistId["Video"] = f"emby_{ItemFilename}_video"
            self.SQLs["emby"].write_playlist_file(f'{utils.PlaylistPathVideo}{KodiPlaylistId["Video"]}.m3u', M3UData.encode("utf-8"))

        Item['KodiItemId'] = f'{KodiPlaylistId["Audio"]};{KodiPlaylistId["Video"]}'
        Item['EmbyLinkedId'] = ";".join(",".join(Group) for Group in (*EmbyLinkedId.values(), VideoOrder))
        self.SQLs["emby"].add_reference_playlist(Item['Id'], Item['LibraryId'], Item['KodiItemId'], Item['KodiArtwork']['favourite'], Item['EmbyLinkedId'], Item['Name'])
        self.Library.Views.update_playlist_nodes(Item['Id'], Item['Name'], Item['KodiArtwork']['favourite'], Item['EmbyLinkedId'])

        CurrentMembers = self.synced_members(Item['EmbyLinkedId'])
        AddedMembers = CurrentMembers - PreviousMembers
        if AddedMembers:
            self.SQLs["emby"].cancel_playlist_member_removals(Item['LibraryId'], AddedMembers)
        self.remove_audio_tags(PreviousAudio.difference(EmbyLinkedId["Audio"]), Item['LibraryId'], Item['Id'])
        self.remove_unused_members(PreviousMembers - CurrentMembers, Item['LibraryId'])

        # Keep old reference targets until the enclosing sync transaction commits.
        if not M3UPlaylist["Audio"]:
            self.SQLs["emby"].queue_playlist_file_delete(Item['Id'], f"emby_{ItemFilename}_audio", f"{utils.PlaylistPathMusic}emby_{ItemFilename}_audio.m3u")
        if not M3UPlaylist["Video"]:
            self.SQLs["emby"].queue_playlist_file_delete(Item['Id'], f"emby_{ItemFilename}_video", f"{utils.PlaylistPathVideo}emby_{ItemFilename}_video.m3u")

        return False

    @staticmethod
    def synced_members(LinkedIds):
        Groups = (LinkedIds or ";;;;").split(";")
        return set(filter(None, (Groups[0] + "," + Groups[4]).split(",")))

    def remove_audio_tags(self, EmbyIds, LibraryId, PlaylistId):
        for EmbyId in EmbyIds:
            LibraryIds, KodiIds, _, _ = self.SQLs["emby"].get_KodiIds_LibraryIds_from_ContentItem(EmbyId, "Audio")
            for SongLibraryId, KodiId in zip(common.get_Ids_SingleContent(LibraryIds), common.get_Ids_SingleContent(KodiIds)):
                if SongLibraryId == LibraryId:
                    self.SQLs["music"].remove_song_tag(KodiId, f"EmbyPlaylistId-{PlaylistId}")

    def remove_unused_members(self, Members, LibraryId):
        if not Members:
            return
        for LinkedIds in self.SQLs["emby"].get_library_playlists(LibraryId):
            Members.difference_update(self.synced_members(LinkedIds))
        for EmbyId in Members:
            self.SQLs["emby"].add_RemoveItem(EmbyId, LibraryId)

    def remove(self, Item, IncrementalSync):
        if not common.verify_KodiIds(Item, IncrementalSync, False):
            return

        self.set_favorite(False, Item)
        self.Library.Views.delete_playlist_nodes(Item['Id'])
        KodiItemIds = Item['KodiItemId'].split(";")

        OwnedName = f"emby_{utils.valid_Filename(str(self.Library.ServerData['ServerId']) + '_' + str(Item['Id']))}"

        if KodiItemIds[1]: # Video
            TagId = f"{utils.MappingIds['Tag']}{Item['Id']}"
            TagKodiId = self.SQLs["emby"].get_KodiId_by_EmbyId_EmbyType(TagId, "Tag")
            self.TagObject.remove({'Id': TagId, 'KodiItemId': TagKodiId, "LibraryId": Item['LibraryId']}, IncrementalSync)

        LibraryIds = [(Item['LibraryId'],)] if Item['LibraryId'] else self.SQLs["emby"].get_LibraryIds_by_EmbyId(Item['Id'])
        self.SQLs["emby"].remove_item(Item['Id'], "Playlist", Item['LibraryId'])
        AudioMembers = set(filter(None, (Item['EmbyLinkedId'] or "").partition(";")[0].split(",")))
        for (LibraryId,) in LibraryIds:
            self.remove_audio_tags(AudioMembers, LibraryId, Item['Id'])
            self.remove_unused_members(self.synced_members(Item['EmbyLinkedId']), LibraryId)
        self.SQLs["emby"].queue_playlist_file_delete(Item['Id'], f"{OwnedName}_audio", f"{utils.PlaylistPathMusic}{OwnedName}_audio.m3u")
        self.SQLs["emby"].queue_playlist_file_delete(Item['Id'], f"{OwnedName}_video", f"{utils.PlaylistPathVideo}{OwnedName}_video.m3u")

    def userdata(self, Item, IncrementalSync, UpdateKodiFavorite):
        if not common.set_Favorite(Item):
            return False

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
