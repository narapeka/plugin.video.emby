import base64
from urllib.parse import unquote, urlsplit
import xbmc
from helper import utils, copy, versions
EmbyTypeMappingShort = {"Movie": "m", "Episode": "e", "MusicVideo": "M", "Audio": "a", "Video": "v"}
ImageTagsMappings = {
    "Series": (('Primary', 'poster'), ('Disc', 'discart'), ('Logo', 'clearlogo'), ('Backdrop', 'fanart'), ('Primary', 'thumb'), ('Backdrop', 'landscape'), ('Primary', 'landscape')),
    "Season": (('Primary', 'poster'), ('Disc', 'discart'), ('Logo', 'clearlogo'), ('SeriesPrimary', 'poster'), ('Primary', 'thumb'), ('ParentLogo', 'clearlogo'), ('ParentBackdrop', 'fanart')),
    "Episode": (('Primary', 'thumb'), ('Disc', 'discart'), ('Logo', 'clearlogo'), ('Backdrop', 'fanart'), ('ParentLogo', 'clearlogo'), ('ParentBackdrop', 'landscape'), ('ParentBackdrop', 'fanart'), ('Primary', 'landscape'), ('SeriesPrimary', 'thumb')),
    "Movie": (('Primary', 'poster'), ('Disc', 'discart'), ('Logo', 'clearlogo'), ('Backdrop', 'thumb'), ('Backdrop', 'landscape'), ('Backdrop', 'fanart'), ('Primary', 'thumb'), ('Primary', 'landscape')),
    "BoxSet": (('Primary', 'poster'), ('Disc', 'discart'), ('Logo', 'clearlogo'), ('Backdrop', 'fanart'), ('Primary', 'thumb'), ('Primary', 'landscape')),
    "Video": (('Primary', 'poster'), ('Disc', 'discart'), ('Logo', 'clearlogo'), ('Backdrop', 'fanart'), ('Primary', 'thumb')),
    "MusicArtist": (('Primary', 'thumb'), ('Primary', 'poster'), ('Disc', 'discart'), ('Logo', 'clearlogo'), ('Backdrop', 'fanart'), ('Primary', 'thumb'), ('Primary', 'landscape')),
    "MusicAlbum": (('Primary', 'thumb'), ('Primary', 'poster'), ('Disc', 'discart'), ('Logo', 'clearlogo'), ('Backdrop', 'fanart'), ('Primary', 'thumb'), ('ParentLogo', 'clearlogo'), ('AlbumArtists', 'poster'), ('AlbumArtists', 'thumb'), ('AlbumArtists', 'fanart'), ('ArtistItems', 'poster'), ('ArtistItems', 'thumb'), ('ArtistItems', 'fanart'), ('Primary', 'landscape')),
    "Audio": (('Primary', 'thumb'), ('Primary', 'poster'), ('Disc', 'discart'), ('Logo', 'clearlogo'), ('Backdrop', 'fanart'), ('AlbumPrimary', 'poster'), ('AlbumPrimary', 'thumb'), ('ParentLogo', 'clearlogo'), ('ParentBackdrop', 'fanart'), ('AlbumArtists', 'poster'), ('AlbumArtists', 'thumb'), ('AlbumArtists', 'fanart'), ('ArtistItems', 'poster'), ('ArtistItems', 'thumb'), ('ArtistItems', 'fanart'), ('Primary', 'landscape')),
    "MusicVideo": (('Primary', 'poster'), ('Disc', 'discart'), ('Logo', 'clearlogo'), ('Backdrop', 'fanart'), ('Primary', 'thumb'), ('Primary', 'landscape')),
    "Folder": (('Primary', 'poster'), ('Disc', 'discart'), ('Logo', 'clearlogo'), ('Backdrop', 'fanart'), ('Primary', 'thumb')),
    "Person": (('Primary', 'poster'), ('Backdrop', 'fanart'), ('Primary', 'thumb'), ('Primary', 'landscape')),
    "Genre": (('Primary', 'poster'), ('Disc', 'discart'), ('Logo', 'clearlogo'), ('Backdrop', 'fanart'), ('Primary', 'thumb'), ('Primary', 'landscape')),
    "MusicGenre": (('Primary', 'poster'), ('Disc', 'discart'), ('Logo', 'clearlogo'), ('Backdrop', 'fanart'), ('Primary', 'thumb'), ('Primary', 'landscape')),
    "Tag": (('Primary', 'poster'), ('Disc', 'discart'), ('Logo', 'clearlogo'), ('Backdrop', 'fanart'), ('Primary', 'thumb'), ('Primary', 'landscape')),
}
CachedItemsMissing = {}

def load_ExistingItem(Item, Library, EmbyDB, EmbyType):
    if 'Id' not in Item:
        xbmc.log("EMBY.core.common: Skipping item without an Emby ID", xbmc.LOGDEBUG)
        return False

    if Item['LibraryId'] not in Library.LibrarySyncedNames:
        return False

    ExistingItem = EmbyDB.get_item_by_id(Item['Id'], EmbyType)
    ForceNew = False

    if ExistingItem and EmbyType in ("Movie", "Video", "MusicVideo", "Episode"):
        if not ExistingItem[1] and not ExistingItem[3]: # no KodiItemId and no KodiFileId assigned but Item exists (this means it's a multi version content item (grouped))
            if len(Item['MediaSources']) == 1: # multi version content item (grouped) was released
                EmbyDB.remove_item(Item['Id'], EmbyType, Item['LibraryId'])
                ForceNew = True
            else:
                return False

    if EmbyType in ("Genre", "Person", "Tag", "Studio"):
        if ExistingItem:
            Item.update({'KodiItemId': ExistingItem[1], 'UpdateItem': True})
        else:
            Item.update({'KodiItemId': "", 'UpdateItem': False})

        return True

    if EmbyType == "BoxSet":
        if ExistingItem:
            Item.update({'KodiItemId': ExistingItem[1], 'UpdateItem': True, "EmbyFavourite": ExistingItem[2], "KodiParentId": ExistingItem[3]})
        else:
            Item.update({'KodiItemId': "", 'UpdateItem': False, "EmbyFavourite": None, "KodiParentId": None})

        return True

    if EmbyType == "Episode":
        if not ForceNew and ExistingItem:
            Item.update({'KodiItemId': ExistingItem[1], 'UpdateItem': True, "EmbyFavourite": ExistingItem[2], "KodiFileId": ExistingItem[3], "KodiParentId": ExistingItem[4], "EmbyPresentationKey": ExistingItem[5], "EmbyFolder": ExistingItem[6], "KodiPathId": ExistingItem[7]})
        else:
            Item.update({'KodiItemId': "", 'UpdateItem': False, "EmbyFavourite": None, "KodiParentId": None, "EmbyPresentationKey": None, "EmbyFolder": None, "KodiFileId": None, "KodiPathId": None})

        return True

    if EmbyType == "Season":
        if ExistingItem:
            Item.update({'KodiItemId': ExistingItem[1], 'UpdateItem': True, "EmbyFavourite": ExistingItem[2], "KodiParentId": ExistingItem[3], "EmbyPresentationKey": ExistingItem[4]})
        else:
            Item.update({'KodiItemId': "", 'UpdateItem': False, "EmbyFavourite": None, "KodiParentId": None, "EmbyPresentationKey": None})

        return True

    if EmbyType == "Playlist":
        if ExistingItem:
            Item.update({'UpdateItem': True, 'EmbyLinkedId': ExistingItem[4]})
        else:
            Item.update({'UpdateItem': False, 'EmbyLinkedId': ""})

        return True

    LibrarySyncedName = Library.LibrarySyncedNames[Item['LibraryId']]

    if EmbyType == "Movie":
        if not ForceNew and ExistingItem:
            Item.update({"LibraryName": LibrarySyncedName, 'KodiItemId': ExistingItem[1], 'UpdateItem': True, "EmbyFavourite": ExistingItem[2], "KodiFileId": ExistingItem[3], "EmbyPresentationKey": ExistingItem[4], "EmbyFolder": ExistingItem[5], "KodiPathId": ExistingItem[6]})
        else:
            Item.update({"LibraryName": LibrarySyncedName, 'KodiItemId': "", 'UpdateItem': False, "EmbyFavourite": None, "EmbyPresentationKey": None, "EmbyFolder": None, "KodiFileId": None, "KodiPathId": None})

        return True

    if EmbyType == "MusicVideo":
        if not ForceNew and ExistingItem:
            Item.update({"LibraryName": LibrarySyncedName, 'KodiItemId': ExistingItem[1], 'UpdateItem': True, "EmbyFavourite": ExistingItem[2], "KodiFileId": ExistingItem[3], "EmbyPresentationKey": ExistingItem[4], "EmbyFolder": ExistingItem[5], "KodiPathId": ExistingItem[6], "LibraryIds": ExistingItem[7]})
        else:
            Item.update({"LibraryName": LibrarySyncedName, 'KodiItemId': "", 'UpdateItem': False, "EmbyFavourite": None, "EmbyPresentationKey": None, "EmbyFolder": None, "KodiFileId": None, "KodiPathId": None, "LibraryIds": None})

        return True

    if EmbyType == "Video":
        if not ForceNew and ExistingItem:
            Item.update({"LibraryName": LibrarySyncedName, 'KodiItemId': ExistingItem[1], 'UpdateItem': True, "EmbyFavourite": ExistingItem[2], "KodiFileId": ExistingItem[3], "EmbyPresentationKey": ExistingItem[4], "EmbyFolder": ExistingItem[5], "KodiPathId": ExistingItem[6]})
        else:
            Item.update({"LibraryName": LibrarySyncedName, 'KodiItemId': "", 'UpdateItem': False, "EmbyFavourite": None, "EmbyPresentationKey": None, "EmbyFolder": None, "KodiFileId": None, "KodiPathId": None})

        return True

    if EmbyType == "Series":
        if ExistingItem:
            Item.update({"LibraryName": LibrarySyncedName, 'KodiItemId': ExistingItem[1], 'UpdateItem': True, "EmbyFavourite": ExistingItem[2], "EmbyPresentationKey": ExistingItem[3], "KodiPathId": ExistingItem[4]})
        else:
            Item.update({"LibraryName": LibrarySyncedName, 'KodiItemId': "", 'UpdateItem': False, "EmbyFavourite": None, "EmbyPresentationKey": None, "KodiPathId": None,})

        return True

    if EmbyType in ("MusicArtist", "MusicGenre"):
        if ExistingItem:
            Item.update({'KodiItemId': ExistingItem[1], 'UpdateItem': True, "LibraryIds": ExistingItem[3]})
        else:
            Item.update({'KodiItemId': "", 'UpdateItem': False, "LibraryIds": ""})

        return True

    if EmbyType == "MusicAlbum":
        if ExistingItem:
            Item.update({'KodiItemId': ExistingItem[1], 'UpdateItem': True, "EmbyFavourite": ExistingItem[2], "LibraryIds": ExistingItem[3]})
        else:
            Item.update({'KodiItemId': "", 'UpdateItem': False, "EmbyFavourite": None, "LibraryIds": ""})

        return True

    if EmbyType == "Audio":
        if ExistingItem:
            Item.update({'KodiItemId': ExistingItem[1], 'UpdateItem': True, "EmbyFavourite": ExistingItem[2], "EmbyFolder": ExistingItem[3], "KodiPathId": ExistingItem[4], "LibraryIds": ExistingItem[5]})
        else:
            Item.update({'KodiItemId': "", 'UpdateItem': False, "EmbyFavourite": None, "EmbyFolder": None, "KodiPathId": None, "LibraryIds": ""})

        return True

    return False


def needs_http_iso_alias(Path, Container):
    if not Path.lower().startswith(('http://', 'https://')) or (Container or '').lower() not in ('', 'strm', 'iso'):
        return False

    try:
        URL = urlsplit(Path.split('|', 1)[0])
    except ValueError:
        return False

    if not URL.netloc:
        return False

    Segments = [unquote(Segment).lower() for Segment in URL.path.rstrip('/').split('/')]
    Filename = Segments[-1]
    if Filename.endswith('.iso'):
        # Keep plain ISO URLs direct. A signed URL can need a visible ISO suffix on the loopback entry.
        return (not Path.lower().endswith('.iso') and not URL.path.endswith('/')
                and '/' not in Filename and '\\' not in Filename)

    # An explicit media filename at the end takes precedence over an earlier directory name.
    if Filename.endswith(('.img', '.nrg', '.udf', '.mkv', '.mp4', '.m4v',
                          '.avi', '.mov', '.wmv', '.webm', '.asf', '.ts', '.tp', '.m2ts', '.mts',
                          '.mpg', '.mpeg', '.vob', '.flv', '.rm', '.rmvb', '.3gp',
                          '.bdmv', '.ifo', '.strm', '.m3u8')):
        return False

    return any(Segment.endswith('.iso') and '/' not in Segment and '\\' not in Segment
               for Segment in Segments[:-1])


def set_path_filename(Item, ServerId, MediaSource, isDynamic=False):
    Item['KodiFullPath'] = ""

    if "Id" not in Item:
        return

    isHttpByEmby = False

    if Item.get('NoLink'):
        return


    if isDynamic:
        Dynamic = "dynamic/"

        if 'LibraryId' not in Item or not Item['LibraryId']:
            Item['LibraryId'] = "0"
    else:
        Dynamic = ""

    IsDisc = False
    Item['KodiStackedFilename'] = None
    MediaSources = Item.get('MediaSources', [])
    MediaSourcesLocal = MediaSources
    PathSource = {}

    if MediaSource and "Path" in MediaSource: # Multiversion content supported by Kodi (Movies)
        PathSource = MediaSource
        MediaSourcesLocal = (PathSource,)
        Path = PathSource['Path']
    elif MediaSources and "Path" in MediaSources[0]:
        PathSource = MediaSources[0]
        Path = PathSource['Path']
        if Item['Type'] == 'Movie' and not isDynamic:
            # Native Kodi movie version URLs resolve to their own file's source.
            MediaSourcesLocal = (PathSource,)
    elif 'Path' in Item:
        Path = Item['Path']
    else:
        Path = ""

    Item['KodiPath'] = Path

    # Addonmode replace filextensions
    if Item['KodiPath'].endswith('.strm') and 'Container' in Item:
        Item['KodiPath'] = Item['KodiPath'][:-5]

        if not Item['KodiPath'].endswith(Item['Container']):
            Item['KodiPath'] += f".{Item['Container']}"

    if Item['KodiPath'].startswith('\\\\'):
        Item['KodiPath'] = Item['KodiPath'].replace('\\\\', "SMBINJECT", 1).replace('\\', "/") # only replace \\ on beginning with smb://
        Item['KodiPath'] = Item['KodiPath'].replace('//', "/")  # fix trailing "/" (Emby server path substitution -> user assigned "wrong" trailing "/")
        Item['KodiPath'] = Item['KodiPath'].replace('SMBINJECT', "smb://") # only replace \\ on beginning with smb://
    elif '://' in Item['KodiPath']:
        protocol = Item['KodiPath'].split('://')[0]
        Item['KodiPath'] = Item['KodiPath'].replace(protocol, protocol.lower())
    else:
        Item['KodiPath'] = Item['KodiPath'].replace("\\\\", "\\")

    KodiPathLower = Item['KodiPath'].lower()

    Container = Item.get('Container', "")

    # Special content type
    if Container == 'dvd':
        Item['KodiPathParent'] = Item['KodiPath']
        Item['KodiPath'] += "/VIDEO_TS/"
        Item['KodiFilename'] = "VIDEO_TS.IFO"
        Item['KodiFullPath'] = f"{Item['KodiPath']}{Item['KodiFilename']}"
        return

    if Container == 'bluray':
        Item['KodiPathParent'] = Item['KodiPath']
        Item['KodiPath'] += "/BDMV/"
        Item['KodiFilename'] = "index.bdmv"
        Item['KodiFullPath'] = f"{Item['KodiPath']}{Item['KodiFilename']}"
        return

    if KodiPathLower.startswith("plugin://"):
        Item['KodiPathParent'] = Item['KodiPath']
        Item['KodiFilename'] = Item['KodiPath']
        Item['KodiFullPath'] = Item['KodiPath']
        return

    HttpIsoSources = set()
    if Item['Type'] in ('Movie', 'Episode', 'MusicVideo', 'Video'):
        for Source in MediaSourcesLocal:
            SourceContainer = Source.get('Container') or (Container if not MediaSources or Source is MediaSources[0] else "")
            if needs_http_iso_alias(Source.get('Path') or '', SourceContainer):
                HttpIsoSources.add(Source['Id'])

    # The loopback URL supplies the .iso filename while the redirect retains the full source URL.
    IsHttpIso = PathSource.get('Id') in HttpIsoSources

    # Disc images retain Kodi's original-path playback.
    if not IsHttpIso and (Container == 'iso' or KodiPathLower.endswith(".iso")):
        IsDisc = True
    elif KodiPathLower.startswith("http://") or KodiPathLower.startswith("https://"):
        IsDisc = False
        Dynamic += "http/"
        isHttpByEmby = True

    # Build filename
    if isHttpByEmby:
        if IsHttpIso and len(MediaSourcesLocal) == 1:
            Item['KodiFilename'] = "unknown.iso"
        elif IsHttpIso and Container == 'iso':
            Item['KodiFilename'] = "unknown"
        elif 'Container' in Item:
            Item['KodiFilename'] = f"unknown.{Item['Container']}"
        else:
            Item['KodiFilename'] = "unknown"
    elif Item['KodiPath']:
        Item['KodiFilename'] = utils.get_Filename(Item['KodiPath'], IsDisc)
    else: # channels
        Item['KodiFilename'] = "unknown.ts"
        IsDisc = False

    # Build path
    if IsDisc:
        PathSeperator = utils.get_Path_Seperator(Item['KodiPath'])
        Temp = Item['KodiPath'].rsplit(PathSeperator, 1)[1]

        if Item['Type'] == "Series":
            Item['KodiPathParent'] = Item['KodiPath'][:len(Item['KodiPath']) - len(Temp)]
            Item['KodiPath'] += PathSeperator
        else:
            Item['KodiPath'] = Item['KodiPath'][:len(Item['KodiPath']) - len(Temp)]
    else:
        if Item['Type'] in EmbyTypeMappingShort:
            ContextMenuTags = ""
            MediaID = EmbyTypeMappingShort[Item['Type']]

            # Set tags in filenames, so addon.xml can detect specials, multiversions etc. -> context menu options
            if len(Item.get('MediaSources', MediaSourcesLocal)) > 1: # Multiversion content
                ContextMenuTags += "m"

            MetaFolder = f"{MediaID}-{Item.get('KodiItemId', 0)}-{Item.get('KodiFileId', 0)}-{ContextMenuTags}"

            # Encode metatdata, sperators are <>, ><, <<, :
            MetadataSub = []

            PlaybackSources = versions.sort_sources(MediaSourcesLocal)
            # Synced generic videos already open the first sorted source without a dialog.
            if HttpIsoSources and isHttpByEmby and Item['Type'] == 'Video' and not isDynamic:
                if PlaybackSources[0]['Id'] in HttpIsoSources:
                    Item['KodiFilename'] = "unknown.iso"

            for MediaSourceItem in PlaybackSources:
                IsRemote = MediaSourceItem.get('IsRemote', False)

                if IsRemote:
                    IsRemote = "1"
                else:
                    IsRemote = "0"

                MediasourceString = f"{MediaSourceItem.get('Name', 'unknown').replace(':', '<;>')}:{MediaSourceItem['Size'] or 0}:{MediaSourceItem['Id']}:{MediaSourceItem['Path'].replace(':', '<;>')}:{MediaSourceItem.get('IntroStartPositionTicks', 0)}:{MediaSourceItem.get('IntroEndPositionTicks', 0)}:{MediaSourceItem.get('CreditsPositionTicks', 0)}:{IsRemote}"
                if len(PlaybackSources) > 1 and MediaSourceItem['Id'] in HttpIsoSources:
                    # Carry the decision only when the source will be chosen at playback.
                    MediasourceString += ":1"
                SubData = [[], [], []]

                for KodiVideoStream in MediaSourceItem['KodiStreams']['Video']:
                    SubData[0].append(f"{KodiVideoStream['codec'].replace(':', '<;>')}:{KodiVideoStream['BitRate'] or 0}:{KodiVideoStream['Index']}:{KodiVideoStream['width'] or 0}")

                for KodiAudioStream in MediaSourceItem['KodiStreams']['Audio']:
                    SubData[1].append(f"{KodiAudioStream['DisplayTitle'].replace(':', '<;>')}:{KodiAudioStream['codec'].replace(':', '<;>')}:{KodiAudioStream['BitRate'] or 0}:{KodiAudioStream['Index']}")

                for KodiSubtitleStream in MediaSourceItem['KodiStreams']['Subtitle']:
                    if KodiSubtitleStream['forced']:
                        isForced = 1
                    else:
                        isForced = 0

                    SubData[2].append(f"{KodiSubtitleStream['language'].replace(':', '<;>')}:{KodiSubtitleStream['DisplayTitle'].replace(':', '<;>')}:{KodiSubtitleStream['external']}:{KodiSubtitleStream['Index']}:{KodiSubtitleStream['codec'].replace(':', '<;>')}:{isForced}")

                SubData[0] = "><".join(SubData[0])
                SubData[1] = "><".join(SubData[1])
                SubData[2] = "><".join(SubData[2])
                MetadataSub.append(f"{MediasourceString}<<{'<<'.join(SubData)}")

            MetadataSub = "<>".join(MetadataSub)
            MetadataSub = base64.b16encode(MetadataSub.encode('utf-8')).decode('utf-8')
            MetaFolder += f"-{MetadataSub}"

        if Item['Type'] == "Series":
            Item['KodiPathParent'] = f"{utils.AddonModePath}{Dynamic}tvshows/{ServerId}/{Item['LibraryId']}/"
            Item['KodiPath'] = f"{utils.AddonModePath}{Dynamic}tvshows/{ServerId}/{Item['LibraryId']}/0/{Item['Id']}/"
        elif Item['Type'] == "Episode":
            Item['KodiPath'] = f"{utils.AddonModePath}{Dynamic}tvshows/{ServerId}/{Item['LibraryId']}/{Item['SeriesId']}/{Item['Id']}/{MetaFolder}/"
        elif Item['Type'] == "Movie":
            Item['KodiPath'] = f"{utils.AddonModePath}{Dynamic}movies/{ServerId}/{Item['LibraryId']}/0/{Item['Id']}/{MetaFolder}/"
        elif Item['Type'] == "Video":
            Item['KodiPath'] = f"{utils.AddonModePath}{Dynamic}video/{ServerId}/{Item['LibraryId']}/0/{Item['Id']}/{MetaFolder}/"
        elif Item['Type'] == "MusicVideo":
            Item['KodiPath'] = f"{utils.AddonModePath}{Dynamic}musicvideos/{ServerId}/{Item['LibraryId']}/0/{Item['Id']}/{MetaFolder}/"
        elif Item['Type'] == "Audio":
            Item['KodiPath'] = f"http://127.0.0.1:57342/{Dynamic}audio/{ServerId}/{Item['LibraryId']}/0/{Item['Id']}/{MetaFolder}/"

    Item['KodiFullPath'] = f"{Item['KodiPath']}{Item['KodiFilename']}"

    if Item['KodiPath'].startswith("http://127.0.0.1:57342/"):
        Item['KodiFullPath'] += "|redirect-limit=1000&failonerror=false"
        Item['KodiPath'] += "|redirect-limit=1000&failonerror=false"

        if 'KodiPathParent' in Item:
            Item['KodiPathParent'] += "|redirect-limit=1000&failonerror=false"

    if isHttpByEmby:
        Item['KodiPath'] = f'{Item["KodiPath"].replace("|redirect-limit=1000&failonerror=false", "")}|redirect-limit=1000&failonerror=false&connection-timeout={utils.httpConnectionTimeout}'
        Item['KodiFullPath'] = f'{Item["KodiFullPath"].replace("|redirect-limit=1000&failonerror=false", "")}|redirect-limit=1000&failonerror=false&connection-timeout={utils.httpConnectionTimeout}'

        if 'KodiPathParent' in Item:
            Item['KodiPathParent'] = f'{Item["KodiPathParent"].replace("|redirect-limit=1000&failonerror=false", "")}|redirect-limit=1000&failonerror=false&connection-timeout={utils.httpConnectionTimeout}'

# Detect Multipart videos
def set_multipart(Item, Library):
    if 'PartCount' in Item and Library.API:
        if Item['PartCount'] >= 2:
            AdditionalParts = Library.API.get_additional_parts(Item['Id'])

            if Item['KodiRunTimeTicks']:
                Value = float(Item['KodiRunTimeTicks'])
                StackedKodiRunTimeTicks = (str(Value),)
                StackedKodiRunTimeTicksSum = Value
            else:
                StackedKodiRunTimeTicks = ("0",)
                StackedKodiRunTimeTicksSum = 0

            StackedFilenames = (Item['KodiFullPath'].replace(',', ' '),)

            for AdditionalItem in AdditionalParts['Items']:
                set_streams(AdditionalItem)
                set_chapters(AdditionalItem, Library.ServerData['ServerId'])
                AdditionalItem.update({'KodiItemId': Item['KodiItemId'], 'KodiFileId': Item['KodiFileId'], 'KodiPath': Item['KodiPath'], 'LibraryId': Item['LibraryId']})
                set_path_filename(AdditionalItem, Library.ServerData['ServerId'], {}, False)
                set_streams(AdditionalItem)
                StackedFilenames += (AdditionalItem['KodiFullPath'].replace(',', ' '),)

                if 'RunTimeTicks' in AdditionalItem and AdditionalItem['RunTimeTicks']:
                    Value = round(float(AdditionalItem['RunTimeTicks'] / 10000000.0), 6)
                else:
                    Value = 0

                StackedKodiRunTimeTicksSum += Value
                StackedKodiRunTimeTicks += (str(StackedKodiRunTimeTicksSum),)

            if StackedKodiRunTimeTicksSum:
                Item['KodiRunTimeTicks'] = StackedKodiRunTimeTicksSum
            else:
                Item['KodiRunTimeTicks'] = None

            Item['KodiStackedFilename'] = f"stack://{' , '.join(StackedFilenames)}"
            Item['KodiStackTimes'] = ','.join(StackedKodiRunTimeTicks)
            Item['KodiPath'] = utils.AddonModePath

def set_streams(Item):
    if 'MediaSources' not in Item or not Item['MediaSources']:
        return

    # Sort mediasources -> core infos must reference first mediasource
    if Item['MediaSources'][0]['Type'] != "Default":
        Defaults = [Source for Source in Item['MediaSources'] if Source['Type'] == "Default"]
        Others = [Source for Source in Item['MediaSources'] if Source['Type'] != "Default"]
        # Retain every source; preserve the original last-first fallback without a default.
        Item['MediaSources'] = Defaults + Others if Defaults else Others[-1:] + Others[:-1]

    # Streams
    for MediaSource in Item['MediaSources']:
        KodiStreamVideoIndex = 0
        KodiStreamAudioIndex = 0
        KodiStreamSubtitleIndex = 0
        MediaSource['Path'] = MediaSource.get('Path', "")
        MediaSource['Size'] = MediaSource.get('Size', "")
        RunTimeTicks = MediaSource.get('RunTimeTicks', Item.get('RunTimeTicks', None))

        if RunTimeTicks:
            MediaSource['KodiRunTimeTicks'] = round(float(RunTimeTicks / 10000000.0), 6)
        else:
            MediaSource['KodiRunTimeTicks'] = None

        Video3DFormat = MediaSource.get('Video3DFormat', None)
        MediaSource['KodiStreams'] = {'Subtitle': [], 'Audio': [], 'Video': []}

        for Stream in MediaSource['MediaStreams']:
            Codec = Stream.get('Codec')
            StreamIndex = Stream.get('Index', "0")

            if not Codec:
                Codec = Stream.get('CodecTag', "")

            if Codec:
                Codec = Codec.lower().replace("-", "")

            if Codec == "dts":
                Profile = Stream.get('Profile', "").lower()

                if Profile == "dts-hd ma":
                    Codec = "dtshd_ma"
                elif Profile == "dts-hd hra":
                    Codec = "dtshd_hra"

            if Stream['Type'] == "Audio" or Stream['Type'] == "Default":
                MediaSource['KodiStreams']['Audio'].append({'SampleRate': Stream.get('SampleRate', None), 'BitRate': Stream.get('BitRate', None), 'codec': Codec, 'channels': Stream.get('Channels', None), 'language': Stream.get('Language', ""), 'Index': StreamIndex, 'DisplayTitle': Stream.get('DisplayTitle', "unknown.jpg").replace(chr(1), "").replace(chr(0), ""), 'default': Stream.get('IsDefault', False), 'hearingimpaired': Stream.get('IsHearingImpaired', False)})
                KodiStreamAudioIndex += 1
            elif Stream['Type'] == "Video":
                StreamData = {'language': Stream.get('Language', ""),'hdrtype': None, 'hdrdetail': "", 'codec': Codec, 'height': Stream.get('Height', None), 'width': Stream.get('Width', None), 'BitRate': Stream.get('BitRate', None), 'Index': StreamIndex, 'aspect': None, 'stereomode': "", 'default': Stream.get('IsDefault', False), 'hearingimpaired': Stream.get('IsHearingImpaired', False)}
                VideoRange = Stream.get('VideoRange', "").lower()

                if VideoRange == "hdr 10":
                    StreamData['hdrtype'] = "hdr10"
                elif VideoRange == "hlg":
                    StreamData['hdrtype'] = "hlg"
                elif VideoRange == "dolbyvision":
                    StreamData['hdrtype'] = "dolbyvision"
                    ExtendedVideoSubType = Stream.get('ExtendedVideoSubType', '')

                    if ExtendedVideoSubType and ExtendedVideoSubType != 'None':
                        if ExtendedVideoSubType == 'DoviProfile50':
                            StreamData['hdrdetail'] = "5"
                        elif ExtendedVideoSubType == 'DoviProfile76':
                            StreamData['hdrdetail'] = "7"
                        elif ExtendedVideoSubType == 'DoviProfile81':
                            StreamData['hdrdetail'] = "8.1"
                        elif ExtendedVideoSubType == 'DoviProfile84':
                            StreamData['hdrdetail'] = "8.4"
                        elif ExtendedVideoSubType == 'DoviProfile92':
                            StreamData['hdrdetail'] = "9.2"
                        elif ExtendedVideoSubType == 'DoviProfile10':
                            StreamData['hdrdetail'] = "10"

                if Video3DFormat in ('HalfSideBySide', 'FullSideBySide'):
                    StreamData['stereomode'] = "left_right"
                elif Video3DFormat in ('HalfTopAndBottom', 'FullTopAndBottom'):
                    StreamData['stereomode'] = "top_bottom"

                if "AspectRatio" in Stream:
                    AspectRatio = Stream['AspectRatio'].split(':')

                    if len(AspectRatio) != 2:
                        AspectRatio = Stream['AspectRatio'].split('/')

                    if len(AspectRatio) == 2 and is_number(AspectRatio[0]) and is_number(AspectRatio[1]) and float(AspectRatio[1]) > 0:
                        StreamData['aspect'] = round(float(AspectRatio[0]) / float(AspectRatio[1]), 6)

                if not StreamData['aspect']:

                    if 'Height' in Stream and Stream['Height'] and 'Width' in Stream and Stream['Width']:
                        StreamData['aspect'] = round(float(Stream['Width']) / float(Stream['Height']), 6)

                MediaSource['KodiStreams']['Video'].append(StreamData)
                KodiStreamVideoIndex += 1
            elif Stream['Type'] == "Subtitle":
                IsExternal = Stream.get('IsExternal', False)

                if IsExternal:
                    IsExternal = "1"
                else:
                    IsExternal = "0"

                MediaSource['KodiStreams']['Subtitle'].append({'Index': StreamIndex, 'language': Stream.get('Language', "undefined"), 'DisplayTitle': Stream.get('DisplayTitle', "undefined").replace(chr(1), "").replace(chr(0), ""), 'codec': Codec, 'external': IsExternal, 'forced': Stream.get('IsForced', False), 'default': Stream.get('IsDefault', False)})
                KodiStreamSubtitleIndex += 1

def set_RunTimeTicks(Item):
    if 'RunTimeTicks' in Item:
        RunTimeTicks = Item['RunTimeTicks']
    elif 'PlaybackPositionTicks' in Item and Item['PlaybackPositionTicks'] and 'PlayedPercentage' in Item and Item['PlayedPercentage']: # calculate runtime based on progress
        RunTimeTicks = int(Item['PlaybackPositionTicks'] / Item['PlayedPercentage'] * 100)
    else:
        RunTimeTicks = None

    if RunTimeTicks:
        Item['KodiRunTimeTicks'] = round(float(RunTimeTicks / 10000000.0), 6)
        Item['RunTimeTicks'] = RunTimeTicks
    else:
        Item['KodiRunTimeTicks'] = None

def set_overview(Item):
    if 'Overview' in Item:
        if Item['Overview']:
            Item['Overview'] = Item['Overview'].replace("\"", "\'")
            Item['Overview'] = Item['Overview'].replace("\n", "[CR]")
            Item['Overview'] = Item['Overview'].replace("\r", " ")
            Item['Overview'] = Item['Overview'].replace("<br>", "[CR]")
    else:
        Item['Overview'] = None


def set_mpaa(Item):
    if 'OfficialRating' in Item:
        if Item['OfficialRating']:
            if Item['OfficialRating'] in ("NR", "UR"):
                # Kodi seems to not like NR, but will accept Not Rated
                Item['OfficialRating'] = "Not Rated"

            if "FSK-" in Item['OfficialRating']:
                Item['OfficialRating'] = Item['OfficialRating'].replace("-", " ")

            if "GB-" in Item['OfficialRating']:
                Item['OfficialRating'] = Item['OfficialRating'].replace("GB-", "UK:")
    else:
        Item['OfficialRating'] = None


def set_PlayCount(UserData):
    PlayCount = UserData.get('PlayCount', None)

    if 'Played' in UserData:
        if not UserData['Played']:
            KodiPlayCount = None
        else:
            if PlayCount:
                KodiPlayCount = PlayCount
            else:
                KodiPlayCount = 1
    else:
        KodiPlayCount = PlayCount

        if not KodiPlayCount: # could be "0" then substitute with "None", Kodi does not accept 0
            KodiPlayCount = None

    return KodiPlayCount

def set_playstate(Item):
    if 'KodiLastPlayedDate' in Item and 'KodiPlaybackPositionTicks' in Item and 'KodiPlayCount' in Item:
        return

    if 'UserData' in Item:
        UserData = Item['UserData']
    else:
        UserData = Item

    Item['KodiPlayCount'] = set_PlayCount(UserData)

    if 'LastPlayedDate' in UserData and UserData['LastPlayedDate']:
        Item['KodiLastPlayedDate'] = utils.convert_to_local(UserData['LastPlayedDate'], False, False)
    else:
        Item['KodiLastPlayedDate'] = None

    if 'PlaybackPositionTicks' in UserData and UserData['PlaybackPositionTicks']:
        Item['KodiPlaybackPositionTicks'] = float(UserData['PlaybackPositionTicks']) / 10000000.0 - float(utils.resumeJumpBack)

        if Item['KodiPlaybackPositionTicks'] <= 0:
            Item['KodiPlaybackPositionTicks'] = None
    else:
        Item['KodiPlaybackPositionTicks'] = None

def set_DateCreated(Item):
    if 'DateCreated' in Item:
        Item['KodiDateCreated'] = utils.convert_to_local(Item['DateCreated'], False, False)
    else:
        Item['KodiDateCreated'] = None

def set_common(Item, ServerId, DynamicNode, IncrementalSync):
    Item['ProductionLocations'] = Item.get('ProductionLocations', [])
    set_DateCreated(Item)

    if 'Taglines' not in Item or not Item['Taglines']:
        Item['Tagline'] = None
    else:
        Item['Tagline'] = "\n".join(Item['Taglines'])

    if 'TagItems' not in Item:
        Item['TagItems'] = []

    Item['OriginalTitle'] = Item.get('OriginalTitle', None)
    Item['SortIndexNumber'] = Item.get('SortIndexNumber', None)
    Item['SortParentIndexNumber'] = Item.get('SortParentIndexNumber', None)
    Item['IndexNumber'] = Item.get('IndexNumber', None)
    Item['CommunityRating'] = Item.get('CommunityRating', None)
    Item['ParentIndexNumber'] = Item.get('ParentIndexNumber', None)

    Item['ShortOverview'] = Item.get('ShortOverview', None)
    Item['Status'] = Item.get('Status', None)
    Item['KodiLastScraped'] = utils.currenttime_kodi_format()
    Item['ProviderIds'] = Item.get('ProviderIds', {})
    Item['ProviderIds']['MusicBrainzTrack'] = Item['ProviderIds'].get('MusicBrainzTrack', None)
    Item['ProviderIds']['MusicBrainzAlbum'] = Item['ProviderIds'].get('MusicBrainzAlbum', None)
    Item['ProviderIds']['MusicBrainzReleaseGroup'] = Item['ProviderIds'].get('MusicBrainzReleaseGroup', None)
    Item['ProviderIds']['MusicBrainzArtist'] = Item['ProviderIds'].get('MusicBrainzArtist', None)
    Item['ProviderIds']['MusicBrainzAlbumArtist'] = Item['ProviderIds'].get('MusicBrainzAlbumArtist', None)
    Item['IndexNumber'] = Item.get('IndexNumber', None)
    set_PresentationUniqueKey(Item)
    set_mpaa(Item)
    set_overview(Item)
    set_Dates(Item)
    set_KodiArtwork(Item, ServerId, DynamicNode)

    if DynamicNode:
        Item['GenreNames'] = []

        if 'GenreItems' in Item and Item['GenreItems']:
            for GenreItem in Item['GenreItems']:
                if 'Name' in GenreItem:
                    Item['GenreNames'].append(GenreItem['Name'])

        Item['StudioNames'] = []

        if 'Studios' in Item and Item['Studios']:
            for Studio in Item['Studios']:
                if 'Name' in Studio:
                    Item['StudioNames'].append(Studio['Name'])

        Item['Writers'] = []
        Item['Directors'] = []
        Item['Cast'] = []
        PeopleInvalidRecords = []

        if "People" in Item:
            for Index, People in enumerate(Item['People']):
                if 'Name' in People:
                    if People['Type'] == "Writer":
                        Item['Writers'].append(People['Name'])
                    elif People['Type'] == "Director":
                        Item['Directors'].append(People['Name'])
                    elif People['Type'] == "Actor":
                        Item['Cast'].append(People['Name'])

                    if 'PrimaryImageTag' in People:
                        People['imageurl'] = utils.image_url(ServerId, People['Id'], 'Primary', People['PrimaryImageTag'], "Person")
                    else:
                        People['imageurl'] = ""
                else:
                    PeopleInvalidRecords.append(Index)

            for PeopleInvalidRecord in PeopleInvalidRecords[::-1]: # reversed order
                del Item['People'][PeopleInvalidRecord]
        else:
            Item['People'] = []

        if "ArtistItems" in Item:
            for ArtistItem in Item['ArtistItems']:
                if 'PrimaryImageTag' in ArtistItem:
                    ArtistItem['imageurl'] = utils.image_url(ServerId, ArtistItem['Id'], 'Primary', ArtistItem['PrimaryImageTag'], "MusicArtist")
                else:
                    ArtistItem['imageurl'] = ""

def set_Dates(Item):
    if 'ProductionYear' in Item:
        Item['KodiProductionYear'] = utils.convert_to_local(Item['ProductionYear'], False, True)
    else:
        Item['KodiProductionYear'] = ""

    if 'PremiereDate' in Item:
        Item['KodiPremiereDate'] = utils.convert_to_local(Item['PremiereDate'], True, False)
    else:
        Item['KodiPremiereDate'] = ""

    if not Item['KodiPremiereDate'] and Item['KodiProductionYear']:
        Item['KodiPremiereDate'] = str(Item['KodiProductionYear'])

    if not Item['KodiProductionYear'] and Item['KodiPremiereDate']:
        Item['KodiProductionYear'] = Item['KodiPremiereDate'][:4]

def set_chapters(Item, ServerId):
    if 'MediaSources' not in Item:
        return

    MediaSourcesChapters = False

    for MediaSource in Item['MediaSources']:
        if 'Chapters' in MediaSource:
            MediaSourcesChapters = True
            break

    for MediaSourceIndex, MediaSource in enumerate(Item['MediaSources']):
        MediaSource['KodiChapters'] = {}
        MediaSource['IntroStartPositionTicks'] = 0
        MediaSource['IntroEndPositionTicks'] = 0
        MediaSource['CreditsPositionTicks'] = 0

        if MediaSourcesChapters:
            if 'Chapters' in MediaSource: # Chapters by mediasource
                ChaptersGenerated = is_generated_chapter_set(MediaSource['Chapters'])

                for Index, Chapter in enumerate(MediaSource['Chapters']):
                    load_chapter(MediaSource, Chapter, Index, ServerId, Item['Id'], ChaptersGenerated)
        else:
            if 'Chapters' in Item and MediaSourceIndex == 0: # load chapters by item
                ChaptersGenerated = is_generated_chapter_set(Item['Chapters'])

                for Index, Chapter in enumerate(Item['Chapters']):
                    load_chapter(MediaSource, Chapter, Index, ServerId, Item['Id'], ChaptersGenerated)
            else: # copy global KodiChapters to all MediaSources
                MediaSource['KodiChapters'] = Item['MediaSources'][0]['KodiChapters']
                MediaSource['IntroStartPositionTicks'] = Item['MediaSources'][0]['IntroStartPositionTicks']
                MediaSource['IntroEndPositionTicks'] = Item['MediaSources'][0]['IntroEndPositionTicks']
                MediaSource['CreditsPositionTicks'] = Item['MediaSources'][0]['CreditsPositionTicks']

def load_chapter(MediaSource, Chapter, Index, ServerId, ItemId, ChaptersGenerated):
    Chapter["StartPositionTicks"] = round(float(Chapter.get("StartPositionTicks", 0) / 10000000))
    Id = MediaSource.get('ItemId', ItemId)

    if "MarkerType" in Chapter and (Chapter['MarkerType'] == "IntroStart" or Chapter['MarkerType'] == "IntroEnd" or Chapter['MarkerType'] == "CreditsStart"):
        if Chapter['MarkerType'] == "IntroStart":
            MediaSource['IntroStartPositionTicks'] = Chapter["StartPositionTicks"]
        elif Chapter['MarkerType'] == "IntroEnd":
            MediaSource['IntroEndPositionTicks'] = Chapter["StartPositionTicks"]
        elif Chapter['MarkerType'] == "CreditsStart":
            MediaSource['CreditsPositionTicks'] = Chapter["StartPositionTicks"]
    else:
        if "Name" in Chapter:
            Chapter['Name'] = Chapter['Name'].replace("-", " ")

            if Chapter['Name'] == "Title Sequence" or Chapter['Name'] == "End Credits" or Chapter['Name'] == "Intro Start" or Chapter['Name'] == "Intro End":
                if Chapter['Name'] == "Intro Start" and not MediaSource['IntroStartPositionTicks']:
                    MediaSource['IntroStartPositionTicks'] = Chapter["StartPositionTicks"]
                elif Chapter['Name'] == "Intro End" and not MediaSource['IntroEndPositionTicks']:
                    MediaSource['IntroEndPositionTicks'] = Chapter["StartPositionTicks"]
                elif Chapter['Name'] == "End Credits" and not MediaSource['CreditsPositionTicks']:
                    MediaSource['CreditsPositionTicks'] = Chapter["StartPositionTicks"]

            elif not ChaptersGenerated:
                return
        else:
            Chapter["Name"] = "unknown"

    if Chapter["StartPositionTicks"] not in MediaSource['KodiChapters']:
        ChapterImage = utils.image_url(
            ServerId, Id, 'Chapter', Chapter.get('ImageTag', 'noimage'), "", Index)
        MediaSource['KodiChapters'][Chapter["StartPositionTicks"]] = ChapterImage

    return

# Detect generated chapters
def is_generated_chapter_set(Chapters):
    Index = 0
    NamePrefix = None
    MarkerTypes = ("IntroStart", "IntroEnd", "CreditsStart")
    MarkerNames = ("Title Sequence", "End Credits", "Intro Start", "Intro End")

    for Chapter in Chapters:
        Name = Chapter.get("Name", "").replace("-", " ")

        if Chapter.get("MarkerType") in MarkerTypes or Name in MarkerNames:
            continue

        if Chapter.get("MarkerType") not in (None, "Chapter"):
            continue

        if Chapter.get("StartPositionTicks", -1) != Index * 3000000000:
            return False

        if " " not in Name:
            return False

        Prefix, Number = Name.rsplit(" ", 1)

        if not Number.isdigit() or Number != str(Index + 1):
            return False

        if NamePrefix is None:
            NamePrefix = Prefix
        elif Prefix != NamePrefix:
            return False

        Index += 1

    return True

# Set Kodi artwork
def set_KodiArtwork(Item, ServerId, DynamicNode):
    Item['ParentLogoItemId'] = Item.get('ParentLogoItemId', None)
    Item['ParentLogoImageTag'] = Item.get('ParentLogoImageTag', None)
    Item['ParentBackdropItemId'] = Item.get('ParentBackdropItemId', None)
    Item['ParentBackdropImageTags'] = Item.get('ParentBackdropImageTags', [])
    Item['ImageTags'] = Item.get('ImageTags', [])
    Item['BackdropImageTags'] = Item.get('BackdropImageTags', [])
    Item['AlbumPrimaryImageTag'] = Item.get('AlbumPrimaryImageTag', None)
    Item['SeriesPrimaryImageTag'] = Item.get('SeriesPrimaryImageTag', None)
    Item['KodiArtwork'] = {'clearlogo': None, 'discart': None, 'landscape': None, 'thumb': None,
                          'poster': None, 'fanart': {}, 'favourite': None}

    if not DynamicNode and Item['Type'] == "Audio": # no artwork for synced song content (Kodi handels that based on Albumart etc.)
        if Item["AlbumPrimaryImageTag"] and "AlbumId" in Item:
            Item['KodiArtwork']['favourite'] = utils.image_url(ServerId, Item['AlbumId'], 'Primary', Item['AlbumPrimaryImageTag'], "MusicAlbum")

        return


    if Item['Type'] == "Studio":
        set_primary_artwork(Item, ServerId)
        Item['KodiArtwork']['thumb'] = Item['KodiArtwork']['favourite']
        return

    if Item['Type'] in ImageTagsMappings:
        for ImageTagsMapping in ImageTagsMappings[Item['Type']]:
            EmbyArtworkId = None
            EmbyArtworkTag = ""

            if ImageTagsMapping[0] in Item["ImageTags"]:
                if Item["ImageTags"][ImageTagsMapping[0]] and Item["ImageTags"][ImageTagsMapping[0]] != "None":
                    EmbyArtworkTag = Item["ImageTags"][ImageTagsMapping[0]]
                    EmbyArtworkId = Item['Id']
            elif f"{ImageTagsMapping[0]}ImageTag" in Item:
                ImageTagKey = f"{ImageTagsMapping[0]}ImageTag"

                if Item[ImageTagKey] and Item[ImageTagKey] != "None":
                    EmbyArtworkTag = Item[ImageTagKey]

                    if f"{ImageTagsMapping[0]}ItemId" in Item:
                        EmbyArtworkId = Item[f"{ImageTagsMapping[0]}ItemId"]
                    elif f"{ImageTagsMapping[0]}ImageItemId" in Item:
                        EmbyArtworkId = Item[f"{ImageTagsMapping[0]}ImageItemId"]
                    else:
                        if ImageTagsMapping[0] == "SeriesPrimary":
                            if "SeriesId" in Item:
                                EmbyArtworkId = Item["SeriesId"]
                        elif ImageTagsMapping[0] == "AlbumPrimary":
                            if "AlbumId" in Item:
                                EmbyArtworkId = Item["AlbumId"]

            if DynamicNode:
                if ImageTagsMapping[0] == "AlbumArtists" and "AlbumArtists" in Item and Item["AlbumArtists"] and Item["AlbumArtists"] != "None":
                    EmbyArtworkId = Item["AlbumArtists"][0]['Id']
                    EmbyArtworkTag = ""
                elif ImageTagsMapping[0] == "ArtistItems" and "ArtistItems" in Item and Item["ArtistItems"] and Item["ArtistItems"] != "None":
                    EmbyArtworkId = Item["ArtistItems"][0]['Id']
                    EmbyArtworkTag = ""

            if f"{ImageTagsMapping[0]}ImageTags" in Item:
                BackDropsKey = f"{ImageTagsMapping[0]}ImageTags"

                if BackDropsKey == "ParentBackdropImageTags":
                    EmbyBackDropsId = Item["ParentBackdropItemId"]
                else:
                    EmbyBackDropsId = Item.get("Id", None)

                if EmbyBackDropsId:
                    if Item[BackDropsKey] and Item[BackDropsKey] != "None":
                        if ImageTagsMapping[1] == "fanart": # Keep only the first backdrop.
                            if "fanart" not in Item['KodiArtwork']["fanart"]:
                                Item['KodiArtwork']["fanart"]["fanart"] = utils.image_url(ServerId, EmbyBackDropsId, 'Backdrop', Item[BackDropsKey][0], Item.get("Type", ""))

                        else:
                            if not Item['KodiArtwork'][ImageTagsMapping[1]]:
                                Item['KodiArtwork'][ImageTagsMapping[1]] = utils.image_url(ServerId, EmbyBackDropsId, ImageTagsMapping[0], Item[BackDropsKey][0], Item.get("Type", ""))

            if EmbyArtworkId:
                if ImageTagsMapping[1] == "fanart":
                    if "fanart" not in Item['KodiArtwork']["fanart"]:
                        Item['KodiArtwork']["fanart"]["fanart"] = utils.image_url(ServerId, EmbyArtworkId, ImageTagsMapping[0], EmbyArtworkTag, Item.get("Type", ""))
                else:
                    if not Item['KodiArtwork'][ImageTagsMapping[1]]:
                        Item['KodiArtwork'][ImageTagsMapping[1]] = utils.image_url(ServerId, EmbyArtworkId, ImageTagsMapping[0], EmbyArtworkTag, Item.get("Type", ""))


    if DynamicNode:
        if Item['Type'] == "Episode":
            if 'SeriesId' in Item and "SeriesPrimaryImageTag" in Item and Item["SeriesPrimaryImageTag"] and Item["SeriesPrimaryImageTag"] != "None":
                Item['KodiArtwork']['tvshow.poster'] = utils.image_url(ServerId, Item['SeriesId'], 'Primary', Item['SeriesPrimaryImageTag'], "Series")

            if 'ParentLogoItemId' in Item and "ParentLogoImageTag" in Item and Item["ParentLogoImageTag"] and Item["ParentLogoImageTag"] != "None":
                Item['KodiArtwork']['tvshow.clearlogo'] = utils.image_url(ServerId, Item['ParentLogoItemId'], 'Logo', Item['ParentLogoImageTag'], Item.get("Type", ""))

            if 'ParentBackdropItemId' in Item and "ParentBackdropImageTags" in Item and Item["ParentBackdropImageTags"]:
                Item['KodiArtwork']['tvshow.fanart'] = utils.image_url(ServerId, Item['ParentBackdropItemId'], 'Backdrop', Item['ParentBackdropImageTags'][0], Item.get("Type", ""))

    if Item['KodiArtwork']['poster']:
        Item['KodiArtwork']['favourite'] = Item['KodiArtwork']['poster']
    else:
        Item['KodiArtwork']['favourite'] = Item['KodiArtwork']['thumb']


def set_TracksByMediasourceName(Item):
    # Try to detect track number
    if 'IndexNumber' in Item and Item['IndexNumber']:
        return

    Item['IndexNumber'] = None

    if not Item['MediaSources']:
        return

    Temp = Item['MediaSources'][0]['Name']  # e.g. 01 - Artist - Title
    Temp = Temp.split("-")

    if len(Temp) > 1:
        Track = Temp[0].strip()

        if Track.isdigit():
            Item['IndexNumber'] = int(Track)  # remove leading zero e.g. 01

def delete_ContentItemMetadata(KodiItemId, SQLs, KodiType, All):
    KodiLibraryTagIds = SQLs["emby"].get_KodiSpecialTagIds()
    SQLs["video"].delete_links_actors(KodiItemId, KodiType)
    SQLs["video"].delete_links_director(KodiItemId, KodiType)
    SQLs["video"].delete_links_writer(KodiItemId, KodiType)
    SQLs["video"].delete_links_countries(KodiItemId, KodiType)
    SQLs["video"].delete_links_studios(KodiItemId, KodiType)
    SQLs["video"].delete_links_tags(KodiItemId, KodiType, KodiLibraryTagIds, All)
    SQLs["video"].delete_links_genres(KodiItemId, KodiType)
    SQLs["video"].delete_uniqueids(KodiItemId, KodiType)
    SQLs["video"].delete_ratings(KodiItemId, KodiType, All=All)
    SQLs["video"].common_db.delete_artwork(KodiItemId, KodiType)

def delete_ContentItemReferences(KodiItemId, KodiFileId, SQLs, KodiType, All, DeleteStreams):
    delete_ContentItemMetadata(KodiItemId, SQLs, KodiType, All)
    SQLs["video"].delete_bookmark(KodiFileId, 0) # Delete Chapter bookmarks

    if All: # Delete Resumepoints
        SQLs["video"].delete_bookmark(KodiFileId, 1)

    if DeleteStreams:
        SQLs["video"].delete_streams(KodiFileId)

    SQLs["video"].delete_stacktimes(KodiFileId)

    if KodiType == "movie":
        SQLs["video"].common_db.delete_artwork(KodiFileId, "videoversion")
        SQLs["video"].delete_videoversion_by_KodiId_notKodiFileId_KodiType(KodiItemId, KodiFileId, KodiType)


def set_VideoCommon(KodiItemId, KodiFileId, Item, SQLs, KodiType, PreserveFileState=False):
    SQLs["video"].common_db.add_artwork(Item['KodiArtwork'], KodiItemId, KodiType)
    SQLs["video"].add_countries_and_links(Item['ProductionLocations'], KodiItemId, KodiType)

    if not PreserveFileState:
        SQLs["video"].add_bookmarks(KodiFileId, Item['KodiRunTimeTicks'], Item['MediaSources'][0]['KodiChapters'])
        SQLs["video"].add_streams(KodiFileId, Item['MediaSources'][0]['KodiStreams']['Video'], Item['MediaSources'][0]['KodiStreams']['Audio'], Item['MediaSources'][0]['KodiStreams']['Subtitle'], Item['KodiRunTimeTicks'])

        if "KodiStackTimes" in Item:
            SQLs["video"].add_stacktimes(KodiFileId, Item['KodiStackTimes'])

def delete_ContentItem(KodiItemId, KodiFileId, Item, SQLs, KodiType, EmbyType):
    Delete = SQLs['emby'].remove_item(Item['Id'], EmbyType, Item['LibraryId'])

    if Delete and KodiItemId:  # KodiItemId can be None for multiversion content
        delete_ContentItemReferences(KodiItemId, KodiFileId, SQLs, KodiType, True, True)

    return Delete

def verify_content(Item, MediaType):
    if 'Name' not in Item:
        xbmc.log(f"EMBY.core.common: Skipping unnamed item {Item.get('Id')}", xbmc.LOGDEBUG)
        return False

    if 'Path' not in Item:
        xbmc.log(f"EMBY.core.common: Path not found in Item {Item['Id']}", xbmc.LOGDEBUG)
        return False

    if 'MediaSources' not in Item or not Item['MediaSources']:
        xbmc.log(f"EMBY.core.common: No mediasources found for {MediaType}: {Item['Id']}", xbmc.LOGDEBUG)
        return False

    return True


def set_Favorite(Item):
    if "UserData" in Item and "IsFavorite" in Item['UserData'] and Item['UserData']['IsFavorite']:
        Item['IsFavorite'] = int(Item['UserData']['IsFavorite'])
    elif 'IsFavorite' in Item and Item['IsFavorite']:
        Item['IsFavorite'] = int(Item['IsFavorite'])
    elif "EmbyFavourite" in Item and Item['EmbyFavourite']:
        Item['IsFavorite'] = 1
    else:
        Item['IsFavorite'] = 0

def set_PresentationUniqueKey(Item):
    if 'PresentationUniqueKey' in Item and Item['PresentationUniqueKey']:
        Item['PresentationUniqueKey'] = Item['PresentationUniqueKey'].replace("-", "_").replace(" ", "")
    else:
        Item['PresentationUniqueKey'] = None

def set_MusicGenre_links(KodiItemId, SQLs, KodiType, MetaDataItems, Index):
    for Order, MetaDataItem in enumerate(MetaDataItems):
        MetaDataItemKodiIds = SQLs["emby"].get_item_by_id(MetaDataItem['Id'], "MusicGenre")

        if MetaDataItemKodiIds:
            MetaDataItemKodiIds = MetaDataItemKodiIds[1].split(";")

            if MetaDataItemKodiIds:
                if Index == 0:
                    SQLs["music"].add_genre_link(MetaDataItemKodiIds[0], KodiItemId, Order)
                else:

                    SQLs["video"].add_genre_link(MetaDataItemKodiIds[1], KodiItemId, KodiType)

def set_Genre_links(KodiItemId, SQLs, KodiType, MetaDataItems):
    for MetaDataItem in MetaDataItems:
        MetaDataItemKodiId = SQLs["emby"].get_item_by_id(MetaDataItem['Id'], "Genre")

        if MetaDataItemKodiId:
            SQLs["video"].add_genre_link(MetaDataItemKodiId[1], KodiItemId, KodiType)

def get_PersonMapping(EmbyId, SQLs, PersonMappings):
    # Reuse only current-item records; leave non-string input handling to SQLite.
    if PersonMappings is not None and type(EmbyId) is str and EmbyId in PersonMappings:
        return PersonMappings[EmbyId]

    return SQLs["emby"].get_item_by_id(EmbyId, "Person")

def set_Writer_links(KodiItemId, SQLs, KodiType, MetaDataItems, PersonMappings=None):
    for MetaDataItem in MetaDataItems:
        MetaDataItemKodiId = get_PersonMapping(MetaDataItem['Id'], SQLs, PersonMappings)

        if MetaDataItemKodiId:
            SQLs["video"].add_writer_link(MetaDataItemKodiId[1], KodiItemId, KodiType)

def set_Director_links(KodiItemId, SQLs, KodiType, MetaDataItems, PersonMappings=None):
    for MetaDataItem in MetaDataItems:
        MetaDataItemKodiId = get_PersonMapping(MetaDataItem['Id'], SQLs, PersonMappings)

        if MetaDataItemKodiId:
            SQLs["video"].add_director_link(MetaDataItemKodiId[1], KodiItemId, KodiType)

def set_Studio_links(KodiItemId, SQLs, KodiType, MetaDataItems):
    for MetaDataItem in MetaDataItems:
        MetaDataItemKodiId = SQLs["emby"].get_item_by_id(MetaDataItem['Id'], "Studio")

        if MetaDataItemKodiId:
            SQLs["video"].add_studio_link(MetaDataItemKodiId[1], KodiItemId, KodiType)

def set_Tag_links(KodiItemId, SQLs, KodiType, MetaDataItems):
    for MetaDataItem in MetaDataItems:
        MetaDataItemKodiId = SQLs["emby"].get_item_by_id(MetaDataItem['Id'], "Tag")

        if MetaDataItemKodiId:
            SQLs["video"].add_tag_link(MetaDataItemKodiId[1], KodiItemId, KodiType)

def set_Actor_links(KodiItemId, SQLs, KodiType, MetaDataItems, PersonMappings=None):
    for Order, MetaDataItem in enumerate(MetaDataItems):
        MetaDataItemKodiId = get_PersonMapping(MetaDataItem['Id'], SQLs, PersonMappings)

        if MetaDataItemKodiId:
            SQLs["video"].add_actor_link(MetaDataItemKodiId[1], KodiItemId, KodiType, MetaDataItem["Role"], Order)

def set_Actor_MusicArtist_links(KodiItemId, SQLs, KodiType, MetaDataItems, LibraryId):
    for Order, MetaDataItem in enumerate(MetaDataItems):
        ArtistData = SQLs["emby"].get_item_by_id(MetaDataItem['Id'], "MusicArtist")

        if ArtistData:
            MetaDataItemKodiId = ArtistData[1].split(";")

            if MetaDataItemKodiId:
                MetaDataItemKodiId = MetaDataItemKodiId[1].split(",")
                MetaDataItemLibraryId = ArtistData[3].split(";")[1]
                MetaDataItemLibraryId = MetaDataItemLibraryId.split(",")
                Index = MetaDataItemLibraryId.index(LibraryId)
                SQLs["video"].add_actor_link(MetaDataItemKodiId[Index], KodiItemId, KodiType, "Artist", Order)

def set_MusicArtist_links(KodiItemId, SQLs, MetaDataItems, LibraryId, ArtistRole):
    for Order, MetaDataItem in enumerate(MetaDataItems):
        ArtistData = SQLs["emby"].get_item_by_id(MetaDataItem['Id'], "MusicArtist")

        if ArtistData:
            MetaDataItemKodiId = ArtistData[1].split(";")

            if MetaDataItemKodiId:
                MetaDataItemKodiId = MetaDataItemKodiId[0].split(",")
                MetaDataItemLibraryId = ArtistData[3].split(";")[0]
                MetaDataItemLibraryId = MetaDataItemLibraryId.split(",")
                Index = MetaDataItemLibraryId.index(LibraryId)

                if ArtistRole:
                    SQLs["music"].add_musicartist_link(MetaDataItemKodiId[Index], KodiItemId, ArtistRole, Order, MetaDataItem['Name'])
                else:
                    SQLs["music"].add_albumartist_link(MetaDataItemKodiId[Index], KodiItemId, Order, MetaDataItem['Name'])

def set_ItemsDependencies(Item, SQLs, WorkerObject, Library, EmbyType, IncrementalSync,
                          LibraryId, PlaylistId="", ExistingParents=None):
    AddSubItem = False
    SubItemId = f'{EmbyType}Id'

    if SubItemId not in Item or not Item[SubItemId]:
        AddSubItem = True
    else:
        if EmbyType == "MusicAlbum":
            Exists = SQLs["emby"].get_item_exists_multi_library(Item[SubItemId], EmbyType, LibraryId)
        elif ExistingParents is not None and EmbyType in ("Series", "Season"):
            Parent = SQLs["emby"].get_item_by_id(Item[SubItemId], EmbyType)
            Exists = bool(Parent)

            if Exists:
                # A row with a NULL KodiId still counts as an existing dependency.
                ExistingParents[EmbyType] = Parent
        else:
            Exists = SQLs["emby"].get_item_exists_by_id(Item[SubItemId], EmbyType)

        if not Exists:
            if ExistingParents is not None:
                ExistingParents.clear()

            SubItem = load_Item(Item[SubItemId], EmbyType, Library, "set_ItemsDependencies", LibraryId, SQLs)

            if SubItem:
                SubItem['PlaylistId'] = PlaylistId
                WorkerObject.change(SubItem, IncrementalSync)
                Item[SubItemId] = SubItem['Id']
            else:
                AddSubItem = True

            del SubItem

    if AddSubItem:
        if ExistingParents is not None:
            ExistingParents.clear()

        Item[SubItemId] = None

        if Item['PresentationUniqueKey'] and EmbyType != "MusicAlbum":
            PresentationData = Item['PresentationUniqueKey'].split("_")

            if Item['Type'] == "Episode" and len(PresentationData) >= 2: # multiepisode:
                SearchPresentationUniqueKey = "_".join(PresentationData[:-1])
                Item[SubItemId] = SQLs["emby"].get_EmbyId_by_EmbyPresentationKey(SearchPresentationUniqueKey, EmbyType)

        if not Item[SubItemId]:
            Item[SubItemId] = utils.MappingIds[EmbyType]

            if EmbyType == "MusicAlbum":
                Item[SubItemId] = f"{Item[SubItemId]}{Item['Id']}"

                if 'AlbumArtists' in Item and Item['AlbumArtists']:
                    WorkerObject.change({"LibraryId": Item["LibraryId"], "Type": EmbyType, "Id": Item[SubItemId], "Name": "--NO INFO--", "SortName": "--NO INFO--", "DateCreated": utils.currenttime(), "ProviderIds": {}, 'ParentId': None, "AlbumArtists": Item['AlbumArtists'], "ArtistItems": [], "AlbumArtist": Item['AlbumArtist']}, IncrementalSync)
                else:
                    WorkerObject.change({"LibraryId": Item["LibraryId"], "Type": EmbyType, "Id": Item[SubItemId], "Name": "--NO INFO--", "SortName": "--NO INFO--", "DateCreated": utils.currenttime(), "ProviderIds": {}, 'ParentId': None, "AlbumArtists": Item['ArtistItems'], "ArtistItems": [], "AlbumArtist": Item['MusicArtist']}, IncrementalSync)
            elif EmbyType == "Season":
                Item["SeasonId"] = f"{Item[SubItemId]}{Item['Id']}"
                WorkerObject.change({"LibraryId": Item["LibraryId"], "Type": EmbyType, "Id": Item["SeasonId"], "SeriesId": Item["SeriesId"], "Name": "--NO INFO--", "SortName": "--NO INFO--", "DateCreated": utils.currenttime(), "ProviderIds": {}, 'ParentId': None}, IncrementalSync)
            else:
                WorkerObject.change({"LibraryId": Item["LibraryId"], "Type": EmbyType, "Id": Item[SubItemId], "Name": "--NO INFO--", "SortName": "--NO INFO--", "DateCreated": utils.currenttime(), "ProviderIds": {}, 'Path': Item.get('Path', "/--NO INFO--/--NO INFO--/"), 'ParentId': None}, IncrementalSync)

def set_MetaItems(Item, SQLs, WorkerObject, Library, EmbyType, MetaDataId, KodiContentCategory, IncrementalSync, LibraryId):
    if EmbyType == "Studio":
        StudioItems = (Item.get(MetaDataId) or []) if Item.get('Type') == "Series" else []
        Item['Studios'] = []
        Item['Studio'] = None
        for MetaItem in StudioItems:
            Record = SQLs["emby"].get_item_by_id(MetaItem['Id'], "Studio")
            if not Record:
                SubItem = load_Item(MetaItem['Id'], "Studio", Library, "set_MetaItems", LibraryId, SQLs)
                if SubItem:
                    SubItem['StudioForSeries'] = True
                    WorkerObject.change(SubItem, IncrementalSync)
                    Record = SQLs["emby"].get_item_by_id(MetaItem['Id'], "Studio")
            if Record:
                SQLs["emby"].update_EmbyLibraryMapping(MetaItem['Id'], LibraryId)
                if Record[1]:
                    Item['Studios'].append(MetaItem)
        Item['Studio'] = " / ".join(MetaItem['Name'] for MetaItem in Item['Studios']) or None
        return

    AddSubItem = False
    Names = ()

    if MetaDataId not in Item or not Item[MetaDataId]:
        AddSubItem = True
    else:
        for MetaItem in Item[MetaDataId]:
            if KodiContentCategory in ("music", "video"): # content defined for video and/or music (content included in Kodi's MyMusic.db and MyVideo.db)
                if KodiContentCategory == "music":
                    Index = 0
                else:
                    Index = 1

                Exists = SQLs["emby"].get_item_exists_multi_db(MetaItem['Id'], EmbyType, LibraryId, Index)
            else: # global unique content
                Exists = SQLs["emby"].get_item_exists_by_id(MetaItem['Id'], EmbyType)

            if Exists:
                Names += (MetaItem['Name'],)
                continue

            SubItem = load_Item(MetaItem["Id"], EmbyType, Library, "set_MetaItems", LibraryId, SQLs)

            if SubItem:
                Names += (MetaItem['Name'],)

                if WorkerObject:
                    WorkerObject.change(SubItem, IncrementalSync)


                continue

            AddSubItem = True

    if AddSubItem:
        Names += ("--NO INFO--",)
        AddSubItemId = utils.MappingIds[EmbyType]

        if WorkerObject:
            WorkerObject.change({"LibraryId": LibraryId, "Type": EmbyType, "Id": AddSubItemId, "Name": "--NO INFO--", 'SortName': "--NO INFO--", "DateCreated": utils.currenttime(), "ProviderIds": {}}, IncrementalSync)

        Item[MetaDataId] = [{"Name": "--NO INFO--", "Id": AddSubItemId, "Memo": f"no info {EmbyType}"}]


    Item[EmbyType] = " / ".join(Names)

def set_people(Item, SQLs, PersonObject, Library, IncrementalSync, PersonMappings=None):
    Item['WritersItems'] = ()
    Item['DirectorsItems'] = ()
    Item['CastItems'] = ()
    Writers = ()
    Directors = ()
    CastLimit = 20 if Item['Type'] in ("Movie", "Series") else None

    if Item['Type'] == "Episode":
        CastLimit = 0

    if "People" in Item:
        for People in Item['People']:
            PeopleType = People.get('Type')

            # Filter before any database lookup or missing-person query.
            if PeopleType in ("Actor", "GuestStar"):
                if CastLimit is not None and len(Item['CastItems']) >= CastLimit:
                    continue
            elif PeopleType not in ("Writer", "Director"):
                continue

            if People.get('Name') and People.get('Id'):
                if PersonMappings is not None and type(People['Id']) is str:
                    PersonData = get_PersonMapping(People['Id'], SQLs, PersonMappings)
                    Exists = bool(PersonData)

                    if Exists:
                        PersonMappings[People['Id']] = PersonData
                else:
                    Exists = SQLs["emby"].get_item_exists_by_id(People['Id'], "Person")

                if not Exists:
                    # Creation can change mappings; never retain a missing-person snapshot.
                    if PersonMappings is not None:
                        PersonMappings.clear()

                    # The work already supplies everything needed for the Kodi person record.
                    SubItem = {'Id': People['Id'], 'Name': People['Name'], 'Type': "Person",
                               'PersonForItem': True, 'ImageTags': {}}

                    if People.get('PrimaryImageTag'):
                        SubItem['ImageTags']['Primary'] = People['PrimaryImageTag']

                    PersonObject.change(SubItem, IncrementalSync)

                    if not SubItem.get('KodiItemId'):
                        continue

                if PeopleType == "Writer":
                    Item['WritersItems'] += ({"Name": People['Name'], "Id": People['Id'], "KodiType": "actor"},)
                    Writers += (People['Name'],)
                elif PeopleType == "Director":
                    Item['DirectorsItems'] += ({"Name": People['Name'], "Id": People['Id'], "KodiType": "actor"},)
                    Directors += (People['Name'],)
                elif People['Type'] in ("Actor", "GuestStar"):
                    if 'Role' in People:
                        role = People['Role']
                    else:
                        if People['Type'] == "GuestStar":
                            role = "Guest Star"
                        else:
                            role = "Actor"

                    Item['CastItems'] += ({"Name": People['Name'], "Id": People['Id'], "KodiType": "actor", "Role": role},)

    if Writers:
        Item['Writers'] = " / ".join(Writers)
    else:
        Item['Writers'] = None

    if Directors:
        Item['Directors'] = " / ".join(Directors)
    else:
        Item['Directors'] = None

def get_MusicArtistInfos(Item, ArtistType, SQLs):
    Artists = []
    SortNames = []
    KodiIds = []

    if ArtistType in Item:
        for ArtistItem in Item[ArtistType]:
            Artists.append(ArtistItem['Name'])
            ArtistItem['KodiId'] = SQLs["emby"].get_KodiId_by_EmbyId_multi_db(ArtistItem['Id'], "MusicArtist", "music")
            KodiIds.append(ArtistItem['KodiId'])
            ArtistSortname = SQLs["music"].get_ArtistSortname(ArtistItem['KodiId'])

            if ArtistSortname:
                SortNames.append(ArtistSortname)
            else:
                if ArtistItem['Name']:
                    SortNames.append(ArtistItem['Name'])

        Item[f"{ArtistType}SortName"] = " / ".join(SortNames)
        Item[f"{ArtistType}Name"] = " / ".join(Artists)
        Item[f"{ArtistType}KodiId"] = ",".join(KodiIds)

def update_multiversion(EmbyDB, EmbyType, EmbyItemId, LibraryId, PresentationUniqueKey):
    if not LibraryId: # Websocket removed item
        StackedIds = EmbyDB.get_EmbyIds_by_EmbyPresentationKey(PresentationUniqueKey, EmbyType)

        if StackedIds: # multi version force update

            for StackedId in StackedIds:  # StackedId[0] = EmbyId
                for LibraryIdStacked in StackedId[1]:
                    EmbyDB.add_RemoveItem(StackedId[0], LibraryIdStacked[0])
                    EmbyDB.add_UpdateItem(StackedId[0], EmbyType, LibraryIdStacked[0])

def update_boxsets(IncrementalSync, ParentId, LibraryId, SQLs, Library):
    if IncrementalSync:
        for BoxSet in Library.API.get_Items(ParentId, ("BoxSet",), True, {'GroupItemsIntoCollections': True}, "", None, True): # Workaround: Emby server does not respect ParentId without Userdata
            SQLs["emby"].add_UpdateItem(BoxSet['Id'], "BoxSet", LibraryId)

# Choose the item's primary image, including Studio's Thumb fallback.

def set_primary_artwork(Item, ServerId):
    if 'KodiArtwork' not in Item:
        Item['KodiArtwork'] = {}

    Item['KodiArtwork']['favourite'] = utils.image_url(ServerId, Item['Id'], 'Primary', 'noimage', Item.get("Type", ""))

    if 'ImageTags' in Item and Item['ImageTags']:
        ItemId = Item['Id'].replace(utils.MappingIds['Tag'], '')

        if "Primary" in Item['ImageTags']:
            Item['KodiArtwork']['favourite'] = utils.image_url(ServerId, ItemId, 'Primary', Item['ImageTags']['Primary'], Item.get("Type", ""))
        elif Item.get('Type') == "Studio" and Item['ImageTags'].get('Thumb'):
            Item['KodiArtwork']['favourite'] = utils.image_url(ServerId, ItemId, 'Thumb', Item['ImageTags']['Thumb'], Item.get("Type", ""))


def validate_FavoriteImage(Item):
    if 'KodiArtwork' not in Item:
        Item['KodiArtwork'] = {}

    if 'favourite' not in Item['KodiArtwork']:
        Item['KodiArtwork']['favourite'] = None


def add_multiversion(Item, EmbyType, Library, SQLs, EmbyMusicArtistIds, EmbyMusicGenreIds):
    PlaybackSources = versions.sort_sources(Item['MediaSources'])
    PreferredSourceId = PlaybackSources[0]['Id']
    MovieDefault = None

    for MediaSource in PlaybackSources:
        if MediaSource['Type'] == "Default":
            continue

        # Get additional data, actually ParentId and probably PresentationUniqueKey could differ to item's core info
        if 'ItemId' not in MediaSource:
            ItemReferenced = load_Item(MediaSource['Id'], EmbyType, Library, "add_multiversion", None, SQLs)

            if not ItemReferenced:  # Server restarted
                xbmc.log(f"EMBY.core.common: Referenced media version not found: {MediaSource['Id']}", xbmc.LOGDEBUG)
                continue

            EmbyId = ItemReferenced['Id']
        else:
            EmbyId = MediaSource['ItemId']

        # Delete old multiversions
        ItemDatas = SQLs['emby'].get_item_by_id(EmbyId, EmbyType)

        if ItemDatas: # Same content assigned to multiple libraries
            if ItemDatas[1]:
                KodiItemIds = str(ItemDatas[1]).split(",")
                KodiFileIds = str(ItemDatas[3]).split(",")
            else: # Linked multiversion
                KodiItemIds = [None]
                KodiFileIds = [None]

            ItemReferenced = copy.Object(Item)

            if len(KodiItemIds) > 1: # Multilib item, get LibraryId (e.g. Musicvideos)
                LibraryIds = ItemDatas[7].split(",")
                Index = LibraryIds.index(Item['LibraryId'])
            else:
                Index = 0

            ItemReferenced.update({'Id': EmbyId, 'MediaSources': [MediaSource], "KodiFileId": KodiFileIds[Index], "KodiItemId": KodiItemIds[Index], 'LibraryId': Item['LibraryId']})

            # Remove old Kodi video-db references
            if ItemReferenced['KodiItemId'] and (str(Item['KodiItemId']) != str(ItemReferenced['KodiItemId']) or str(Item['KodiFileId']) != str(ItemReferenced['KodiFileId'])):
                delete_ContentItem(ItemReferenced['KodiItemId'], ItemReferenced['KodiFileId'], ItemReferenced, SQLs, utils.EmbyTypeMapping[EmbyType], EmbyType)

                if SQLs['video']: # Video database is unavailable for audio-only synchronization.
                    if EmbyType == "Episode":
                        SQLs['video'].delete_episode(ItemReferenced['KodiItemId'], ItemReferenced['KodiFileId'])
                    elif EmbyType in ("Movie", "Video"):
                        SQLs['video'].delete_movie(ItemReferenced['KodiItemId'], ItemReferenced['KodiFileId'])
                    elif EmbyType == "MusicVideo":
                        SQLs['video'].delete_musicvideos(ItemReferenced['KodiItemId'], ItemReferenced['KodiFileId'])

        # Add references
        ItemReferenced = copy.Object(Item)
        ItemReferenced.update({'Id': EmbyId, 'MediaSources': [MediaSource]})

        if EmbyType == "Episode":
            SQLs['emby'].add_reference_episode(ItemReferenced['Id'], ItemReferenced['LibraryId'], None, None, None, ItemReferenced['PresentationUniqueKey'], MediaSource['Path'], None)
        elif EmbyType == "MusicVideo":
            SQLs["emby"].add_reference_musicvideo(ItemReferenced['Id'], ItemReferenced['LibraryId'], None, None, ItemReferenced['PresentationUniqueKey'], MediaSource['Path'], None, Item['LibraryIds'], EmbyMusicArtistIds, EmbyMusicGenreIds)
        elif EmbyType == "Movie":
            ItemReferenced['KodiFileId'] = SQLs["video"].create_entry_file()
            EmbyIdBackup = ItemReferenced['Id'] # workaround for Emby limitiation not unifying progress by version and not respecting subversion specific ItemId
            ItemReferenced['Id'] = Item['Id'] # workaround for Emby limitiation not unifying progress by version and not respecting subversion specific ItemId
            set_path_filename(ItemReferenced, Library.ServerData['ServerId'], MediaSource)
            ItemReferenced['Id'] = EmbyIdBackup # workaround for Emby limitiation not unifying progress by version and not respecting subversion specific ItemId
            ItemReferenced['KodiPathId'] = SQLs['video'].get_add_path(ItemReferenced['KodiPath'], "movies")
            SQLs["video"].add_bookmarks(ItemReferenced['KodiFileId'], MediaSource['KodiRunTimeTicks'], MediaSource['KodiChapters'])
            SQLs["video"].add_streams(ItemReferenced['KodiFileId'], MediaSource['KodiStreams']['Video'], MediaSource['KodiStreams']['Audio'], MediaSource['KodiStreams']['Subtitle'], MediaSource['KodiRunTimeTicks'])
            SQLs["video"].common_db.add_artwork(ItemReferenced['KodiArtwork'], ItemReferenced['KodiFileId'], "videoversion")
            SQLs["video"].add_movie_version(Item['KodiItemId'], ItemReferenced['KodiFileId'], ItemReferenced['KodiPathId'], ItemReferenced['KodiFilename'], ItemReferenced['KodiDateCreated'], ItemReferenced['KodiStackedFilename'], MediaSource['Name'], "movie", "regular")
            SQLs['emby'].add_reference_movie(ItemReferenced['Id'], Item['LibraryId'], Item['KodiItemId'], ItemReferenced['KodiFileId'], ItemReferenced['PresentationUniqueKey'], MediaSource['Path'], ItemReferenced['KodiPathId'])

            if MediaSource['Id'] == PreferredSourceId:
                MovieDefault = (ItemReferenced['KodiFileId'], ItemReferenced['KodiPathId'], ItemReferenced['KodiPath'])
        elif EmbyType == "Video":
            SQLs['emby'].add_reference_video(ItemReferenced['Id'], Item['LibraryId'], None, None, ItemReferenced['ParentId'], ItemReferenced['PresentationUniqueKey'], MediaSource['Path'], None)

    # Update video version
    if MovieDefault:
        SQLs["video"].update_default_movieversion(Item['KodiItemId'], *MovieDefault)

def load_Item(ItemId, EmbyType, Library, WorkerName, LibraryId, SQLs):
    if ItemId in CachedItemsMissing:
        Item = CachedItemsMissing[ItemId]
        Item['LibraryId'] = LibraryId
    else:
        Item = Library.API.get_Item(ItemId, (EmbyType,), False, False, False) # Do not load userdata, as it's slow

        if Item:
            Item['LibraryId'] = LibraryId

            if 'music' in SQLs and SQLs['music']:
                KodiDB = 'music'
            elif 'video' in SQLs and SQLs['video']:
                KodiDB = 'video'
            else:
                KodiDB = ''

            SQLs["emby"].add_UpdateItem(Item['Id'], Item['Type'], Item['LibraryId'], KodiDB) # Resync items (with userdata) but grouped (faster than single Id queries)
            CachedItemsMissing[ItemId] = Item

    return Item

def is_number(Value):
    return Value.replace('.', '', 1).isdigit()

def get_Artist_Ids(Item, ArtistItems, AlbumArtists, Composers):
    EmbyMusicArtistIds = set()

    if ArtistItems:
        for ArtistItem in Item.get('ArtistItems', ()):
            EmbyMusicArtistIds.add(str(ArtistItem['Id']))

    if AlbumArtists:
        for AlbumArtist in Item.get('AlbumArtists', ()):
            EmbyMusicArtistIds.add(str(AlbumArtist['Id']))

    if Composers:
        for Composer in Item.get('Composers', ()):
            EmbyMusicArtistIds.add(str(Composer['Id']))

    return EmbyMusicArtistIds

def get_MusicGenre_Ids(Item):
    EmbyMusicGenreIds = set()

    for GenreItem in Item.get('GenreItems', ()):
        EmbyMusicGenreIds.add(str(GenreItem['Id']))

    return EmbyMusicGenreIds

def remove_old_EmbyMusicArtist(EmbyDB, ItemId, LibraryId, EmbyMusicArtistIds, MusicArtistObject, IncrementalSync):
    EmbyMusicArtistIdsOld = EmbyDB.get_Linked_EmbyMusicArtists(ItemId, LibraryId)

    for EmbyMusicArtistIdOld in EmbyMusicArtistIdsOld:
        if str(EmbyMusicArtistIdOld) not in EmbyMusicArtistIds:
            MusicArtistObject.remove({'Id': EmbyMusicArtistIdOld, 'LibraryId': LibraryId}, IncrementalSync)

def remove_old_EmbyMusicGenre(EmbyDB, ItemId, LibraryId, EmbyMusicGenreIds, MusicGenreObject, IncrementalSync):
    EmbyMusicGenreIdsOld = EmbyDB.get_Linked_EmbyMusicGenres(ItemId, LibraryId)

    for EmbyMusicGenreIdOld in EmbyMusicGenreIdsOld:
        if str(EmbyMusicGenreIdOld) not in EmbyMusicGenreIds:
            MusicGenreObject.remove({'Id': EmbyMusicGenreIdOld, 'LibraryId': LibraryId}, IncrementalSync)

def remove_old_EmbyMusicAlbum(EmbyDB, ItemId, LibraryId, MusicAlbumId, MusicAlbumObject, IncrementalSync):
    EmbyMusicAlbumIdOld = EmbyDB.get_Linked_EmbyMusicAlbum(ItemId, LibraryId)

    if EmbyMusicAlbumIdOld and str(MusicAlbumId) != str(EmbyMusicAlbumIdOld):
        MusicAlbumObject.remove({'Id': EmbyMusicAlbumIdOld, 'LibraryId': LibraryId}, IncrementalSync)

def delete_MusicAlbum_Links(LibraryId, Links, MusicAlbumObject, IncrementalSync, EmbyDB):
    if Links["EmbyMusicAlbumId"]:
        if not EmbyDB.isLinked_EmbyMusicAlbumId(LibraryId, Links["EmbyMusicAlbumId"]):
            MusicAlbumObject.remove({'Id': Links["EmbyMusicAlbumId"], 'LibraryId': LibraryId}, IncrementalSync)

def delete_MusicArtist_Links(LibraryId, Links, MusicArtistObject, IncrementalSync, EmbyDB):
    for EmbyMusicArtistId in Links["EmbyMusicArtistId"]:
        if not EmbyDB.isLinked_EmbyMusicArtistId(LibraryId, EmbyMusicArtistId):
            MusicArtistObject.remove({'Id': EmbyMusicArtistId, 'LibraryId': LibraryId}, IncrementalSync)

def delete_MusicGenre_Links(LibraryId, Links, MusicGenreObject, IncrementalSync, EmbyDB):
    for EmbyMusicGenreId in Links["EmbyMusicGenreId"]:
        if not EmbyDB.isLinked_EmbyMusicGenreId(LibraryId, EmbyMusicGenreId):
            MusicGenreObject.remove({'Id': EmbyMusicGenreId, 'LibraryId': LibraryId}, IncrementalSync)

# Array format for LibraryIds: "LibraryId1,LibraryId2;LibraryId3,LibraryId4". ";" is the seperator between Kodi's MyMusic.db and MyVideo.db. "," is the seperator for Emby's librarys
def get_Ids_MultiContent(IdsStr):
    if IdsStr:
        Ids = IdsStr.split(";")

        if Ids[0]:
            Ids[0] = Ids[0].split(",")
        else:
            Ids[0] = []

        if Ids[1]:
            Ids[1] = Ids[1].split(",")
        else:
            Ids[1] = []
    else:
        Ids = [[], []]

    return Ids

def add_Ids_MultiContent(Ids, Id, Index):
    Ids[Index].append(str(Id))
    IdsTemp = copy.Object(Ids)
    IdsTemp[1] = ",".join(Ids[1])
    IdsTemp[0] = ",".join(Ids[0])
    IdsTemp = ";".join(IdsTemp)
    return IdsTemp

def del_Ids_MultiContent(Ids, Id, Index):
    SubIndex = Ids[Index].index(str(Id))
    del Ids[Index][SubIndex]
    IdsTemp = copy.Object(Ids)
    IdsTemp[1] = ",".join(Ids[1])
    IdsTemp[0] = ",".join(Ids[0])
    IdsTemp = ";".join(IdsTemp)
    return IdsTemp, SubIndex

def get_Ids_SingleContent(IdsStr):
    if IdsStr:
        Ids = IdsStr.split(",")
    else:
        Ids = []

    return Ids

def add_Ids_SingleContent(Ids, Id):
    Ids.append(str(Id))
    return ",".join(Ids)

def del_Ids_SingleContent(Ids, Id):
    SubIndex = Ids.index(str(Id))
    del Ids[SubIndex]
    return ",".join(Ids)

def get_Ids_MultiContentUnique(IdsStr):
    if IdsStr:
        Ids = IdsStr.split(";")
    else:
        Ids = ["", ""]

    return Ids

def add_Ids_MultiContentUnique(Ids, Index, Id):
    Ids[Index] = str(Id)
    return ";".join(Ids)

def del_Ids_MultiContentUnique(Ids, Index):
    Ids[Index] = ""
    return ";".join(Ids)

def verify_KodiIds(Item, IncrementalSync, CheckKodiFileId):
    if CheckKodiFileId:
        if 'KodiFileId' not in Item or not Item['KodiFileId']: # Not integrated content (Kodi's database)

            return False

    if 'KodiItemId' not in Item or not Item['KodiItemId']: # Not integrated content (Kodi's database)

        return False

    return True
