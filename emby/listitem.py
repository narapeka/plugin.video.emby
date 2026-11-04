import xbmc
import xbmcgui
from helper import utils
from core import common


def set_ListItem_from_Kodi_database(Item, Path, StartOffset=0.0):
    if 'ListItem' in Item: # Cached item
        return

    Item['KodiFullPath'] = ""

    if Path:
        Item['KodiFullPath'] = Path
    elif Item.get('KodiMetadataPathandfilename'):
        Item['KodiFullPath'] = Item['KodiMetadataPathandfilename']
    elif Item.get('KodiMetadataPath'):
        Item['KodiFullPath'] = Item['KodiMetadataPath']

    if Item['KodiFullPath']:
        MimeType, _ = utils.get_MimeType(Item['KodiFullPath'])
    else:
        MimeType = ""


    ListItem = xbmcgui.ListItem(label=Item['KodiMetadataTitle'], offscreen=True, path=Item['KodiFullPath'])

    if MimeType:
        ListItem.setMimeType(MimeType)
        Item['KodiMetadataProperties']['mimetype'] = MimeType

    if Item['KodiMetadataMediatype'] in ("episode", "movie", "musicvideo", "tvshow", "season", "set", "video"):
        if Item.get('KodiMetadataProductionLocation'):
            Item['KodiMetadataProductionLocations'] = Item['KodiMetadataProductionLocation'].split("/")

        if Item.get('KodiMetadataStudioName'):
            Item['KodiMetadataStudioNames'] = Item['KodiMetadataStudioName'].split("/")

        if Item.get('KodiMetadataWriter'):
            Item['KodiMetadataWriters'] = Item['KodiMetadataWriter'].split("/")

        if Item.get('KodiMetadataDirector'):
            Item['KodiMetadataDirectors'] = Item['KodiMetadataDirector'].split("/")

        InfoTags = ListItem.getVideoInfoTag()

        if Item.get('KodiMetadataDBID'):
            InfoTags.setDbId(int(Item['KodiMetadataDBID']))

        set_DateAdded(Item, InfoTags)
        set_UserRating(Item, InfoTags)
        set_TagLine(Item, InfoTags)
        set_PlotOutline(Item, InfoTags)
        set_Countries(Item, InfoTags)
        set_Mpaa(Item, InfoTags)
        set_OriginalTitle(Item, InfoTags)
        set_Plot(Item, InfoTags)
        set_SortTitle(Item, InfoTags)
        set_Studios(Item, InfoTags)
        set_Writers(Item, InfoTags)
        set_Directors(Item, InfoTags)
        set_SortSeason(Item, InfoTags)
        set_Season(Item, InfoTags, 'ParentIndexNumber')
        set_Episode(Item, InfoTags)
        set_SortEpisode(Item, InfoTags)
        set_TvShowTitle(Item, InfoTags)
        set_IMDBNumber(Item, InfoTags)
        set_Premiered(Item, InfoTags)
        set_ResumePoint(Item, InfoTags)
        set_Album(Item, InfoTags)
        set_TvShowStatus(Item, InfoTags)
        set_Artists(Item, InfoTags)
        set_RatingVideo(Item, InfoTags)
        set_SetOverview(Item, InfoTags)
        set_Set(Item, InfoTags)
        set_SetId(Item, InfoTags)
        set_VideoAssetTitle(Item, InfoTags)
        set_ShowLinks(Item, InfoTags)
        set_Tags(Item, InfoTags)
        set_UniqueIDs(Item, InfoTags)
        set_PlaycountVideo(Item, InfoTags)
        set_FilenameAndPath(Item, InfoTags)
        set_Path(Item, InfoTags)

        if Item.get('KodiMetadataTrack'):
            InfoTags.setTrackNumber(int(Item['KodiMetadataTrack']))

        if Item.get('KodiMetadataFirstaired'):
            InfoTags.setFirstAired(Item['KodiMetadataFirstaired'])

        if Item.get('KodiMetadataPeople'):
            People = ()

            for Person in Item['KodiMetadataPeople']:
                People += (xbmc.Actor(*Person),)

            InfoTags.setCast(People)

        if Item['KodiMetadataMediatype'] in ("tvshow", "season", "set"):
            ListItem.setContentLookup(False) # HLS streams needs content lookup
    elif Item['KodiMetadataMediatype'] in ("song", "artist", "album"):
        InfoTags = ListItem.getMusicInfoTag()

        InfoTags.setDbId(int(Item['KodiMetadataDBID']), Item['KodiMetadataMediatype'])

        set_RatingMusic(Item, InfoTags)

        if Item.get('KodiMetadataArtist'):
            InfoTags.setArtist(Item['KodiMetadataArtist'])

        set_AlbumArtist(Item, InfoTags)
        set_Comment(Item, InfoTags)
        set_Disc(Item, InfoTags)
        set_Track(Item, InfoTags)
        set_Album(Item, InfoTags)
        set_MusicBrainzReleaseGroupID(Item, InfoTags)
        set_SongVideoURL(Item, InfoTags)
        set_PlaycountAudio(Item, InfoTags)
        set_MusicBrainzArtistID(Item, InfoTags)
        set_MusicBrainzAlbumID(Item, InfoTags)
        set_MusicBrainzTrackID(Item, InfoTags)
        set_MusicBrainzAlbumArtistID(Item, InfoTags)
        ListItem.setContentLookup(False)

        if Item.get('KodiMetadataReleasedate'):
            InfoTags.setReleaseDate(Item['KodiMetadataReleasedate'])

        if Item.get('KodiMetadataPathandfilename'):
            InfoTags.setURL(Item['KodiMetadataPathandfilename'])
        elif Item.get('KodiMetadataPath'):
            InfoTags.setURL(Item['KodiMetadataPath'])

    # Common infotags
    if InfoTags:
        InfoTags.setTitle(Item['KodiMetadataTitle'])
        InfoTags.setMediaType(Item['KodiMetadataMediatype'])

        if Item.get('KodiMetadataGenre'):
            Item['KodiMetadataGenres'] = Item['KodiMetadataGenre'].split("/")

        set_Art(ListItem, Item['KodiMetadataArtwork'])
        set_Year(Item, InfoTags)
        set_LastPlayed(Item, InfoTags)
        set_Duration(Item, InfoTags)
        set_Genres(Item, InfoTags)

    if StartOffset:
        Item['KodiMetadataProperties']["StartOffset"] = StartOffset

    ListItem.setProperties(Item['KodiMetadataProperties'])

    Item.update({'KodiType': Item['KodiMetadataMediatype'], 'KodiId': int(Item['KodiMetadataDBID']), 'ListItem': ListItem, 'IsFolder': bool(Item['KodiMetadataProperties']['IsFolder'] == "true")})

def set_playback_listitem(Item, ServerId, StartOffset=0.0):
    """Build a playable Movie, Video, Episode, MusicVideo or Audio item."""
    if 'ListItem' in Item: # Cached item
        return

    Properties = {}

    if 'Name' in Item:
        Name = Item['Name']
    elif 'SeriesName' in Item: # {'ServerId': '2a38697ffc1b428b943aa1b6014e2263', 'PremiereDate': '2024-10-23T22:00:00.0000000Z', 'ProductionYear': 2024, 'IndexNumber': 2, 'ParentIndexNumber': 5, 'ProviderIds': {}, 'Type': 'Episode', 'SeriesName': 'Star Trek: Lower Decks', 'SeriesId': '58574', 'SeriesPrimaryImageTag': 'fb201a2139810a15d125dfea5e981f36', 'ParentThumbItemId': '58574', 'ParentThumbImageTag': '01e69ca501869a469606bc82bd94d300', 'LocationType': 'Virtual'}
        Name = Item['SeriesName']
    else:
        Name = "Unknown"

    if Item['Type'] == "Movie":
        common.set_RunTimeTicks(Item)
        common.set_playstate(Item)
        common.set_streams(Item)
        common.set_chapters(Item, ServerId)
        common.set_common(Item, ServerId, True, False)

    elif Item['Type'] == "Episode":
        common.set_RunTimeTicks(Item)
        common.set_playstate(Item)
        common.set_streams(Item)
        common.set_chapters(Item, ServerId)
        common.set_common(Item, ServerId, True, False)

    elif Item['Type'] == "MusicVideo":
        common.set_RunTimeTicks(Item)
        common.set_playstate(Item)
        common.set_streams(Item)
        common.set_chapters(Item, ServerId)
        common.set_common(Item, ServerId, True, False)
        common.set_TracksByMediasourceName(Item)

    elif Item['Type'] == "Video":
        common.set_RunTimeTicks(Item)
        common.set_playstate(Item)
        common.set_streams(Item)
        common.set_chapters(Item, ServerId)
        common.set_common(Item, ServerId, True, False)

    elif Item['Type'] == "Audio":
        common.set_streams(Item)
        common.set_RunTimeTicks(Item)
        common.set_playstate(Item)
        common.set_common(Item, ServerId, True, False)
        common.set_TracksByMediasourceName(Item)

    # Fake Id is necessary, otherwise Kodi does not report notifications via monitor.py
    if 'Id' in Item and Item['Id']:
        Item['KodiId'] = utils.set_EmbyId_ServerId_by_Fake_KodiId(Item['Id'], ServerId) # Maximum value is 2147483648

    # Set path
    if 'KodiFullPath' not in Item or not Item['KodiFullPath']:
        common.set_path_filename(Item, ServerId, None, True)


    # ListItem
    ListItem = xbmcgui.ListItem(label=Name, offscreen=True, path=Item['KodiFullPath'])
    Properties.update({'embyserverid': str(ServerId), 'embyid': str(Item.get('Id', ""))})
    InfoTags = None
    IsVideo = False

    if Item['Type'] == "Movie":
        InfoTags = ListItem.getVideoInfoTag()
        IsVideo = True
        InfoTags.setMediaType("movie")
        InfoTags.setTitle(Name)
        set_SortTitle(Item, InfoTags)
        set_OriginalTitle(Item, InfoTags)
        set_Plot(Item, InfoTags)
        set_PlotOutline(Item, InfoTags)
        set_DateAdded(Item, InfoTags)
        set_Year(Item, InfoTags)
        set_RatingVideo(Item, InfoTags)
        set_Mpaa(Item, InfoTags)
        set_Duration(Item, InfoTags)
        set_PlaycountVideo(Item, InfoTags)
        set_LastPlayed(Item, InfoTags)
        set_Genres(Item, InfoTags)
        set_Countries(Item, InfoTags)
        set_TagLine(Item, InfoTags)
        set_Studios(Item, InfoTags)
        set_Writers(Item, InfoTags)
        set_Directors(Item, InfoTags)
        set_IMDBNumber(Item, InfoTags)
        set_UserRating(Item, InfoTags)
        set_Premiered(Item, InfoTags)
        set_DbIdVideo(Item, InfoTags)
        set_ResumePoint(Item, InfoTags)
        set_Path(Item, InfoTags)
        set_FilenameAndPath(Item, InfoTags)
        Properties.update({'IsFolder': 'false', 'IsPlayable': 'true', "KodiType": "movie"})

    elif Item['Type'] == "Episode":
        InfoTags = ListItem.getVideoInfoTag()
        IsVideo = True
        InfoTags.setMediaType("episode")
        InfoTags.setTitle(Name)
        set_SortTitle(Item, InfoTags)
        set_OriginalTitle(Item, InfoTags)
        set_Plot(Item, InfoTags)
        set_PlotOutline(Item, InfoTags)
        set_DateAdded(Item, InfoTags)
        set_Year(Item, InfoTags)
        set_RatingVideo(Item, InfoTags)
        set_Mpaa(Item, InfoTags)
        set_Duration(Item, InfoTags)
        set_PlaycountVideo(Item, InfoTags)
        set_LastPlayed(Item, InfoTags)
        set_Genres(Item, InfoTags)
        set_Countries(Item, InfoTags)
        set_TagLine(Item, InfoTags)
        set_Studios(Item, InfoTags)
        set_Writers(Item, InfoTags)
        set_Directors(Item, InfoTags)
        set_SortSeason(Item, InfoTags)
        set_Season(Item, InfoTags, 'ParentIndexNumber')
        set_Episode(Item, InfoTags)
        set_SortEpisode(Item, InfoTags)
        set_TvShowTitle(Item, InfoTags)
        set_IMDBNumber(Item, InfoTags)
        set_UserRating(Item, InfoTags)
        set_Premiered(Item, InfoTags)
        set_DbIdVideo(Item, InfoTags)
        set_ResumePoint(Item, InfoTags)
        set_Path(Item, InfoTags)
        set_FilenameAndPath(Item, InfoTags)
        Properties.update({'IsFolder': 'false', 'IsPlayable': 'true', "KodiType": "episode"})

        # Virtual content e.g. Upcoming
        if 'Id' not in Item:
            Properties['IsPlayable'] = 'false'
            Item['NoLink'] = True

    elif Item['Type'] == "MusicVideo":
        InfoTags = ListItem.getVideoInfoTag()
        IsVideo = True
        InfoTags.setMediaType("musicvideo")

        if Item['IndexNumber']:
            InfoTags.setTrackNumber(int(Item['IndexNumber']))

        InfoTags.setTitle(Name)
        set_Album(Item, InfoTags)
        set_SortTitle(Item, InfoTags)
        set_OriginalTitle(Item, InfoTags)
        set_Plot(Item, InfoTags)
        set_PlotOutline(Item, InfoTags)
        set_DateAdded(Item, InfoTags)
        set_Year(Item, InfoTags)
        set_RatingVideo(Item, InfoTags)
        set_Duration(Item, InfoTags)
        set_PlaycountVideo(Item, InfoTags)
        set_LastPlayed(Item, InfoTags)
        set_Genres(Item, InfoTags)
        set_Countries(Item, InfoTags)
        set_TagLine(Item, InfoTags)
        set_Studios(Item, InfoTags)
        set_Writers(Item, InfoTags)
        set_Directors(Item, InfoTags)
        set_UserRating(Item, InfoTags)
        set_Premiered(Item, InfoTags)
        set_DbIdVideo(Item, InfoTags)
        set_ResumePoint(Item, InfoTags)
        set_Path(Item, InfoTags)
        set_FilenameAndPath(Item, InfoTags)
        Properties.update({'IsFolder': 'false', 'IsPlayable': 'true', "KodiType": "musicvideo"})

    elif Item['Type'] == "Video":
        InfoTags = ListItem.getVideoInfoTag()
        IsVideo = True
        InfoTags.setMediaType("video")
        InfoTags.setTitle(Name)
        set_SortTitle(Item, InfoTags)
        set_OriginalTitle(Item, InfoTags)
        set_Plot(Item, InfoTags)
        set_PlotOutline(Item, InfoTags)
        set_DateAdded(Item, InfoTags)
        set_Year(Item, InfoTags)
        set_Duration(Item, InfoTags)
        set_PlaycountVideo(Item, InfoTags)
        set_LastPlayed(Item, InfoTags)
        set_Genres(Item, InfoTags)
        set_TagLine(Item, InfoTags)
        set_Studios(Item, InfoTags)
        set_Writers(Item, InfoTags)
        set_Directors(Item, InfoTags)
        set_DbIdVideo(Item, InfoTags)
        set_ResumePoint(Item, InfoTags)
        set_Path(Item, InfoTags)
        set_FilenameAndPath(Item, InfoTags)
        Properties.update({'IsFolder': 'false', 'IsPlayable': 'true', "KodiType": "movie"})

    elif Item['Type'] == "Audio":
        Item['IndexNumber'] = Item.get('IndexNumber', None)
        common.set_RunTimeTicks(Item)
        InfoTags = ListItem.getMusicInfoTag()
        InfoTags.setArtist(" / ".join(Item['Artists']))
        set_Album(Item, InfoTags)
        set_AlbumArtist(Item, InfoTags)
        set_RatingMusic(Item, InfoTags)
        InfoTags.setMediaType("song")
        InfoTags.setTitle(Name)
        set_Year(Item, InfoTags)
        set_Duration(Item, InfoTags)
        set_PlaycountAudio(Item, InfoTags)
        set_LastPlayed(Item, InfoTags)
        set_Genres(Item, InfoTags)
        set_DbIdAudio(Item, InfoTags, "song")
        set_MusicBrainzArtistID(Item, InfoTags)
        set_MusicBrainzAlbumID(Item, InfoTags)
        set_MusicBrainzAlbumArtistID(Item, InfoTags)
        set_MusicBrainzTrackID(Item, InfoTags)
        set_Comment(Item, InfoTags)
        set_Disc(Item, InfoTags)
        set_Track(Item, InfoTags)
        InfoTags.setURL(Item['KodiFullPath'])
        Properties.update({'IsFolder': 'false', 'IsPlayable': 'true',  "KodiType": "song"})
        ListItem.setContentLookup(False)

    if 'MediaSources' in Item and Item['MediaSources']:
        Properties['mediasourcescount'] = len(Item['MediaSources'])

        if IsVideo and Item['MediaSources'][0] and 'KodiStreams' in Item['MediaSources'][0] and Item['MediaSources'][0]['KodiStreams']:
            for Stream in Item['MediaSources'][0]['KodiStreams']['Video']:
                set_ListItem_StreamInfo('video', InfoTags, Item['KodiRunTimeTicks'], Stream)

            for Stream in Item['MediaSources'][0]['KodiStreams']['Audio']:
                set_ListItem_StreamInfo('audio', InfoTags, 0, Stream)

            for Stream in Item['MediaSources'][0]['KodiStreams']['Subtitle']:
                set_ListItem_StreamInfo('subtitle', InfoTags, 0, Stream)

    cast = ()

    if IsVideo and 'ArtistItems' in Item and Item['ArtistItems']:
        for person in Item['ArtistItems']:
            cast += ((xbmc.Actor(person['Name'], "Artist", len(cast) + 1, person['imageurl'])),)

    if IsVideo and 'People' in Item and Item['People']:
        for person in Item['People']:
            if person['Type'] in ("Actor", 'Director', 'GuestStar'):
                ImageUrl = person['imageurl']
                cast += ((xbmc.Actor(person['Name'], person.get('Role', "Unknown"), len(cast) + 1, ImageUrl)),)

    if cast:
        InfoTags.setCast(cast)

    if Item['KodiArtwork']:
        ArtworkData = {}

        for KodiArtworkId, ArtworkValue in list(Item['KodiArtwork'].items()):
            if KodiArtworkId == 'fanart':
                for KodiArtworkIdFanart, ArtworkValueFanart in list(ArtworkValue.items()):
                    ArtworkData[KodiArtworkIdFanart] = ArtworkValueFanart
            else:
                if ArtworkValue:
                    ArtworkData[KodiArtworkId] = ArtworkValue

        set_Art(ListItem, ArtworkData)

    MimeType, _ = utils.get_MimeType(Item.get('KodiFilename', ""))

    if MimeType:
        ListItem.setMimeType(MimeType)
        Properties['mimetype'] = MimeType

    if StartOffset:
        Properties["StartOffset"] = StartOffset

    ListItem.setProperties(Properties)
    Item.update({'ListItem': ListItem, 'ServerId': ServerId, 'IsFolder': bool(Properties['IsFolder'] == "true")})

def set_Art(ListItem, Artwork):
    if Artwork:
        ArtworkData = dict(Artwork)

        # Work around Kodi's missing artwork fallbacks for plugin ListItems (Kodi bug)
        for Target, Sources in (("thumb", ("album.thumb", "season.poster", "season.banner", "tvshow.poster", "tvshow.banner", "set.poster")), ("fanart", ("artist.fanart", "albumartist.fanart", "tvshow.fanart", "set.fanart")), ("tvshow.thumb", ("tvshow.poster",)),):
            if not ArtworkData.get(Target):
                for Source in Sources:
                    if ArtworkData.get(Source):
                        ArtworkData[Target] = ArtworkData[Source]
                        break

        ListItem.setArt(ArtworkData)

def set_TvShowStatus(Item, InfoTags):
    Status = Item.get('Status', Item.get('KodiMetadataStatus', ""))

    if Status:
        InfoTags.setTvShowStatus(Status)

def set_UserRating(Item, InfoTags):
    UserRating = Item.get('UserRating', Item.get('KodiMetadataUserRating', 0))

    if UserRating:
        InfoTags.setUserRating(int(UserRating))

def set_RatingVideo(Item, InfoTags):
    if 'Ratings' not in Item and 'KodiMetadataRatings' in Item:
        Item['Ratings'] = Item['KodiMetadataRatings']

    if 'RatingType' not in Item and 'KodiMetadataRatingType' in Item:
        Item['RatingType'] = Item['KodiMetadataRatingType']

    if 'Ratings' not in Item:
        Item['Ratings'] = ()

        if 'CommunityRating' in Item and Item['CommunityRating']:
            Item['Ratings'] += (("default", float(Item['CommunityRating']), 0),)
            Item['RatingType'] = "default"
        elif 'KodiMetadataCommunityRating' in Item and Item['KodiMetadataCommunityRating']:
            Item['Ratings'] += (("default", float(Item['KodiMetadataCommunityRating']), 0),)
            Item['RatingType'] = "default"

    RatingData = {}

    for Rating in Item['Ratings']:
        if Rating[2]:
            RatingData[Rating[0]] = (float(Rating[1]), int(Rating[2]))
        else:
            RatingData[Rating[0]] = (float(Rating[1]), 0)

    if RatingData:
        InfoTags.setRatings(RatingData, Item['RatingType'])

def set_Path(Item, InfoTags):
    Path = Item.get('KodiPath', Item.get('KodiMetadataPath', ""))

    if Path:
        InfoTags.setPath(Path)

def set_FilenameAndPath(Item, InfoTags):
    Path = Item.get('KodiFullPath', Item.get('KodiMetadataPathandfilename', ""))

    if Path:
        InfoTags.setFilenameAndPath(Path)

def set_RatingMusic(Item, InfoTags):
    Rating = Item.get('CommunityRating', Item.get('KodiMetadataCommunityRating', ""))

    if Rating:
        InfoTags.setRating(float(Rating))

def set_PlotOutline(Item, InfoTags):
    Plot = Item.get('ShortOverview', Item.get('KodiMetadataShortOverview', ""))

    if Plot:
        InfoTags.setPlotOutline(Plot)

def set_OriginalTitle(Item, InfoTags):
    Title = Item.get('OriginalTitle', Item.get('KodiMetadataOriginalTitle', ""))

    if Title:
        InfoTags.setOriginalTitle(Title)

def set_SortSeason(Item, InfoTags):
    Season = Item.get('SortParentIndexNumber', Item.get('KodiMetadataSortParentIndexNumber', ""))

    if Season:
        InfoTags.setSortSeason(int(Season))

def set_Season(Item, InfoTags, IndexNumber):
    Season = Item.get(IndexNumber, Item.get(f"KodiMetadata{IndexNumber}", ""))

    if Season:
        InfoTags.setSeason(int(Season))

def set_Episode(Item, InfoTags):
    Ep = Item.get('IndexNumber', Item.get('KodiMetadataIndexNumber', ""))

    if Ep:
        InfoTags.setEpisode(int(Ep))

def set_SortEpisode(Item, InfoTags):
    Ep = Item.get('SortIndexNumber', Item.get('KodiMetadataSortIndexNumber', ""))

    if Ep:
        InfoTags.setSortEpisode(int(Ep))

def set_Genres(Item, InfoTags):
    Genres = Item.get('GenreNames', Item.get('KodiMetadataGenres', ""))

    if Genres:
        InfoTags.setGenres(Genres)

def set_Disc(Item, InfoTags):
    Disc = Item.get('ParentIndexNumber', Item.get('KodiMetadataDisc', 0))

    if Disc:
        InfoTags.setDisc(int(Disc))

def set_Year(Item, InfoTags):
    Year = Item.get('KodiProductionYear', Item.get('KodiMetadataYear', 0))

    if Year:
        InfoTags.setYear(int(Year))

def set_MusicBrainzArtistID(Item, InfoTags):
    MbId = Item.get('ProviderIds', {}).get('MusicBrainzArtist', Item.get('KodiMetadataMusicbrainzartistId', ""))

    if MbId:
        InfoTags.setMusicBrainzArtistID(tuple(MbId) if isinstance(MbId, (list, tuple)) else tuple(MbId.split("/")))

def set_MusicBrainzTrackID(Item, InfoTags):
    MbId = Item.get('ProviderIds', {}).get('MusicBrainzTrack', Item.get('KodiMetadataMusicbrainztrackId', ""))

    if MbId:
        InfoTags.setMusicBrainzTrackID(MbId)

def set_MusicBrainzAlbumID(Item, InfoTags):
    MbId = Item.get('ProviderIds', {}).get('MusicBrainzAlbum', Item.get('KodiMetadataMusicbrainzalbumId', ""))

    if MbId:
        InfoTags.setMusicBrainzAlbumID(MbId)

def set_MusicBrainzAlbumArtistID(Item, InfoTags):
    MbId = Item.get('ProviderIds', {}).get('MusicBrainzAlbumArtist', Item.get('KodiMetadataMusicbrainzalbumartistId', ""))

    if MbId:
        InfoTags.setMusicBrainzAlbumArtistID(tuple(MbId) if isinstance(MbId, (list, tuple)) else tuple(MbId.split("/")))

def set_MusicBrainzReleaseGroupID(Item, InfoTags):
    MbId = Item.get('ProviderIds', {}).get('MusicBrainzReleaseGroup', Item.get('KodiMetadataMusicbrainzReleaseGroupId', ""))

    if MbId:
        InfoTags.setMusicBrainzReleaseGroupID(MbId)

def set_Countries(Item, InfoTags):
    Locs = Item.get('ProductionLocations', Item.get('KodiMetadataProductionLocations', ""))

    if Locs:
        InfoTags.setCountries(Locs)

def set_Plot(Item, InfoTags):
    Plot = Item.get('Overview', Item.get('KodiMetadataOverview', ""))

    if Plot:
        InfoTags.setPlot(Plot)

def set_TagLine(Item, InfoTags):
    Tag = Item.get('Tagline', Item.get('KodiMetadataTagline', ""))

    if Tag:
        InfoTags.setTagLine(Tag)

def set_Studios(Item, InfoTags):
    Studios = Item.get('StudioNames', Item.get('KodiMetadataStudioNames', ""))

    if Studios:
        InfoTags.setStudios(Studios)

def set_Premiered(Item, InfoTags):
    Date = Item.get('KodiPremiereDate', Item.get('KodiMetadataPremiereDate', Item.get('KodiMetadataFirstaired', "")))

    if Date:
        InfoTags.setPremiered(Date)

def set_DateAdded(Item, InfoTags):
    Date = Item.get('KodiDateCreated', Item.get('KodiMetadataDateCreated', ""))

    if Date:
        InfoTags.setDateAdded(Date)

def set_AlbumArtist(Item, InfoTags):
    Artist = Item.get('AlbumArtist', Item.get('KodiMetadataAlbumartists', ""))

    if Artist:
        InfoTags.setAlbumArtist(Artist)

def set_Track(Item, InfoTags):
    Track = Item.get('IndexNumber', Item.get('KodiMetadataTrack', 0))

    if Track:
        InfoTags.setTrack(int(Track))

def set_Album(Item, InfoTags):
    Album = Item.get('Album', Item.get('KodiMetadataAlbum', ""))

    if Album:
        InfoTags.setAlbum(Album)

def set_SortTitle(Item, InfoTags):
    Sort = Item.get('SortName', Item.get('KodiMetadataSortName', ""))

    if Sort:
        InfoTags.setSortTitle(Sort)

def set_Comment(Item, InfoTags):
    Comment = Item.get('Overview', Item.get('KodiMetadataComment', ""))

    if Comment:
        InfoTags.setComment(Comment)

def set_Duration(Item, InfoTags):
    Dur = Item.get('KodiRunTimeTicks', Item.get('KodiMetadataDuration', 0))

    if Dur:
        InfoTags.setDuration(int(float(Dur)))

def set_PlaycountAudio(Item, InfoTags):
    Count = Item.get('KodiPlayCount', Item.get('KodiMetadataPlaycount', 0))

    if Count:
        InfoTags.setPlayCount(int(Count))
    else:
        InfoTags.setPlayCount(0)

def set_PlaycountVideo(Item, InfoTags):
    Count = Item.get('KodiPlayCount', Item.get('KodiMetadataPlaycount', 0))

    if Count:
        InfoTags.setPlaycount(int(Count))
    else:
        InfoTags.setPlaycount(0)

def set_LastPlayed(Item, InfoTags):
    PlayedDate = Item.get('KodiLastPlayedDate', Item.get('KodiMetadataLastplayed', ""))

    if PlayedDate:
        InfoTags.setLastPlayed(PlayedDate)

def set_IMDBNumber(Item, InfoTags):
    IdType = Item.get('UniqueIdType', Item.get('KodiMetadataUniqueIdType', ""))

    if IdType and IdType.lower() == "imdb":
        Val = Item.get('UniqueIdValue', Item.get('KodiMetadataUniqueIdValue', ""))

        if Val:
            InfoTags.setIMDBNumber(Val)

def set_Mpaa(Item, InfoTags):
    Mpaa = Item.get('MPAA', Item.get('KodiMetadataMPAA', ""))

    if Mpaa:
        InfoTags.setMpaa(Mpaa)

def set_TvShowTitle(Item, InfoTags):
    Title = Item.get('SeriesName', Item.get('KodiMetadataSeriesName', ""))

    if Title:
        InfoTags.setTvShowTitle(Title)

def set_ResumePoint(Item, InfoTags):
    Pos = Item.get('KodiPlaybackPositionTicks', Item.get('KodiMetadataPlaybackPositionTicks', ""))

    if Pos:
        Run = Item.get('KodiRunTimeTicks', Item.get('KodiMetadataRunTimeTicks'))

        if Run:
            InfoTags.setResumePoint(float(Pos), int(float(Run)))
        else:
            InfoTags.setResumePoint(float(Pos))

def set_Artists(Item, InfoTags):
    Artists = Item.get('Artists', Item.get('KodiMetadataArtist', ""))

    if Artists:
        InfoTags.setArtists(Artists if isinstance(Artists, (list, tuple)) else [Artists])

def set_Writers(Item, InfoTags):
    Writers = Item.get('Writers', Item.get('KodiMetadataWriters', ""))

    if Writers:
        InfoTags.setWriters(Writers)

def set_Directors(Item, InfoTags):
    Directors = Item.get('Directors', Item.get('KodiMetadataDirectors', ""))

    if Directors:
        InfoTags.setDirectors(Directors)


def set_DbIdVideo(Item, InfoTags):
    if 'KodiId' in Item and Item['KodiId']:
        InfoTags.setDbId(Item['KodiId'])

def set_DbIdAudio(Item, InfoTags, KodiType):
    if 'KodiId' in Item and Item['KodiId']:
        InfoTags.setDbId(Item['KodiId'], KodiType)

def set_ListItem_StreamInfo(Content, InfoTags, Duration, StreamInfo):
    if Content == "video":
        if StreamInfo['width'] and StreamInfo['height'] and StreamInfo['aspect']:
            if StreamInfo['language']:
                Language = StreamInfo['language']
            else:
                Language = ""

            if StreamInfo['codec']:
                Codec = StreamInfo['codec']
            else:
                Codec = ""

            if Duration:
                Duration = int(Duration)
            else:
                Duration = 0

            InfoTags.addVideoStream(xbmc.VideoStreamDetail(int(StreamInfo['width']), int(StreamInfo['height']), float(StreamInfo['aspect']), Duration, Codec, "", Language))
    elif Content == "audio":
        if StreamInfo['channels'] and StreamInfo['codec']:
            InfoTags.addAudioStream(xbmc.AudioStreamDetail(StreamInfo['channels'], StreamInfo['codec'], ""))
    elif Content == "subtitle":
        if StreamInfo['language']:
            InfoTags.addSubtitleStream(xbmc.SubtitleStreamDetail(StreamInfo['language']))

def set_Set(Item, InfoTags):
    Set = Item.get('Set', Item.get('KodiMetadataSet', ""))

    if Set:
        InfoTags.setSet(Set)

def set_SetOverview(Item, InfoTags):
    SetOverview = Item.get('SetOverview', Item.get('KodiMetadataSetOverview', ""))

    if SetOverview:
        InfoTags.setSetOverview(SetOverview)

def set_SetId(Item, InfoTags):
    SetId = Item.get('KodiMetadataSetId', 0)

    if SetId:
        InfoTags.setSetId(int(SetId))

def set_VideoAssetTitle(Item, InfoTags):
    VideoAssetTitle = Item.get('VideoAssetTitle', Item.get('KodiMetadataVideoAssetTitle', ""))

    if VideoAssetTitle:
        InfoTags.setVideoAssetTitle(VideoAssetTitle)

def set_ShowLinks(Item, InfoTags):
    ShowLinks = Item.get('ShowLinks', Item.get('KodiMetadataShowLinks', ()))

    if ShowLinks:
        InfoTags.setShowLinks(list(ShowLinks))

def set_Tags(Item, InfoTags):
    Tags = Item.get('Tags', Item.get('KodiMetadataTags', ()))

    if Tags:
        InfoTags.setTags(list(Tags))

def set_UniqueIDs(Item, InfoTags):
    UniqueIds = Item.get('UniqueIds', Item.get('KodiMetadataUniqueIds', {}))
    DefaultUniqueId = Item.get('UniqueIdType', Item.get('KodiMetadataUniqueIdType', ""))

    if UniqueIds:
        InfoTags.setUniqueIDs(UniqueIds, DefaultUniqueId)

def set_SongVideoURL(Item, InfoTags):
    SongVideoURL = Item.get('SongVideoURL', Item.get('KodiMetadataSongVideoURL', ""))

    if SongVideoURL:
        InfoTags.setSongVideoURL(SongVideoURL)
