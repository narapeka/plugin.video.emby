import threading
import os
import tempfile
import shutil
import json
import re
from urllib.parse import quote, unquote, urlsplit
from datetime import datetime, timezone

import xbmcvfs
import xbmc
import xbmcaddon
import xbmcgui
from . import artwork

Addon = xbmcaddon.Addon("plugin.service.emby-next-gen")
addon_version = Addon.getAddonInfo('version')
addon_name = Addon.getAddonInfo('name')
CustomDialogParameters = (Addon.getAddonInfo('path'), "default", "1080i")
WidgetsRefreshLock = threading.Lock()
MappingIds = {'Season': "999999989", 'Series': "999999990", 'MusicAlbum': "999999991", 'MusicGenre': "999999992", "Studio": "999999994", "Tag": "999999993", "Genre": "999999995", "MusicArtist": "999999996"}
MappingIdsListKeys = list(MappingIds.keys())
EmbyTypeMapping = {"Person": "actor", "Video": "movie", "Movie": "movie", "Series": "tvshow", "Season": "season", "Episode": "episode", "Audio": "song", "MusicAlbum": "album", "MusicArtist": "artist", "Genre": "genre", "MusicGenre": "genre", "Tag": "tag" , "Studio": "studio" , "BoxSet": "set", "Folder": "folder", "MusicVideo": "musicvideo", "Playlist": "Playlist"}
FavoriteTypes = ("Movie", "Video", "Series", "Season", "Episode", "MusicVideo",
                 "Audio", "MusicAlbum", "MusicArtist", "BoxSet", "Playlist")
KodiTypeMapping = {"actor": "Person", "tvshow": "Series", "season": "Season", "episode": "Episode", "song": "Audio", "album": "MusicAlbum", "artist": "MusicArtist", "genre": "Genre", "tag": "Tag", "studio": "Studio" , "set": "BoxSet", "musicvideo": "MusicVideo", "playlist": "Playlist", "movie": "Movie", "videoversion": "Video", "video": "Video"}
ContentTypes = {"Movie": "video", "Series": "video", "Season": "video", "Episode": "video", "Genre": "video", "Video": "video", "MusicVideo": "video", "Audio": "audio", "MusicAlbum": "audio", "audio": "audio", "podcasts": "audio", "audiobooks": "audio", "playlistsaudio": "audio", "playlistsvideo": "video", "rootvideo": "video", "rootaudio": "audio", "music": "audio", "homevideos": "video", "musicvideos": "video", "movies": "video", "tvshows": "video", "mixedvideo": "video", "videos": "video", "Person": "video", "Audios": "audio", "Videos": "video"}
icon = "special://home/addons/plugin.service.emby-next-gen/resources/icon.png"
ForbiddenCharecters = {}

for Char in ("/", "<", ">", ":", '"', "\\", "|", "?", "*", " ", "&", chr(0), chr(1), chr(2), chr(3), chr(4), chr(5), chr(6), chr(7), chr(8), chr(9), chr(10), chr(11), chr(12), chr(13), chr(14), chr(15), chr(16), chr(17), chr(18), chr(19), chr(20), chr(21), chr(22), chr(23), chr(24), chr(25), chr(26), chr(27), chr(28), chr(29), chr(30), chr(31)):
    CharId = ord(Char)
    ForbiddenCharecters[CharId] = "_"

ENC_MAP = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;"}
ENC_RE = re.compile(r'[&<>"\']')
DEC_MAP = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": "\"", "&apos;": "'"}
DEC_RE = re.compile(r"&amp;|&lt;|&gt;|&quot;|&apos;")
AutoplaySettings = []
FilesizeSuffixes = ('B', 'KB', 'MB', 'GB', 'TB')
EmbyServers = {}
EmbyServersBan = set()
EmbyServerIds = []
ItemSkipUpdate = []
MinimumVersion = "12.5.0"
EmbyServerVersionResync = "4.9.0.25"
device_name = "Kodi"
displayMessage = 1000
startupDelay = 0
DEFAULT_CURL_TIMEOUT = 5
curltimeouts = DEFAULT_CURL_TIMEOUT
MinimumSetup = ""
restartMsg = False
enableContextSettingsOptions = False
enableContextRefreshOptions = True
autoSelectHighestPlaybackResolution = False
enableSkipIntro = False
enableSkipCredits = False
askSkipIntro = False
askSkipCredits = False
PauseSyncDuringPlayback = False
PauseSyncDuringPlaybackStateChange = True
PauseRefreshLibrary = False
PauseRefreshChapterImages = False
busyMsg = False
offlineMsg = True
websocketenabled = True
startsyncenabled = True
FolderAddonUserdata = "special://profile/addon_data/plugin.service.emby-next-gen/"
FolderEmbyTemp = "special://profile/addon_data/plugin.service.emby-next-gen/temp/"
FolderUserdataThumbnails = "special://profile/Thumbnails/"
PlaylistPathMusic = "special://profile/playlists/music/"
PlaylistPathVideo = "special://profile/playlists/video/"
SystemShutdown = False
SyncPause = {}  # keys: playing, kodi_sleep, embyserverID, kodi_rw, priority (thread with higher priority needs access)
SyncPauseCondition = threading.Condition(threading.Lock())
EmbyServerOnlineCondition = threading.Condition(threading.Lock())
WidgetRefresh = {"video": False, "music": False}
SyncFavorites = False
LibraryIndependentProgress = False
Dialog = xbmcgui.Dialog()
WizardCompleted = True
sslverify = False
AddonModePath = "http://127.0.0.1:57342/"
TranslationsCached = {}
FavoriteQueue = None
httpConnectionTimeout = 5
WebserviceWorkers = 5
maxnodeitems = 25
SyncLockCondition = threading.Condition(threading.Lock())
SyncLock = True
DatabaseFiles = {'texture': "", 'texture-version': 0, 'music': "", 'music-version': 0, 'video': "", 'video-version': 0}
IconExtensions = ("jpg", "png", "gif", "webp", "apng", "avif", "svg", "ukn")
noimagejpg = b''
NextGenOnline = threading.Event()
ProgressBars = [True, {}] # [ProgressbarsEnabled, {Header, Message, Value, ProgressBar}]
ProgressBarsLock = threading.Lock()
JsonId = 1
ArtworkDelete = set()
ArtworkDeleteLock = threading.Lock()

# Kodi hash
CRC_TABLE = []

for ValueHex in range(256):
    CRC = ValueHex << 24

    for _ in range(8):
        if CRC & 0x80000000:
            CRC = (CRC << 1) ^ 0x04C11DB7
        else:
            CRC <<= 1

        CRC &= 0xffffffff

    CRC_TABLE.append(CRC)


# JsonRPC
def SendJson(Method, Params, ForceBreak):
    global JsonId
    JsonId += 1

    # Keep " escapes but escape \
    Params = Params.replace('\\"', "KEEPESPACES") # escape backslashes
    Params = Params.replace("\\", "\\\\") # escape backslashes
    Params = Params.replace('KEEPESPACES', '\\"') # escape backslashes

    if Params:
        JsonString = f'{{"jsonrpc": "2.0", "id": {JsonId}, "method": "{Method}", "params": {Params}}}'
    else:
        JsonString = f'{{"jsonrpc": "2.0", "id": {JsonId}, "method": "{Method}"}}'

    for Index in range(55): # retry -> timeout 10 seconds
        Ret = xbmc.executeJSONRPC(JsonString)

        if not Ret: # Valid but not correct Kodi return value -> Kodi bug
            return {}

        Ret = json.loads(Ret)

        if not Ret.get("error", False):
            return Ret

        if ForceBreak:
            return {}

        if Index < 50: # 5 seconds rapidly
            if sleep(0.1):
                return {}
        else: # after 5 seconds delay cycle by 1 second for the last 5 seconds
            if sleep(1):
                return {}

    xbmc.log(f"EMBY.helper.jsonrpc: Retry limit reached for {Method}", xbmc.LOGDEBUG)
    return {}

# Progress bars
def create_ProgressBar(TaskId, Header, Message):
    with SafeLock(ProgressBarsLock):
        if TaskId not in ProgressBars[1]:
            ProgressBars[1][TaskId] = [Header, Message, 0, None]

        if ProgressBars[0] and not ProgressBars[1][TaskId][3]: # Progress bars enabled
            ProgressBars[1][TaskId][3] = xbmcgui.DialogProgressBG()
            ProgressBars[1][TaskId][3].create(ProgressBars[1][TaskId][0], ProgressBars[1][TaskId][1])

def update_ProgressBar(TaskId, Value, Header, Message):
    with SafeLock(ProgressBarsLock):
        if TaskId in ProgressBars[1]:
            Value = int(Value)
            ProgressBars[1][TaskId][0] = Header
            ProgressBars[1][TaskId][1] = Message
            ProgressBars[1][TaskId][2] = Value

            if ProgressBars[1][TaskId][3]:
                ProgressBars[1][TaskId][3].update(Value, ProgressBars[1][TaskId][0], ProgressBars[1][TaskId][1])

def close_ProgressBar(TaskId):
    with SafeLock(ProgressBarsLock):
        if TaskId in ProgressBars[1]:
            if ProgressBars[1][TaskId][3]:
                ProgressBars[1][TaskId][3].close()

            del ProgressBars[1][TaskId]

def closeall_ProgressBar():
    with SafeLock(ProgressBarsLock):
        ProgressBars[0] = False

        for ProgressBar in ProgressBars[1].values():
            if ProgressBar[3]:
                ProgressBar[3].close()

            ProgressBar[3] = None

def openall_ProgressBar():
    with SafeLock(ProgressBarsLock):
        ProgressBars[0] = True

        for ProgressBar in ProgressBars[1].values():
            ProgressBar[3] = xbmcgui.DialogProgressBG()
            ProgressBar[3].create(ProgressBar[0], ProgressBar[1])
            ProgressBar[3].update(ProgressBar[2], ProgressBar[0], ProgressBar[1])

# Kodi workaround as it has flaws with blocking code
class SafeLock:
    __slots__ = ['lock']

    def __init__(self, lock):
        self.lock = lock

    def __enter__(self):
        while not self.lock.acquire(timeout=0.1):
            pass

    def __exit__(self, *args):
        self.lock.release()

def unset_SyncLock():
    global SyncLock

    with SafeLock(SyncLockCondition):
        SyncLock = False
        SyncLockCondition.notify_all()

def set_SyncLock():
    global SyncLock

    with SafeLock(SyncLockCondition):
        SyncLock = True
        SyncLockCondition.notify_all()

# Run workers in specific order
def RunSyncJobsAsync():
    global SyncLock

    while True:

        with SafeLock(SyncLockCondition): # threading.Condition required (not threading.event) as multiple workers can access this module
            while SyncLock:
                SyncLockCondition.wait(timeout=0.1)

                if SystemShutdown:

                    return

            SyncLock = True

        for EmbyServer in list(EmbyServers.values()):
            try:
                if not EmbyServer.library.Worker_is_paused("RunSyncJobsAsync"):
                    EmbyServer.library.RunJobs(True, False)
            except Exception as Error:
                xbmc.log(f"EMBY.helper.utils: Sync job failed: {type(Error).__name__}", xbmc.LOGERROR)

def update_SyncPause(Key, Value):
    with SafeLock(SyncPauseCondition):
        SyncPause[Key] = Value
        SyncPauseCondition.notify_all()

def clear_SyncPause():
    global SyncPause

    with SafeLock(SyncPauseCondition):
        SyncPause = {}
        SyncPauseCondition.notify_all()

def refresh_widgets(isVideo):
    with SafeLock(WidgetsRefreshLock):
        if isVideo:
            if WidgetRefresh['video']:
                return

            WidgetRefresh['video'] = True
            xbmc.executebuiltin('UpdateLibrary(video,/EMBY_widget_refresh_trigger_video/,false)')
        else:
            if WidgetRefresh['music']:
                return

            WidgetRefresh['music'] = True
            xbmc.executebuiltin('UpdateLibrary(music,/EMBY_widget_refresh_trigger_music/,true)')

# image:// Kodi uses the jobqueue for http calls "async" -> prevents blocking stat requests.
# image://specialtype@ forces Kodi to disable autorefresh cache write the path with image://specialtype@ prefix into the texture.db. Otherwise it would be unquoted to http://127.0.0.1 and written into texture.db
# from xbmc code: image://[type@]<url_encoded_path>?options
# Kodi 21 does not support custom specialtypes
def image_url(ServerId, ItemId, ImageType, ImageTag, ItemType="", ImageIndex=0):
    Profile = artwork.profile_for(ItemType, ImageType)
    Format = artwork.PROFILES[Profile][2]
    Code = artwork.SOURCE_CODES[ImageType]
    Filename = "noimage" if ImageTag == "noimage" else "unknown"
    # Keep the empty reserved URL field; artwork carries no text payload.
    Path = (f"dav://127.0.0.1:57342/picture/{ServerId}/"
            f"p-{ItemId}-{ImageIndex}-{Code}-{ImageTag}--{Profile}.{Format}")
    return image_url_encode(Path, f"{Filename}.{Format}")


def image_url_encode(url, Filename):
    if DatabaseFiles["texture-version"] <= 13: # Kodi 21
        url = f"{url}|redirect-limit=1000&failonerror=false"
        return f"image://epg@{quote(url, safe='')}/{Filename}"

    url = f"{url}|redirect-limit=1000&failonerror=false"
    return f"image://emby@{quote(url, safe='')}/{Filename}"

def image_url_decode(url, KeepUrlParams=False):
    imagePath, _ = unquote(url).rsplit("/", 1) # imagePath, urlFilename

    if not KeepUrlParams:
        imagePath = imagePath.replace("|redirect-limit=1000&failonerror=false", "")

    if DatabaseFiles["texture-version"] <= 13: # Kodi 21
        return imagePath.replace("image://epg@", "")

    return imagePath.replace("image://emby@", "")


def get_MimeType(Path):
    if not Path:
        return "", "unknown"

    p = Path.lower().replace("|redirect-limit=1000&failonerror=false", "").replace("|seekable=0&failonerror=false&verifypeer=false", "").replace("%7Credirect-limit%3D1000%26failonerror%3Dfalse", "")

    if p.endswith(".jpg") or p.endswith(".jpeg") or p.endswith(".jpe") or p.endswith(".jfif"):
        return "image/jpeg", "jpg"

    if p.endswith(".png"):
        return "image/png", "png"

    if p.endswith(".mp4") or p.endswith(".m4v"):
        return "video/mp4", "mp4"

    if p.endswith(".mp3"):
        return "audio/mpeg", "mp3"

    if p.endswith(".flac"):
        return "audio/flac", "flac"

    if p.endswith(".mkv"):
        return "video/x-matroska", "mkv"

    if p.endswith(".avi"):
        return "video/x-msvideo", "avi"

    if p.endswith(".bmp"):
        return "image/bmp", "bmp"

    if p.endswith(".ts") or p.endswith(".m2ts") or p.endswith(".mts"):
        return "video/mp2t", "ts"

    if p.endswith(".mpg") or p.endswith(".mpeg") or p.endswith(".mpe"):
        return "video/mpeg", "mpg"

    if p.endswith(".strm"):
        return "text/plain", "strm"

    if p.endswith(".gif"):
        return "image/gif", "gif"

    if p.endswith(".m3u") or p.endswith(".m3u8"):
        return "application/vnd.apple.mpegurl", "m3u8"

    if p.endswith(".webm"):
        return "video/webm", "webm"

    if p.endswith(".mov"):
        return "video/quicktime", "mov"

    if p.endswith(".wmv"):
        return "video/x-ms-wmv", "wmv"

    if p.endswith(".ogv"):
        return "video/ogg", "ogv"

    if p.endswith(".3gp"):
        return "video/3gpp", "3gp"

    if p.endswith(".flv"):
        return "video/x-flv", "flv"

    if p.endswith(".mxf"):
        return "application/mxf", "mxf"

    if p.endswith(".vob"):
        return "video/dvd", "vob"

    if p.endswith(".asf"):
        return "video/x-ms-asf", "asf"

    if p.endswith(".pls"):
        return "audio/x-scpls", "pls"

    if p.endswith(".webp"):
        return "image/webp", "webp"

    if p.endswith(".avif"):
        return "image/avif", "avif"

    if p.endswith(".heic") or p.endswith(".heif"):
        return "image/heic", "heic"

    if p.endswith(".apng"):
        return "image/apng", "apng"

    if p.endswith(".svg") or p.endswith(".svgz"):
        return "image/svg+xml", "svg"

    if p.endswith(".ico"):
        return "image/vnd.microsoft.icon", "ico"

    if p.endswith(".tiff") or p.endswith(".tif"):
        return "image/tiff", "tiff"

    if p.endswith(".psd"):
        return "image/vnd.adobe.photoshop", "psd"

    if p.endswith(".ai") or p.endswith(".eps"):
        return "application/postscript", "ai"

    if p.endswith(".dng"):
        return "image/x-adobe-dng", "dng"

    if p.endswith(".cr2") or p.endswith(".cr3") or p.endswith(".crw"):
        return "image/x-canon-raw", "crw"

    if p.endswith(".nef") or p.endswith(".nrw"):
        return "image/x-nikon-nef", "nrw"

    if p.endswith(".arw") or p.endswith(".srf") or p.endswith(".sr2"):
        return "image/x-sony-arw", "arw"

    if p.endswith(".orf"):
        return "image/x-olympus-orf", "orf"

    if p.endswith(".raf"):
        return "image/x-fuji-raf", "raf"

    if p.endswith(".rw2"):
        return "image/x-panasonic-raw", "rw2"

    if p.endswith(".raw"):
        return "image/x-dcraw", "raw"

    if p.endswith(".jpx") or p.endswith(".jp2"):
        return "image/jp2", "jp2"

    if p.endswith(".tga"):
        return "image/x-tga", "tga"

    if p.endswith(".pcx"):
        return "image/x-pcx", "pcx"

    if p.endswith(".m4a") or p.endswith(".m4b"):
        return "audio/mp4", "m4a"

    if p.endswith(".wav"):
        return "audio/wav", "wav"

    if p.endswith(".aac"):
        return "audio/aac", "aac"

    if p.endswith(".ogg") or p.endswith(".oga"):
        return "audio/ogg", "ogg"

    if p.endswith(".opus"):
        return "audio/opus", "opus"

    if p.endswith(".wma"):
        return "audio/x-ms-wma", "wma"

    if p.endswith(".aiff") or p.endswith(".aif") or p.endswith(".aifc"):
        return "audio/x-aiff", "aiff"

    if p.endswith(".ac3"):
        return "audio/ac3", "ac3"

    if p.endswith(".dts"):
        return "audio/vnd.dts", "dts"

    if p.endswith(".amr"):
        return "audio/amr", "amr"

    if p.endswith(".mp2"):
        return "audio/mpeg", "mp2"

    if p.endswith(".dsf"):
        return "audio/x-dsf", "dsf"

    if p.endswith(".dff"):
        return "audio/x-dff", "dff"

    if p.endswith(".ape"):
        return "audio/x-ape", "ape"

    if p.endswith(".wv"):
        return "audio/x-wavpack", "wv"

    if p.endswith(".tta"):
        return "audio/x-tta", "tta"

    if p.endswith(".mpc"):
        return "audio/x-musepack", "mpc"

    if p.endswith(".shn"):
        return "audio/x-shn", "shn"

    if p.endswith(".mka"):
        return "audio/x-matroska", "mka"

    if p.endswith(".mid") or p.endswith(".midi"):
        return "audio/midi", "midi"

    if p.endswith(".mod"):
        return "audio/x-mod", "mod"

    if p.endswith(".it"):
        return "audio/x-it", "it"

    if p.endswith(".s3m"):
        return "audio/x-s3m", "s3m"

    if p.endswith(".xm"):
        return "audio/x-xm", "xm"

    return "", "unknown"


def restart_kodi():
    global SystemShutdown
    SystemShutdown = True
    xbmc.executebuiltin('RestartApp')

def sleep(Seconds):
    if Seconds < 0.1:
        if SystemShutdown:
            return True

        xbmc.sleep(int(Seconds * 1000))
    else:
        for _ in range(int(Seconds * 10)):
            if SystemShutdown:
                return True

            xbmc.sleep(100)

    return False

# Delete objects from kodi cache
def delFolder(path, Pattern=""):
    dirs, files = xbmcvfs.listdir(path)
    SelectedDirs = ()

    if not Pattern:
        SelectedDirs = dirs
    else:
        for Dir in dirs:
            if Pattern in Dir:
                SelectedDirs += (Dir,)

    delete_recursive(path, SelectedDirs)

    for Filename in files:
        if Pattern in Filename:
            delFile(os.path.join(path, Filename))

    if path:
        rmFolder(path)


# Delete files and dirs recursively
def delete_recursive(path, dirs):
    for directory in dirs:
        SubFolder = os.path.join(path, directory, '')
        dirs2, files = xbmcvfs.listdir(SubFolder)

        for Filename in files:
            delFile(os.path.join(SubFolder, Filename))

        delete_recursive(SubFolder, dirs2)
        rmFolder(SubFolder)

def rmFolder(Path):
    try:
        xbmcvfs.rmdir(Path)
    except Exception as Error:
        xbmc.log(f"EMBY.helper.utils: Delete folder issue: {Error} / {Path}", xbmc.LOGWARNING)

def mkDir(Path):
    if xbmcvfs.exists(Path):
        return True

    try:
        xbmcvfs.mkdirs(Path)
        return True
    except Exception as Error:
        xbmc.log(f"EMBY.helper.utils: mkDir: {Error}", xbmc.LOGWARNING)

    return False

def delFile(Path):
    try:
        xbmcvfs.delete(Path)
    except Exception as Error:
        xbmc.log(f"EMBY.helper.utils: delFile: {Error}", xbmc.LOGWARNING)

def copyFile(SourcePath, DestinationPath):
    if xbmcvfs.exists(DestinationPath):
        return

    try:
        success = xbmcvfs.copy(SourcePath, DestinationPath)

        if not success:
            xbmc.log(f"EMBY.helper.utils: Cannot copy {SourcePath} to {DestinationPath}", xbmc.LOGERROR)
    except Exception as Error:
        xbmc.log(f"EMBY.helper.utils: copy issue: {SourcePath} to {DestinationPath} -> {Error}", xbmc.LOGERROR)


def readFileBinary(Path):
    try:
        infile = xbmcvfs.File(Path)
        data = infile.readBytes()
        infile.close()
        return data
    except Exception:
        return b""

def readFileString(Path):
    try:
        infile = xbmcvfs.File(Path)
        data = infile.read()
        infile.close()
        return data
    except Exception:
        return ""

def writeFile(Path, Data):
    try:
        outfile = xbmcvfs.File(Path, 'w')
        outfile.write(Data)
        outfile.close()
    except Exception as Error:
        xbmc.log(f"EMBY.helper.utils: writeFile ({Path}): {Error}", xbmc.LOGWARNING)


class PlaylistFileTransaction:
    """Keep the original files until their Emby database transaction completes."""
    def __init__(self):
        self.Originals = {}

    def write(self, Path, Data):
        Filename = xbmcvfs.translatePath(Path)
        if Filename not in self.Originals:
            Backup = None
            try:
                Source = open(Filename, 'rb')
            except FileNotFoundError:
                Source = None
            if Source is not None:
                try:
                    with Source, tempfile.NamedTemporaryFile(dir=os.path.dirname(Filename), prefix=".emby-rollback-", suffix=".tmp", delete=False) as File:
                        Backup = File.name
                        shutil.copyfileobj(Source, File)
                except Exception:
                    if Backup:
                        os.unlink(Backup)
                    raise
            self.Originals[Filename] = [Backup, False]
        writeFileAtomic(Path, Data)
        self.Originals[Filename][1] = True

    def close(self, Commit):
        Error = None
        for Filename, (Backup, Replaced) in list(self.Originals.items()):
            try:
                if not Commit and Replaced:
                    if Backup:
                        os.replace(Backup, Filename)
                    else:
                        try:
                            os.unlink(Filename)
                        except FileNotFoundError:
                            pass
                elif Backup:
                    os.unlink(Backup)
                del self.Originals[Filename]
            except OSError as Failure:
                # Keep a failed restore's backup and try the remaining files.
                xbmc.log(f"EMBY.helper.utils: Playlist file recovery/cleanup failed: {Filename}: {Failure}", xbmc.LOGERROR)
                Error = Error or Failure
        if Error:
            raise Error


def writeFileAtomic(Path, Data):
    """Replace a local profile file only after the new contents are fully written."""
    Filename = xbmcvfs.translatePath(Path)
    Directory = os.path.dirname(Filename)
    os.makedirs(Directory, exist_ok=True)
    Temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=Directory, prefix=".emby-", suffix=".tmp", delete=False) as File:
            Temporary = File.name
            if File.write(Data) != len(Data):
                raise OSError("Incomplete playlist write")
            File.flush()
            os.fsync(File.fileno())
        os.replace(Temporary, Filename)
    finally:
        if Temporary and os.path.exists(Temporary):
            os.unlink(Temporary)


def currenttime():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def currenttime_kodi_format():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def currenttime_kodi_format_and_unixtime():
    Current = datetime.now()
    KodiFormat = Current.strftime('%Y-%m-%d %H:%M:%S')
    UnixTime = int(datetime.timestamp(Current))
    return KodiFormat, UnixTime

def get_url_info(ConnectionString):
    if not ConnectionString.startswith("http://") and not ConnectionString.startswith("https://"):
        ConnectionString = f"http://{ConnectionString}"

    Url = urlsplit(ConnectionString)
    Scheme = Url.scheme
    Hostname = Url.hostname

    if Url.port:
        Port = Url.port
    elif Scheme == "https":
        Port = 443
    else:
        Port = 80

    SubUrl = f"/{Url.path.strip('/')}/".replace("//", "/")
    return Scheme, Hostname, Port, SubUrl

# Remove all emby playlists
def delete_playlists():
    for SearchFolder in (PlaylistPathVideo, PlaylistPathMusic):
        _, Filenames = xbmcvfs.listdir(SearchFolder)

        for Filename in Filenames:
            if is_emby_playlist(Filename):
                delFile(os.path.join(SearchFolder, Filename))

def is_emby_playlist(Filename):
    return Filename.startswith("emby_") and Filename.endswith(("_video.m3u", "_audio.m3u"))

# Remove all nodes
def delete_nodes():
    for Folder in ("special://profile/library/video/", "special://profile/library/music/"):
        Dirs, Files = xbmcvfs.listdir(Folder)
        delete_recursive(Folder, [Name for Name in Dirs if Name.startswith("emby_")])

        for Name in Files:
            if Name.startswith("emby_") and Name.endswith(".xml"):
                delFile(Folder + Name)


def get_unix_ticks(Date):
    try:
        return int(datetime.fromisoformat(Date).timestamp())
    except:
        return 0

def convert_to_local(date_input, DateOnly, YearOnly):
    if not date_input or str(date_input) == "0":
        return "0"

    try:
        if isinstance(date_input, (int, float)):
            dt = datetime(date_input, 1, 1, tzinfo=timezone.utc)
        elif isinstance(date_input, str):
            if len(date_input) < 10:
                return "0"

            Zulu = False

            if date_input.endswith("Z"):
                Zulu = True
                date_input = date_input[:-1]

            Pos = date_input.find(".")

            if Pos != -1:
                date_input = date_input[:Pos]

            if Zulu:
                date_input += "+00:00"

            dt = datetime.fromisoformat(date_input)

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = date_input

        if not 100 <= dt.year <= 9000:
            return "0"

        try:
            local_dt = dt.astimezone(None)
        except (OSError, OverflowError):
            # Windows cannot convert some pre-1970 dates via the system timezone.
            # Approximate historical local time with today's fixed UTC offset.
            LocalTimezone = datetime.now().astimezone().tzinfo
            local_dt = dt.astimezone(LocalTimezone) if dt.tzinfo else dt.replace(tzinfo=LocalTimezone)

        if YearOnly:
            return local_dt.year

        if DateOnly:
            return f"{local_dt.year:04d}-{local_dt.month:02d}-{local_dt.day:02d}"

        return f"{local_dt.year:04d}-{local_dt.month:02d}-{local_dt.day:02d} {local_dt.hour:02d}:{local_dt.minute:02d}:{local_dt.second:02d}"
    except Exception:
        return "0"

def Translate(Id):
    if Id in TranslationsCached:
        return TranslationsCached[Id]

    result = Addon.getLocalizedString(Id)

    if not result:
        result = xbmc.getLocalizedString(Id)

    TranslationsCached[Id] = result
    return result

def valid_Filename(Filename):
    Filename = decode_XML(Filename)

    if len(Filename) > 150:
        Filename = Filename[:150]

    return Filename.translate(ForbiddenCharecters)

def get_Filename(Path, KeepOriginal):
    Separator = get_Path_Seperator(Path)
    Pos = Path.rfind(Separator)
    Filename = Path[Pos + 1:]

    if not KeepOriginal:
        Filename = quote(Filename)

    return Filename

def SizeToText(FileSize):
    try:
        FileSize = float(FileSize or 0)
    except (TypeError, ValueError, OverflowError):
        FileSize = 0

    if not 0 <= FileSize < float('inf'):
        FileSize = 0

    Index = 0

    while FileSize >= 1024 and Index < 4:
        Index += 1
        FileSize /= 1024.0

    return f"{round(FileSize)}{FilesizeSuffixes[Index]}"

# Copy folder content from one to another
def copytree(PathSource, PathDestination, FilesExclude, Recursive, Overwrite):
    Folders, Filenames = xbmcvfs.listdir(PathSource)
    mkDir(PathDestination)

    if Recursive and Folders:
        copy_recursive(PathSource, Folders, PathDestination, FilesExclude, Overwrite)

    copy_files(Filenames, FilesExclude, PathSource, PathDestination, Overwrite)

def copy_recursive(PathSource, Folders, PathDestination, FilesExclude, Overwrite):
    for Folder in Folders:
        FolderSource = os.path.join(PathSource, Folder, '')
        FolderDestination = os.path.join(PathDestination, Folder, '')
        mkDir(FolderDestination)
        SubFolders, Filenames = xbmcvfs.listdir(FolderSource)

        if SubFolders:
            copy_recursive(FolderSource, SubFolders, FolderDestination, FilesExclude, Overwrite)

        copy_files(Filenames, FilesExclude, FolderSource, FolderDestination, Overwrite)

def copy_files(Filenames, FilesExclude, FolderSource, FolderDestination, Overwrite):
    for Filename in Filenames:
        # Filter by filename end
        if FilesExclude:
            Found = False

            for FileExclude in FilesExclude:
                if Filename.endswith(FileExclude):
                    Found = True
                    break

            if Found:
                continue

        FilePathDestination = os.path.join(FolderDestination, Filename)

        if xbmcvfs.exists(FilePathDestination):
            if Overwrite:
                delFile(FilePathDestination)
                copyFile(os.path.join(FolderSource, Filename), FilePathDestination)
        else:
            copyFile(os.path.join(FolderSource, Filename), FilePathDestination)

# Kodi Settings
def InitSettings():
    global device_name
    global displayMessage

    load_settings('MinimumSetup')
    load_settings_int('displayMessage')
    load_settings_int('startupDelay')
    load_settings_int('curltimeouts')
    load_settings_int('httpConnectionTimeout')
    load_settings_int('WebserviceWorkers')
    load_settings_int('maxnodeitems')
    load_settings_bool('sslverify')
    load_settings_bool('PauseSyncDuringPlayback')
    load_settings_bool('PauseRefreshLibrary')
    load_settings_bool('PauseRefreshChapterImages')
    load_settings_bool('restartMsg')
    load_settings_bool('enableContextSettingsOptions')
    load_settings_bool('enableContextRefreshOptions')
    load_settings_bool('autoSelectHighestPlaybackResolution')
    load_settings_bool('enableSkipIntro')
    load_settings_bool('enableSkipCredits')
    load_settings_bool('askSkipIntro')
    load_settings_bool('askSkipCredits')
    load_settings_bool('busyMsg')
    load_settings_bool('offlineMsg')
    load_settings_bool('WizardCompleted')
    load_settings_bool('websocketenabled')
    load_settings_bool('startsyncenabled')
    load_settings_bool('SyncFavorites')
    load_settings_bool('LibraryIndependentProgress')
    load_settings_bool('PauseSyncDuringPlaybackStateChange')

    CustomName = Addon.getSetting('customDeviceName').strip()
    DeviceName = CustomName.replace("/", "-") if CustomName else xbmc.getInfoLabel('System.FriendlyName')
    device_name = quote(DeviceName or "Kodi")

    displayMessage *= 1000
    update_mode_settings()
    xbmc.executebuiltin(f'SetProperty(EmbyRefresh,{enableContextRefreshOptions},10000)')
    xbmc.executebuiltin(f'SetProperty(EmbySettings,{enableContextSettingsOptions},10000)')


def update_mode_settings():
    # disable file metadata extraction
    SendJson("Settings.SetSettingValue", '{"setting":"myvideos.extractflags","value":false}', True)
    SendJson("Settings.SetSettingValue", '{"setting":"myvideos.usetags","value":false}', True)
    SendJson("Settings.SetSettingValue", '{"setting":"musicfiles.usetags","value":false}', True)
    SendJson("Settings.SetSettingValue", '{"setting":"musicfiles.findremotethumbs","value":false}', True)


def load_settings_bool(setting):
    for _ in range(10):
        value = Addon.getSetting(setting)

        if value == "": # Can happen when Kodi locked the file

            if sleep(0.1):
                break

            continue

        if value == "true":
            globals()[setting] = True
        else:
            globals()[setting] = False

        break

def load_settings(setting):
    for _ in range(10):
        value = Addon.getSetting(setting)

        if value == "": # Can happen when Kodi locked the file

            if sleep(0.1):
                break

            continue

        globals()[setting] = value
        break

def load_settings_int(setting):
    for _ in range(10):
        value = Addon.getSetting(setting)

        if value == "": # Can happen when Kodi locked the file

            if sleep(0.1):
                break

            continue

        globals()[setting] = int(value)
        break

def set_settings(setting, value):
    globals()[setting] = value
    Addon.setSetting(setting, value)

def set_settings_bool(setting, value):
    globals()[setting] = value

    if value:
        Addon.setSetting(setting, "true")
    else:
        Addon.setSetting(setting, "false")

def nodesreset():
    delete_nodes()

    for EmbyServer in list(EmbyServers.values()):
        EmbyServer.Views.update_nodes()

    Dialog.notification(heading=addon_name, icon=icon, message=Translate(33672), sound=False, time=displayMessage)

def get_Path_Seperator(Path):
    Pos = Path.rfind("/")

    if Pos == -1:
        return "\\"

    return "/"

def encode_XML(Data):
    if not any(char in Data for char in '&<>"\''):
        return Data

    return ENC_RE.sub(lambda m: ENC_MAP[m.group(0)], Data)

def decode_XML(Data):
    if "&" not in Data:
        return Data

    return DEC_RE.sub(lambda m: DEC_MAP[m.group(0)], Data)


def start_thread(Object, Args):
    if SystemShutdown:
        return

    Failed = False

    while True:
        try:
            Thread = threading.Thread(target=Object, args=Args)
            Thread.start()

            if Failed:
                xbmc.log(f"EMBY.helper.utils: Started worker after retry: {Object.__name__}", xbmc.LOGDEBUG)

            break
        except RuntimeError as error:
            if not Failed:
                xbmc.log(f"EMBY.helper.utils: Cannot start worker {Object.__name__}: {error}", xbmc.LOGDEBUG)
                Failed = True

            if sleep(1):
                break

def close_busyDialog():
    for _ in range(20):
        busydialogOpen = xbmc.getCondVisibility("Window.IsActive(10138)")
        busydialognocancelOpen = xbmc.getCondVisibility("Window.IsActive(10160)")

        if busydialogOpen:
            xbmc.executebuiltin('Dialog.Close(10138,true)') # busydialog

        if busydialognocancelOpen:
            xbmc.executebuiltin('Dialog.Close(10160,true)') # busydialognocancel

        if busydialogOpen or busydialognocancelOpen:
            if sleep(0.1):
                return
        else:
            break

def close_dialog(DialogNameOrId):
    if DialogNameOrId == "all":
        for _ in range(20):
            DialogOpen = xbmc.getCondVisibility("System.HasActiveModalDialog")

            if DialogOpen:
                xbmc.executebuiltin('Dialog.Close(all,true)')

                if sleep(0.01): # Kodi needs time to process
                    return
            else:
                break
    else:
        for _ in range(20):
            DialogOpen = xbmc.getCondVisibility(f"Window.IsActive({DialogNameOrId})")

            if DialogOpen:
                xbmc.executebuiltin(f'Dialog.Close({DialogNameOrId},true)') # busydialog

                if sleep(0.01):
                    return
            else:
                break

def ActivateWindow(WindowId, Path, DialogClose=False, WaitForOpen=0):
    if DialogClose:
        close_dialog("all")

    if Path:
        xbmc.executebuiltin(f'ActivateWindow({WindowId}, "{Path}", return)')
    else:
        xbmc.executebuiltin(f'ActivateWindow({WindowId})')

    if WaitForOpen:
        WindowId = xbmcgui.getCurrentWindowId()

        while WindowId != WaitForOpen:
            WindowId = xbmcgui.getCurrentWindowId()
            sleep(0.01)


def refresh_library_widgets():
    refresh_widgets(True)
    refresh_widgets(False)

def set_EmbyId_ServerId_by_Fake_KodiId(EmbyId, ServerId): # Maximum value is 2147483648
    if ServerId in EmbyServerIds:
        ServerIndex = EmbyServerIds.index(ServerId) + 1
    else:
        return 0

    EmbyFakeId = str(EmbyId)
    FakeIndex = 0

    for Index, Value in enumerate(MappingIds.values()):
        if str(EmbyId).startswith(Value):
            EmbyFakeId = EmbyFakeId.replace(Value, "", 1)
            FakeIndex = Index + 1
            break

    KodiId = ServerIndex * 100000000 + FakeIndex * 10000000 + int(EmbyFakeId)
    return KodiId

def get_EmbyId_ServerId_by_Fake_KodiId(KodiId):
    KodiId = int(KodiId)
    ServerIndex = KodiId // 100000000

    if not ServerIndex: # not an EmbyId
        return 0, ""

    Remain = KodiId % 100000000
    FakeNumberKey = Remain // 10000000
    EmbyId = Remain % 10000000

    if FakeNumberKey:
        FakeNumberKey = MappingIdsListKeys[FakeNumberKey - 1]
        EmbyId = int(f"{MappingIds[FakeNumberKey]}{EmbyId}")

    ServerId = EmbyServerIds[ServerIndex - 1]
    return EmbyId, ServerId

def get_digits(Text):
    Temp = ''.join(i for i in Text if i.isdigit())

    if Temp:
        return int(Temp)

    return 0

# Make folders
mkDir(FolderAddonUserdata)
mkDir(FolderEmbyTemp)
mkDir(FolderUserdataThumbnails)

# Init settings
InitSettings()
# Keep the current resume policy until the add-on starts again.
MovieResumeOwnerEnabled = not LibraryIndependentProgress

# Find Kodi's database files
DatabaseFiles = {'texture': "", 'texture-version': 0, 'music': "", 'music-version': 0, 'video': "", 'video-version': 0}
_, DatabaseFilesFound = xbmcvfs.listdir("special://profile/Database/")
noimagejpg = readFileBinary("special://home/addons/plugin.service.emby-next-gen/resources/noimage.jpg")

for DatabaseFileFound in DatabaseFilesFound:
    if not DatabaseFileFound.endswith('-wal') and not DatabaseFileFound.endswith('-shm') and not DatabaseFileFound.endswith('db-journal'):
        if DatabaseFileFound.startswith('Textures'):
            Version = get_digits(DatabaseFileFound)

            if Version > DatabaseFiles['texture-version']:
                DatabaseFiles['texture'] = xbmcvfs.translatePath(f"special://profile/Database/{DatabaseFileFound}")
                DatabaseFiles['texture-version'] = Version
        elif DatabaseFileFound.startswith('MyMusic'):
            Version = get_digits(DatabaseFileFound)

            if Version > DatabaseFiles['music-version']:
                DatabaseFiles['music'] = xbmcvfs.translatePath(f"special://profile/Database/{DatabaseFileFound}")
                DatabaseFiles['music-version'] = Version
        elif DatabaseFileFound.startswith('MyVideos'):
            Version = get_digits(DatabaseFileFound)

            if Version > DatabaseFiles['video-version']:
                DatabaseFiles['video'] = xbmcvfs.translatePath(f"special://profile/Database/{DatabaseFileFound}")
                DatabaseFiles['video-version'] = Version
