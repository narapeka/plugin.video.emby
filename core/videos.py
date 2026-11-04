from helper import utils
from . import common, genre, tag, studio, person


class Videos:
    def __init__(self, Library, SQLs):
        self.Library = Library
        self.SQLs = SQLs
        self.GenreObject = genre.Genre(Library, SQLs)
        self.TagObject = tag.Tag(Library, SQLs)
        self.StudioObject = studio.Studio(Library, SQLs)
        self.PersonObject = person.Person(Library, SQLs)

    def update_SQLs(self, SQLs): # When paused, databases are closed and re-opened -> Update database
        self.SQLs = SQLs
        self.GenreObject.update_SQLs(self.SQLs)
        self.TagObject.update_SQLs(self.SQLs)
        self.StudioObject.update_SQLs(self.SQLs)
        self.PersonObject.update_SQLs(self.SQLs)

    def change(self, Item, IncrementalSync):
        if not common.verify_content(Item, "video"):
            return False

        if not common.load_ExistingItem(Item, self.Library, self.SQLs["emby"], "Video"):
            return False


        # ungroup versions
        if Item['UpdateItem']:
            Movieversions = self.SQLs["emby"].get_movieversions(Item['Id'])

            if len(Movieversions) > 1:
                for Movieversion in Movieversions:
                    DelteItem = {'KodiFileId': Movieversion[1], 'KodiItemId': Movieversion[2], 'Id': Movieversion[0], 'KodiPathId': Movieversion[3], 'LibraryId': Item['LibraryId']}
                    self.remove(DelteItem, False)

                Item['UpdateItem'] =  False

        common.set_RunTimeTicks(Item)
        common.set_streams(Item)
        common.set_common(Item, self.Library.ServerData['ServerId'], False, IncrementalSync)
        common.set_chapters(Item, self.Library.ServerData['ServerId'])
        Item['TagItems'].append({"LibraryId": Item["LibraryId"], "Type": "Tag", "Id": f"{utils.MappingIds['Tag']}00{Item['LibraryId']}", "Name": Item['LibraryName'], "Memo": "library"})
        common.set_MetaItems(Item, self.SQLs, self.GenreObject, self.Library, "Genre", "GenreItems", "", IncrementalSync, Item["LibraryId"])
        common.set_MetaItems(Item, self.SQLs, self.StudioObject, self.Library, "Studio", "Studios", "", IncrementalSync, Item["LibraryId"])
        common.set_MetaItems(Item, self.SQLs, self.TagObject, self.Library, "Tag", 'TagItems', "", IncrementalSync, Item["LibraryId"])
        PersonMappings = {}
        common.set_people(Item, self.SQLs, self.PersonObject, self.Library,
                          IncrementalSync, PersonMappings)
        self.SQLs["emby"].add_streamdata(Item['Id'], Item['MediaSources'])

        if Item['UpdateItem']:
            common.delete_ContentItemReferences(Item['KodiItemId'], Item['KodiFileId'], self.SQLs, "movie", False, Item['MediaSources'][0]['KodiStreams']['Subtitle'] or Item['MediaSources'][0]['KodiStreams']['Audio'] or Item['MediaSources'][0]['KodiStreams']['Video'])
            common.set_path_filename(Item, self.Library.ServerData['ServerId'], None)
            common.set_multipart(Item, self.Library)
        else:
            Item['KodiItemId'] = self.SQLs["video"].create_movie_entry()
            Item['KodiFileId'] = self.SQLs["video"].create_entry_file()
            common.set_path_filename(Item, self.Library.ServerData['ServerId'], None)
            common.set_multipart(Item, self.Library)
            Item['KodiPathId'] = self.SQLs['video'].get_add_path(Item['KodiPath'], "movies")

        common.set_VideoCommon(Item['KodiItemId'], Item['KodiFileId'], Item, self.SQLs, "movie")
        common.set_Genre_links(Item['KodiItemId'], self.SQLs, "movie", Item["GenreItems"])
        common.set_Studio_links(Item['KodiItemId'], self.SQLs, "movie", Item["Studios"])
        common.set_Tag_links(Item['KodiItemId'], self.SQLs, "movie", Item["TagItems"])
        common.set_Actor_links(Item['KodiItemId'], self.SQLs, "movie", Item["CastItems"],
                               PersonMappings)
        common.set_Writer_links(Item['KodiItemId'], self.SQLs, "movie", Item["WritersItems"],
                                PersonMappings)
        common.set_Director_links(Item['KodiItemId'], self.SQLs, "movie", Item["DirectorsItems"],
                                  PersonMappings)
        self.SQLs["video"].common_db.add_artwork(Item['KodiArtwork'], Item['KodiFileId'], "videoversion")
        Item['KodiUniqueId'] = self.SQLs["video"].add_uniqueids(Item['KodiItemId'], Item['ProviderIds'], "movie", 'imdb')
        Item['KodiRatingId'] = self.SQLs["video"].add_ratings(Item['KodiItemId'], "movie", "default", Item['CommunityRating'])

        if not Item['ProductionLocations']:
            Item['ProductionLocations'].append("")

        if Item['UpdateItem']:
            self.SQLs["video"].update_movie(Item['KodiItemId'], Item['KodiFileId'], Item['Name'], Item['Overview'], Item['ShortOverview'], Item['Tagline'], Item['KodiRatingId'], Item['Writers'], Item['KodiArtwork']['poster'], Item['KodiUniqueId'], Item['SortName'], Item['KodiRunTimeTicks'], Item['OfficialRating'], Item['Genre'], Item['Directors'], Item['OriginalTitle'], Item['Studio'], None, Item['KodiArtwork']['fanart'].get('fanart', None), Item['ProductionLocations'][0], Item['KodiPremiereDate'], None, Item['KodiFilename'], Item['KodiStackedFilename'], Item['KodiDateCreated'], Item['MediaSources'][0]['Name'], Item['KodiPathId'], Item['KodiPath'], Item['KodiFullPath'])
            self.SQLs["emby"].update_reference_video(Item['Id'], Item['ParentId'], Item['PresentationUniqueKey'], Item['LibraryId'])

        else: # new item
            self.SQLs["video"].add_movie(Item['KodiItemId'], Item['KodiFileId'], Item['Name'], Item['Overview'], Item['ShortOverview'], Item['Tagline'], Item['KodiRatingId'], Item['Writers'], Item['KodiArtwork']['poster'], Item['KodiUniqueId'], Item['SortName'], Item['KodiRunTimeTicks'], Item['OfficialRating'], Item['Genre'], Item['Directors'], Item['OriginalTitle'], Item['Studio'], None, Item['KodiArtwork']['fanart'].get('fanart', None), Item['ProductionLocations'][0], Item['KodiFullPath'], Item['KodiPathId'], Item['KodiPremiereDate'], Item['KodiFilename'], Item['KodiDateCreated'], None, Item['KodiStackedFilename'], Item['MediaSources'][0]['Name'])
            self.SQLs["emby"].add_reference_video(Item['Id'], Item['LibraryId'], Item['KodiItemId'], Item['KodiFileId'], Item['ParentId'], Item['PresentationUniqueKey'], Item['Path'], Item['KodiPathId'])

        common.update_boxsets(IncrementalSync, Item['ParentId'], Item['LibraryId'], self.SQLs, self.Library) # Update Boxset
        common.add_multiversion(Item, "Video", self.Library, self.SQLs, None, None)
        return not Item['UpdateItem']

    # This updates: Favorite, LastPlayedDate, Playcount, PlaybackPositionTicks
    def userdata(self, Item, IncrementalSync, UpdateKodiFavorite):
        if not common.verify_KodiIds(Item, IncrementalSync, False):
            return False

        common.set_Favorite(Item)
        Update = False
        common.set_playstate(Item)
        common.set_RunTimeTicks(Item)

        if not self.SQLs["video"]: # skip LibraryId 999999998 / shared
            return False

        self.SQLs["emby"].update_favourite(Item['IsFavorite'], Item['Id'], "Video")

        if UpdateKodiFavorite:
            self.set_favorite(Item['IsFavorite'], Item)

        for KodiFileId in self.SQLs["video"].get_KodiFileId_by_videoversion(Item['KodiItemId'], "movie"):
            if self.SQLs["video"].update_bookmark_playstate(KodiFileId[0], Item['KodiPlayCount'], Item['KodiLastPlayedDate'], Item['KodiPlaybackPositionTicks'], Item['KodiRunTimeTicks']):
                Update = True

        return Update

    def remove(self, Item, IncrementalSync):
        if common.delete_ContentItem(Item['KodiItemId'], Item['KodiFileId'], Item, self.SQLs, "movie", "Video"):
            self.set_favorite(False, Item)
            self.SQLs["video"].delete_movie(Item['KodiItemId'], Item['KodiFileId'])

            common.update_multiversion(self.SQLs["emby"], "Video", Item['Id'], Item['LibraryId'], Item.get('PresentationUniqueKey', ''))
        else:
            LibrarySyncedName = self.Library.LibrarySyncedNames[Item['LibraryId']]
            self.SQLs["video"].delete_library_links_tags(Item['KodiItemId'], "movie", LibrarySyncedName)

    def set_favorite(self, IsFavorite, Item):
        common.validate_FavoriteImage(Item)

        if IsFavorite and not Item['KodiArtwork']['favourite'] or "Name" not in Item or "KodiFullPath" not in Item:
            Item['KodiFullPath'], Item['KodiArtwork']['favourite'], Item['Name'] = self.SQLs["video"].get_favoriteData(Item['KodiFileId'], Item['KodiItemId'], "movie")

        utils.FavoriteQueue.put((((Item['KodiArtwork']['favourite'] or ""), IsFavorite, Item['KodiFullPath'], Item['Name'].replace('"', "'"), "media", 0),))
