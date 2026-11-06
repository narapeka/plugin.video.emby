from helper import utils
from . import common, series, season, genre, studio, person


class Episode:
    def __init__(self, Library, SQLs, SeasonObject=None, SeriesObject=None):
        self.Library = Library
        self.SQLs = SQLs

        if SeriesObject:
            self.SeriesObject = SeriesObject
        else:
            self.SeriesObject = series.Series(Library, SQLs)

        if SeasonObject:
            self.SeasonObject = SeasonObject
        else:
            self.SeasonObject = season.Season(Library, SQLs)

        self.GenreObject = genre.Genre(Library, SQLs)
        self.StudioObject = studio.Studio(Library, SQLs)
        self.PersonObject = person.Person(Library, SQLs)

    def update_SQLs(self, SQLs): # When paused, databases are closed and re-opened -> Update database
        self.SQLs = SQLs
        self.SeriesObject.update_SQLs(self.SQLs)
        self.SeasonObject.update_SQLs(self.SQLs)
        self.GenreObject.update_SQLs(self.SQLs)
        self.StudioObject.update_SQLs(self.SQLs)
        self.PersonObject.update_SQLs(self.SQLs)

    def change(self, Item, IncrementalSync):
        if not common.verify_content(Item, "episode"):
            return False

        if not common.load_ExistingItem(Item, self.Library, self.SQLs["emby"], "Episode"):
            return False

        common.set_RunTimeTicks(Item)
        common.set_streams(Item)
        common.set_chapters(Item, self.Library.ServerData['ServerId'])
        common.set_MetaItems(Item, self.SQLs, self.GenreObject, self.Library, "Genre", "GenreItems", "", IncrementalSync, Item['LibraryId'])
        common.set_MetaItems(Item, self.SQLs, self.StudioObject, self.Library, "Studio", "Studios", "", IncrementalSync, Item['LibraryId'])
        self.SQLs["emby"].add_streamdata(Item['Id'], Item['MediaSources'])
        PersonMappings = {}
        common.set_people(Item, self.SQLs, self.PersonObject, self.Library,
                          IncrementalSync, PersonMappings)
        common.set_common(Item, self.Library.ServerData['ServerId'], False, IncrementalSync)
        ExistingParents = {}
        common.set_ItemsDependencies(Item, self.SQLs, self.SeriesObject, self.Library,
                                    "Series", IncrementalSync, Item['LibraryId'],
                                    ExistingParents=ExistingParents)
        common.set_ItemsDependencies(Item, self.SQLs, self.SeasonObject, self.Library,
                                    "Season", IncrementalSync, Item['LibraryId'],
                                    ExistingParents=ExistingParents)

        if "Series" in ExistingParents and "Season" in ExistingParents:
            Item['KodiParentId'] = ExistingParents["Series"][1]
            KodiSeasonId = ExistingParents["Season"][1]
        else:
            PersonMappings.clear()
            Item['KodiParentId'] = self.SQLs["emby"].get_KodiId_by_EmbyId_EmbyType(
                Item['SeriesId'], "Series")
            KodiSeasonId = self.SQLs["emby"].get_KodiId_by_EmbyId_EmbyType(
                Item['SeasonId'], "Season")
        SeasonNumber = self.SQLs["video"].get_season_number(KodiSeasonId)

        # Check if ParentIndexNumber (Season number) not in Kodi database
        if not Item['ParentIndexNumber'] and Item['ParentIndexNumber'] != 0:
            Item['ParentIndexNumber'] = SeasonNumber

        if Item['UpdateItem']:
            common.delete_ContentItemReferences(Item['KodiItemId'], Item['KodiFileId'], self.SQLs, "episode", False, Item['MediaSources'][0]['KodiStreams']['Subtitle'] or Item['MediaSources'][0]['KodiStreams']['Audio'] or Item['MediaSources'][0]['KodiStreams']['Video'])
            common.set_path_filename(Item, self.Library.ServerData['ServerId'], None)
            common.set_multipart(Item, self.Library)
        else:
            Item['KodiItemId'] = self.SQLs["video"].create_entry_episode()
            Item['KodiFileId'] = self.SQLs["video"].create_entry_file()
            common.set_path_filename(Item, self.Library.ServerData['ServerId'], None)
            common.set_multipart(Item, self.Library)
            Item['KodiPathId'] = self.SQLs["video"].get_add_path(Item['KodiPath'], None)

        common.set_VideoCommon(Item['KodiItemId'], Item['KodiFileId'], Item, self.SQLs, "episode")
        common.set_Genre_links(Item['KodiItemId'], self.SQLs, "episode", Item["GenreItems"])
        common.set_Studio_links(Item['KodiItemId'], self.SQLs, "episode", Item["Studios"])
        common.set_Actor_links(Item['KodiItemId'], self.SQLs, "episode", Item["CastItems"],
                               PersonMappings)
        common.set_Writer_links(Item['KodiItemId'], self.SQLs, "episode", Item["WritersItems"],
                                PersonMappings)
        common.set_Director_links(Item['KodiItemId'], self.SQLs, "episode", Item["DirectorsItems"],
                                  PersonMappings)
        Item['KodiUniqueId'] = self.SQLs["video"].add_uniqueids(Item['KodiItemId'], Item['ProviderIds'], "episode", 'tvdb')
        Item['KodiRatingId'] = self.SQLs["video"].add_ratings(Item['KodiItemId'], "episode", "default", Item['CommunityRating'])

        if Item['UpdateItem']:
            self.SQLs["video"].update_episode(Item['KodiItemId'], Item['KodiFileId'], Item['Name'], Item['Overview'], Item['KodiRatingId'], Item['Writers'], Item['KodiPremiereDate'], Item['KodiArtwork']['thumb'], Item['KodiRunTimeTicks'], Item['Directors'], Item['ParentIndexNumber'], Item['IndexNumber'], Item['OriginalTitle'], Item['SortParentIndexNumber'], Item['SortIndexNumber'], Item['KodiPath'], Item['KodiFilename'], Item['KodiPathId'], Item['KodiUniqueId'], Item['KodiParentId'], KodiSeasonId, Item['KodiStackedFilename'], Item['KodiDateCreated'], Item['KodiFullPath'])
            self.SQLs["emby"].update_reference_episode(Item['Id'], Item['KodiParentId'], Item['PresentationUniqueKey'], Item['LibraryId'])

        else:
            self.SQLs["video"].add_episode(Item['KodiItemId'], Item['KodiFileId'], Item['Name'], Item['Overview'], Item['KodiRatingId'], Item['Writers'], Item['KodiPremiereDate'], Item['KodiArtwork']['thumb'], Item['KodiRunTimeTicks'], Item['Directors'], Item['ParentIndexNumber'], Item['IndexNumber'], Item['OriginalTitle'], Item['SortParentIndexNumber'], Item['SortIndexNumber'], Item['KodiFullPath'], Item['KodiPathId'], Item['KodiUniqueId'], Item['KodiParentId'], KodiSeasonId, Item['KodiFilename'], Item['KodiDateCreated'], Item['KodiStackedFilename'])
            self.SQLs["emby"].add_reference_episode(Item['Id'], Item['LibraryId'], Item['KodiItemId'], Item['KodiFileId'], Item['KodiParentId'], Item['PresentationUniqueKey'], Item['Path'], Item['KodiPathId'])

        common.add_multiversion(Item, "Episode", self.Library, self.SQLs, None, None)
        return not Item['UpdateItem']

    # This updates: Favorite, LastPlayedDate, Playcount, PlaybackPositionTicks
    def userdata(self, Item, IncrementalSync, UpdateKodiFavorite):
        if not common.verify_KodiIds(Item, IncrementalSync, True):
            return False

        if common.set_Favorite(Item):
            if UpdateKodiFavorite:
                self.set_favorite(Item['IsFavorite'], Item)
            self.SQLs["emby"].update_favourite(Item['IsFavorite'], Item['Id'], "Episode")

        common.set_playstate(Item)
        common.set_RunTimeTicks(Item)
        return self.SQLs["video"].update_bookmark_playstate(Item['KodiFileId'], Runtime=Item['KodiRunTimeTicks'], **common.get_playstate_updates(Item))

    # Remove showid, fileid, pathid, emby reference.
    # There's no episodes left, delete show and any possible remaining seasons
    def remove(self, Item, IncrementalSync):
        KodiItemId = Item.get('KodiItemId', "")
        KodiFileId = Item.get('KodiFileId', "")

        if common.delete_ContentItem(KodiItemId, KodiFileId, Item, self.SQLs, "episode", "Episode"):
            self.set_favorite(False, Item)
            self.SQLs["video"].delete_episode(KodiItemId, KodiFileId)

            common.update_multiversion(self.SQLs["emby"], "Episode", Item['Id'], Item['LibraryId'], Item.get('PresentationUniqueKey', ''))

    def set_favorite(self, IsFavorite, Item):
        common.validate_FavoriteImage(Item)

        if IsFavorite and not Item['KodiArtwork']['favourite'] or "Name" not in Item or "KodiFullPath" not in Item:
            Item['KodiFullPath'], Item['KodiArtwork']['favourite'], Item['Name'] = self.SQLs["video"].get_favoriteData(Item['KodiFileId'], Item['KodiItemId'], "episode")

        utils.FavoriteQueue.put((((Item['KodiArtwork']['favourite'] or ""), IsFavorite, Item['KodiFullPath'], Item['Name'].replace('"', "'"), "media", 0),))
