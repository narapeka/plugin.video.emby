from helper import utils, copy
from . import common, genre, tag, studio, person


class Movies:
    def __init__(self, Library, SQLs):
        self.Library = Library
        self.SQLs = SQLs
        self.GenreObject = genre.Genre(Library, SQLs)
        self.TagObject = tag.Tag(Library, SQLs)
        self.StudioObject = studio.Studio(Library, SQLs)
        self.PersonObject = person.Person(Library, SQLs)

    def update_SQLs(self, SQLs): # When paused, databases are closed and re-opened -> Update database
        self.SQLs = SQLs
        self.GenreObject.update_SQLs(SQLs)
        self.TagObject.update_SQLs(SQLs)
        self.StudioObject.update_SQLs(SQLs)
        self.PersonObject.update_SQLs(SQLs)

    def change(self, Item, IncrementalSync):
        if not common.verify_content(Item, "movie"):
            return False

        if not common.load_ExistingItem(Item, self.Library, self.SQLs["emby"], "Movie"):
            return False

        # Rebuild only when the version members or their ownership have changed.
        isMultiVersion = False
        Item["KodiSetId"] = None
        VersionUpdates = {}

        if Item['UpdateItem']:
            MultiVersionsFound = self.SQLs["emby"].get_movieversions(Item['Id'])

            if len(MultiVersionsFound) > 1:
                VersionUpdates = self.get_version_updates(Item, MultiVersionsFound)

            if len(MultiVersionsFound) > 1 and not VersionUpdates:
                isMultiVersion = True
                Item['IsFavorite'] = Item['EmbyFavourite']
                LastPlayedTicksCompare = 0

                for MultiVersionFound in MultiVersionsFound:
                    Found, timeInSeconds, playCount, lastPlayed = self.SQLs["video"].get_Progress(MultiVersionFound[1])

                    if lastPlayed:
                        LastPlayedTicks = utils.get_unix_ticks(lastPlayed)
                    else:
                        LastPlayedTicks = 0

                    if Found and LastPlayedTicks > LastPlayedTicksCompare:
                        LastPlayedTicksCompare = LastPlayedTicks
                        Item.update({'KodiPlayCount': playCount, 'KodiLastPlayedDate': lastPlayed, 'KodiPlaybackPositionTicks': timeInSeconds})

                    if not Item["KodiSetId"]:
                        Item["KodiSetId"] = self.SQLs["video"].get_setId(MultiVersionFound[2])

                for MultiVersionFound in MultiVersionsFound:
                    self.remove({'KodiFileId': MultiVersionFound[1], 'KodiItemId': MultiVersionFound[2], 'Id': MultiVersionFound[0], 'KodiPathId': MultiVersionFound[3], 'LibraryId': Item['LibraryId']}, False)

        common.set_RunTimeTicks(Item)
        common.set_streams(Item)
        Item['KodiRunTimeTicks'] = Item['MediaSources'][0]['KodiRunTimeTicks'] or Item['KodiRunTimeTicks']
        common.set_chapters(Item, self.Library.ServerData['ServerId'])
        common.set_common(Item, self.Library.ServerData['ServerId'], False, IncrementalSync)

        TmdbId = next((str(Value).strip() for Provider, Value in Item['ProviderIds'].items()
                       if Provider.lower() == "tmdb"), "")
        Item['TmdbId'] = str(int(TmdbId)) if TmdbId.isascii() and TmdbId.isdecimal() and int(TmdbId) > 0 else None

        Item['TagItems'].append({"LibraryId": Item["LibraryId"], "Type": "Tag", "Id": f"{utils.MappingIds['Tag']}00{Item['LibraryId']}", "Name": Item['LibraryName'], "Memo": "library"})
        common.set_MetaItems(Item, self.SQLs, self.GenreObject, self.Library, "Genre", "GenreItems", "", IncrementalSync, Item["LibraryId"])
        common.set_MetaItems(Item, self.SQLs, self.StudioObject, self.Library, "Studio", "Studios", "", IncrementalSync, Item["LibraryId"])
        common.set_MetaItems(Item, self.SQLs, self.TagObject, self.Library, "Tag", 'TagItems', "", IncrementalSync, Item["LibraryId"])
        PersonMappings = {}
        common.set_people(Item, self.SQLs, self.PersonObject, self.Library,
                          IncrementalSync, PersonMappings)
        self.SQLs["emby"].add_streamdata(Item['Id'], Item['MediaSources'])

        if Item['UpdateItem'] and not isMultiVersion:
            if VersionUpdates:
                common.delete_ContentItemMetadata(Item['KodiItemId'], self.SQLs, "movie", False)
            else:
                common.delete_ContentItemReferences(Item['KodiItemId'], Item['KodiFileId'], self.SQLs, "movie", False, Item['MediaSources'][0]['KodiStreams']['Subtitle'] or Item['MediaSources'][0]['KodiStreams']['Audio'] or Item['MediaSources'][0]['KodiStreams']['Video'])
            common.set_path_filename(Item, self.Library.ServerData['ServerId'], None)
            common.set_multipart(Item, self.Library)
        else:
            Item['KodiItemId'] = self.SQLs["video"].create_movie_entry()
            Item['KodiFileId'] = self.SQLs["video"].create_entry_file()
            common.set_path_filename(Item, self.Library.ServerData['ServerId'], None)
            common.set_multipart(Item, self.Library)
            Item['KodiPathId'] = self.SQLs['video'].get_add_path(Item['KodiPath'], "movies")

        common.set_VideoCommon(Item['KodiItemId'], Item['KodiFileId'], Item, self.SQLs, "movie", PreserveFileState=bool(VersionUpdates))
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
        Item['KodiUniqueId'] = self.SQLs["video"].add_uniqueids(Item['KodiItemId'], Item['ProviderIds'], "movie", 'tmdb')
        Item['KodiRatingId'] = self.SQLs["video"].add_ratings(Item['KodiItemId'], "movie", "default", Item['CommunityRating'])

        if not Item['ProductionLocations']:
            Item['ProductionLocations'].append(None)

        if Item['UpdateItem'] and not isMultiVersion:
            self.SQLs["video"].update_movie(Item['KodiItemId'], Item['KodiFileId'], Item['Name'], Item['Overview'], Item['ShortOverview'], Item['Tagline'], Item['KodiRatingId'], Item['Writers'], Item['KodiArtwork']['poster'], Item['KodiUniqueId'], Item['SortName'], Item['KodiRunTimeTicks'], Item['OfficialRating'], Item['Genre'], Item['Directors'], Item['OriginalTitle'], Item['Studio'], None, Item['KodiArtwork']['fanart'].get('fanart', None), Item['ProductionLocations'][0], Item['KodiPremiereDate'], None, Item['KodiFilename'], Item['KodiStackedFilename'], Item['KodiDateCreated'], Item['MediaSources'][0]['Name'], Item['KodiPathId'], Item['KodiPath'], Item['KodiFullPath'], PreserveVersions=bool(VersionUpdates))
            self.SQLs["emby"].update_reference_movie(Item['Id'], Item['PresentationUniqueKey'], Item['LibraryId'], Item['TmdbId'])
            if not VersionUpdates:
                self.SQLs["video"].fill_resume_bookmark_duration(Item['KodiFileId'], Item['KodiRunTimeTicks'])
        else:
            self.SQLs["video"].add_movie(Item['KodiItemId'], Item['KodiFileId'], Item['Name'], Item['Overview'], Item['ShortOverview'], Item['Tagline'], Item['KodiRatingId'], Item['Writers'], Item['KodiArtwork']['poster'], Item['KodiUniqueId'], Item['SortName'], Item['KodiRunTimeTicks'], Item['OfficialRating'], Item['Genre'], Item['Directors'], Item['OriginalTitle'], Item['Studio'], None, Item['KodiArtwork']['fanart'].get('fanart', None), Item['ProductionLocations'][0], Item['KodiFullPath'], Item['KodiPathId'], Item['KodiPremiereDate'], Item['KodiFilename'], Item['KodiDateCreated'], Item["KodiSetId"], Item['KodiStackedFilename'], Item['MediaSources'][0]['Name'])
            self.SQLs["emby"].add_reference_movie(Item['Id'], Item['LibraryId'], Item['KodiItemId'], Item['KodiFileId'], Item['PresentationUniqueKey'], Item['Path'], Item['KodiPathId'], Item['TmdbId'])

        common.update_boxsets(IncrementalSync, Item['ParentId'], Item['LibraryId'], self.SQLs, self.Library) # Update Boxset
        if VersionUpdates:
            self.update_versions(Item, VersionUpdates)
        else:
            common.add_multiversion(Item, "Movie", self.Library, self.SQLs, None, None)

        # Update userdata
        if isMultiVersion:
            self.userdata(Item, IncrementalSync, True, RestorePlaystate='KodiPlayCount' in Item)

        return not Item['UpdateItem']

    def get_version_updates(self, Item, Versions):
        # Match stable server identities before add_streamdata replaces the cached sources.
        if len(Item['MediaSources']) != len(Versions) or not all('ItemId' in Source for Source in Item['MediaSources']):
            return {}

        CachedSources = self.SQLs["emby"].get_mediasource(Item['Id'])
        if {(Source['Id'], Source['Path']) for Source in Item['MediaSources']} != {(Source['MediaSourceId'], Source['Path']) for Source in CachedSources.values()}:
            return {}

        VersionsById = {str(Version[0]): Version for Version in Versions}
        if {str(Source['ItemId']) for Source in Item['MediaSources']} != set(VersionsById):
            return {}

        if {Version[1] for Version in Versions} != self.SQLs["video"].get_movieversion_fileids(Item['KodiItemId']):
            return {}

        VersionUpdates = {}
        for Source in Item['MediaSources']:
            EmbyId = str(Source['ItemId'])
            Reference = self.SQLs["emby"].get_item_by_id(EmbyId, "Movie")
            LibraryIds = self.SQLs["emby"].get_LibraryIds_by_EmbyId(EmbyId)
            SourcePath = Item['Path'] if Source['Type'] == "Default" else Source['Path']
            if Reference[5] != SourcePath or str(Item['LibraryId']) not in {str(Library[0]) for Library in LibraryIds}:
                return {}

            if Source['Type'] == "Default" and EmbyId != str(Item['Id']):
                return {}

            VersionUpdates[Source['Id']] = VersionsById[EmbyId]

        return VersionUpdates

    def update_versions(self, Item, VersionUpdates):
        for Source in Item['MediaSources']:
            EmbyId, KodiFileId, KodiItemId, KodiPathId = VersionUpdates[Source['Id']]
            if Source['Type'] != "Default":
                VersionItem = copy.Object(Item)
                VersionItem.update({'KodiFileId': KodiFileId, 'KodiPathId': KodiPathId})
                common.set_path_filename(VersionItem, self.Library.ServerData['ServerId'], Source)
                self.SQLs["video"].update_movie_version(KodiItemId, KodiFileId, KodiPathId, VersionItem['KodiPath'], VersionItem['KodiFilename'], VersionItem['KodiDateCreated'], VersionItem['KodiStackedFilename'], Source['Name'])
                self.SQLs["emby"].update_reference_movie(EmbyId, Item['PresentationUniqueKey'], Item['LibraryId'], Item['TmdbId'])

            self.SQLs["video"].common_db.delete_artwork(KodiFileId, "videoversion")
            self.SQLs["video"].common_db.add_artwork(Item['KodiArtwork'], KodiFileId, "videoversion")
            self.SQLs["video"].add_missing_streams(KodiFileId, Source)
            if Item.get('PartCount', 1) < 2:
                self.SQLs["video"].fill_resume_bookmark_duration(KodiFileId, Source['KodiRunTimeTicks'])

    # This updates: Favorite, LastPlayedDate, Playcount, PlaybackPositionTicks
    def userdata(self, Item, IncrementalSync, UpdateKodiFavorite, *, RestorePlaystate=False):
        if not common.verify_KodiIds(Item, IncrementalSync, True):
            return False

        Update = False
        common.set_playstate(Item)
        if common.set_Favorite(Item):
            self.SQLs["video"].set_Favorite_Tag(Item['IsFavorite'], Item['KodiItemId'], "movie")
            self.SQLs["emby"].update_favourite(Item['IsFavorite'], Item['Id'], "Movie")
            if UpdateKodiFavorite:
                self.set_favorite(Item['IsFavorite'], Item)

        if RestorePlaystate:
            Playstate = {'playcount': Item['KodiPlayCount'], 'date_played': Item['KodiLastPlayedDate'], 'Progress': Item['KodiPlaybackPositionTicks']}
        else:
            Playstate = common.get_playstate_updates(Item)
        if not Playstate:
            return False

        if 'Progress' in Playstate and utils.MovieResumeOwnerEnabled:
            UserId = self.Library.ServerData['UserId']
            PendingSession = self.Library.MovieResumeSession
            CheckOwner = (IncrementalSync or (PendingSession and PendingSession['PendingTmdbId'])
                          or self.SQLs["emby"].has_movie_resume_owners(UserId))
            Owner = self.SQLs["emby"].get_movie_resume_owner(UserId, Item['Id']) if CheckOwner else None
            if Owner:
                TmdbId, KodiId, OwnerEmbyId, OwnerKodiId, _ = Owner
                Session = self.Library.MovieResumeSession
                PendingSwitch = Session and Session['PendingTmdbId'] == TmdbId
                UpdateResume = not PendingSwitch and (not OwnerKodiId or OwnerKodiId == KodiId)
                if not UpdateResume:
                    del Playstate['Progress']
                elif (OwnerEmbyId == int(Item['Id']) and not Playstate['Progress']
                      and (Item.get('UserData') or Item).get('PlaybackPositionTicks') == 0
                      and (not Session or Session['EmbyId'] != OwnerEmbyId)):
                    self.SQLs["emby"].clear_movie_resume_owner(UserId, Item['Id'])

        if not Playstate:
            return False

        for KodiFileId, Runtime in self.SQLs["video"].get_movie_bookmark_data(Item['KodiItemId'], Playstate.get('Progress')):
            if self.SQLs["video"].update_bookmark_playstate(KodiFileId, Runtime=Runtime, **Playstate):
                Update = True

        return Update

    def remove(self, Item, IncrementalSync):
        if not common.verify_KodiIds(Item, IncrementalSync, True):
            return

        if common.delete_ContentItem(Item['KodiItemId'], Item['KodiFileId'], Item, self.SQLs, "movie", "Movie"):
            self.set_favorite(False, Item)
            self.SQLs["video"].delete_movie(Item['KodiItemId'], Item['KodiFileId'])

            common.update_multiversion(self.SQLs["emby"], "Movie", Item['Id'], Item['LibraryId'], Item.get('PresentationUniqueKey', ''))
        else:
            LibrarySyncedName = self.Library.LibrarySyncedNames[Item['LibraryId']]
            self.SQLs["video"].delete_library_links_tags(Item['KodiItemId'], "movie", LibrarySyncedName)


    def set_favorite(self, IsFavorite, Item):
        common.validate_FavoriteImage(Item)

        if IsFavorite and not Item['KodiArtwork']['favourite'] or "Name" not in Item or "KodiFullPath" not in Item:
            Item['KodiFullPath'], Item['KodiArtwork']['favourite'], Item['Name'] = self.SQLs["video"].get_favoriteData(Item['KodiFileId'], Item['KodiItemId'], "movie")

        utils.FavoriteQueue.put((((Item['KodiArtwork']['favourite'] or ""), IsFavorite, Item['KodiFullPath'], Item['Name'].replace('"', "'"), "media", 0),))
