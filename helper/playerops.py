import threading
import xbmc
import xbmcvfs
import xbmcgui
from helper import utils, cache
from database import dbio
from emby import listitem

PlayerId = -1
PlayerPause = False
AVStarted = False
AVStartedCondition = threading.Condition(threading.Lock())
XbmcPlayer = xbmc.Player() # Init Player
XbmcPlaylists = [xbmc.PlayList(0), xbmc.PlayList(1)] # Init Playlists
PlaylistsPosition = [-1, -1, -1]
PlaybackRate = [1.0, 1.0, 1.0]
RepeatMode = ['RepeatNone', 'RepeatNone', 'RepeatNone']
Shuffled = [False, False, False]
PauseLock = threading.Lock()

def reload_PlaylistHandles(PlaylistId):
    XbmcPlaylists[PlaylistId] = xbmc.PlayList(PlaylistId)

def GetTempo():
    if PlayerId != -1:
        Tempo = xbmc.getInfoLabel('Player.PlaySpeed')

        if Tempo:
            try:
                Tempo = float(Tempo)
            except:
                return 0

            if Tempo == 0.76:
                Tempo = 0.75

            return Tempo

    return 0

def SetSpeed(Speed):
    if PlayerId != -1: # Tempo accepct only ranges between 0.75 to 1.55
        if Speed < 0.75: # Not possible by Kodi
            return

        if Speed > 1.54:
            if Speed < 1.5:
                Speed = 1
            else:
                Speed = 2

            utils.SendJson("Player.SetSpeed", f'{{"playerid": {PlayerId}, "speed": {int(Speed)}}}', True) # fast forward
        else: # Try set Tempo
            Result = utils.SendJson("Settings.GetSettingValue", '{"setting": "videoplayer.usedisplayasclock"}', True)

            if Result:
                Result = Result.get("result", {})
                UseDisplayAsClock = Result.get("value", False)
            else:
                UseDisplayAsClock = False

            if not UseDisplayAsClock: # Tempo not supported when UseDisplayAsClock is disabled
                if Speed < 1.5:
                    Speed = 1
                else:
                    Speed = 2

                utils.SendJson("Player.SetSpeed", f'{{"playerid": {PlayerId}, "speed": {int(Speed)}}}', True) # fast forward
            else:
                if Speed == 0.75:
                    Speed = 0.76

                utils.SendJson("Player.SetSpeed", f'{{"playerid": {PlayerId}, "speed": 1}}', True) # fast forward
                utils.SendJson("Player.SetTempo", f'{{"playerid": {PlayerId}, "tempo": {float(Speed)}}}', True) # playback speed

def GetStreamInfo(IndexMappingSubtitleEmby, IndexMappingSubtitleKodi):
    if PlayerId != -1:
        Result = utils.SendJson("Player.GetProperties", f'{{"playerid": {PlayerId}, "properties": ["currentaudiostream", "subtitleenabled", "currentsubtitle", "subtitles"]}}', True)

        if Result:
            Result = Result.get("result", {})
        else:
            return -1, -1, False, {}, {}

        KodiSubtitles = Result.get("subtitles", [])

        # Sort: External subtitles always last
        if KodiSubtitles and len(IndexMappingSubtitleEmby) == len(KodiSubtitles):
            KodiSubtitlesIndexExternal = []
            KodiSubtitlesIndexInternal = []
            KodiSubtitlesIndex = []
            IndexMappingSubtitleEmbyKeyByIndex = []
            Valid = True

            for KodiSubtitle in KodiSubtitles:
                Name = KodiSubtitle.get("name", "")

                if 'index' not in KodiSubtitle:
                    Valid = False
                    break

                if "(External)" in Name:
                    KodiSubtitlesIndexExternal.append(KodiSubtitle['index'])
                else:
                    KodiSubtitlesIndexInternal.append(KodiSubtitle['index'])

            if Valid:
                KodiSubtitlesIndex = KodiSubtitlesIndexInternal + KodiSubtitlesIndexExternal

                for Key in IndexMappingSubtitleEmby:
                    IndexMappingSubtitleEmbyKeyByIndex.append(Key)

                for Index, KodiSubtitlsIndex in enumerate(KodiSubtitlesIndex):
                    Key = IndexMappingSubtitleEmbyKeyByIndex[Index]
                    IndexMappingSubtitleEmby[Key] = KodiSubtitlsIndex
                    IndexMappingSubtitleKodi[KodiSubtitlsIndex] = Key

        KodiSubtitleIndex = Result.get("currentsubtitle", -1)

        if KodiSubtitleIndex:
            if KodiSubtitleIndex != -1:
                KodiSubtitleIndex = KodiSubtitleIndex.get("index", -1)
        else:
            KodiSubtitleIndex = -1

        KodiAudioIndex = Result.get("currentaudiostream", -1)

        if KodiAudioIndex:
            if KodiAudioIndex != -1:
                KodiAudioIndex = KodiAudioIndex.get("index", -1)
        else:
            KodiAudioIndex = -1

        return KodiAudioIndex, KodiSubtitleIndex, Result.get("subtitleenabled", False), IndexMappingSubtitleEmby, IndexMappingSubtitleKodi

    return -1, -1, False, {}, {}

def InsertPlaylist(PlaylistId, Position, KodiType, KodiId):
    if PlaylistId != -1:
        utils.SendJson("Playlist.Insert", f'{{"playlistid": {PlaylistId}, "position": {Position}, "item": {{"{KodiType}id": {KodiId}}}}}', False)
    else:
        xbmc.log(f"EMBY.helper.playerops: InsertPlaylist failed: PlaylistId={PlaylistId}", xbmc.LOGERROR)


def GetPlaylistPosition(PlaylistId):
    if -1 < PlaylistId < 2:
        try:
            PlaylistsPosition[PlaylistId] = XbmcPlaylists[PlaylistId].getposition()
            return PlaylistsPosition[PlaylistId]
        except:
            try:
                reload_PlaylistHandles(PlaylistId)
                PlaylistsPosition[PlaylistId] = XbmcPlaylists[PlaylistId].getposition()
                return PlaylistsPosition[PlaylistId]
            except:
                xbmc.log("EMBY.helper.playerops: [ GetPlaylistPosition ] failed", xbmc.LOGERROR)
                PlaylistsPosition[PlaylistId] = -1
                return -1
    elif PlaylistId == 2:
        Ret = utils.SendJson("Player.GetProperties", '{"playerid":2,"properties":["position", "playlistid"]}', False)
        PlaylistsPosition[PlaylistId] = int(Ret.get("result", {}).get("position", -1))
        return PlaylistsPosition[PlaylistId]

    return -1

def GetPlaylistSize(PlaylistId):
    if PlaylistId != -1:
        try:
            Size = XbmcPlaylists[PlaylistId].size()
            return Size
        except:
            try:
                reload_PlaylistHandles(PlaylistId)
                Size = XbmcPlaylists[PlaylistId].size()
                return Size
            except:
                xbmc.log("EMBY.helper.playerops: [ GetPlaylistSize ] failed", xbmc.LOGERROR)
                return 0

    return 0

def PlayPlaylistItem(PlaylistId, Index):
    global PlayerId

    if PlaylistId != -1:
        utils.SendJson("Player.Open", f'{{"item":{{"playlistid":{PlaylistId},"position":{Index}}} ,"options": {{"resume": false}}}}', True)
        PlayerId = PlaylistId
    else:
        xbmc.log(f"EMBY.helper.playerops: PlayPlaylistItem failed: PlaylistId={PlaylistId}", xbmc.LOGERROR)

def GetPlayerFilepath():
    if XbmcPlayer.isPlaying():
        try:
            Filepath = XbmcPlayer.getPlayingFile()
            return Filepath
        except:
            return ""

    return ""

def AddSubtitle(Path):
    SubtitleIndexAdded = -1
    Path = xbmcvfs.translatePath(Path)

    if not wait_AVStarted():
        return -1

    Ret = utils.SendJson("Player.GetProperties", '{"playerid":1,"properties":["subtitles"]}', False)
    SubtitleCount = len(Ret.get("result", {}).get("subtitles", []))
    utils.SendJson("Player.AddSubtitle", f'{{"playerid":1, "subtitle":"{Path}"}}', False)

    # Wait for subtitle added
    for _ in range(50):
        Ret = utils.SendJson("Player.GetProperties", '{"playerid":1,"properties":["subtitles"]}', False)
        Subtitles = Ret.get("result", {}).get("subtitles", [])

        if len(Subtitles) > SubtitleCount:
            SubtitleIndexAdded = Subtitles[-1]["index"]
            break

        utils.sleep(0.1)

    return SubtitleIndexAdded

def SelectSubtitle(Index):
    if XbmcPlayer.isPlaying():
        try:
            XbmcPlayer.setSubtitleStream(Index)
        except:
            xbmc.log(f"EMBY.helper.playerops: [ SelectSubtitle ] failed {Index}", xbmc.LOGDEBUG)

def EnableSubtitle(Enable):
    if XbmcPlayer.isPlaying():
        try:
            XbmcPlayer.showSubtitles(Enable)
        except:
            xbmc.log(f"EMBY.helper.playerops: [ EnableSubtitle ] failed {Enable}", xbmc.LOGDEBUG)

def RemovePlaylistItem(PlaylistId, Index):
    if PlaylistId != -1:
        utils.SendJson("Playlist.Remove", f'{{"playlistid":{PlaylistId}, "position":{Index}}}', False)
    else:
        xbmc.log(f"EMBY.helper.playerops: RemovePlaylistItem failed: PlaylistId={PlaylistId}", xbmc.LOGERROR)

def Next():
    global PlayerPause
    global AVStarted

    if XbmcPlayer.isPlaying():

        try:
            xbmc.executebuiltin("PlayerControl(Next)")
            PlayerPause = False
            AVStarted = False
            return
        except:
            xbmc.log(f"EMBY.helper.playerops: Next failed: PlayerId={PlayerId}", xbmc.LOGERROR)

def Previous():
    global PlayerPause
    global AVStarted

    if XbmcPlayer.isPlaying():

        try:
            xbmc.executebuiltin("PlayerControl(Previous)")
            PlayerPause = False
            AVStarted = False
            return
        except:
            xbmc.log("EMBY.helper.playerops: Previous failed", xbmc.LOGERROR)

def Stop(Wait=False):
    global PlayerPause
    global AVStarted
    AVStarted = False
    PlayerPause = False

    if XbmcPlayer.isPlaying():

        PlayerPause = False
        xbmc.executebuiltin(f'PlayerControl(Stop, {PlayerId})')

        if Wait:
            while XbmcPlayer.isPlaying():
                if utils.sleep(0.1):
                    break


def Play(Path, ListItem, Windowed):
    global PlayerPause
    global AVStarted
    AVStarted = False
    PlayerPause = False

    XbmcPlayer.play(Path, listitem=ListItem, windowed=Windowed)

    return True

def UpdateInfoTag(ListItem):
    if XbmcPlayer.isPlaying():
        try:
            XbmcPlayer.updateInfoTag(ListItem)
            return True
        except:
            return False

    return False

def PauseToggle():
    if PlayerPause:
        Unpause()
    else:
        Pause()


def Pause(WaitForPlayback=False):
    global PlayerPause

    with utils.SafeLock(PauseLock):
        if not PlayerPause:
            if WaitForPlayback:
                if not wait_AVStarted():
                    return

            if XbmcPlayer.isPlaying():

                xbmc.executebuiltin('PlayerControl(Play)')
                PlayerPause = True

        else:
            xbmc.log(f"EMBY.helper.playerops: Pause failed: PlayerId={PlayerId} / PlayerPause={PlayerPause}", xbmc.LOGERROR)

def Unpause():
    global PlayerPause

    with utils.SafeLock(PauseLock):
        if PlayerPause:
            if XbmcPlayer.isPlaying():

                xbmc.executebuiltin('PlayerControl(Play)')

            PlayerPause = False
        else:
            xbmc.log(f"EMBY.helper.playerops: Unpause failed: PlayerId={PlayerId} / PlayerPause={PlayerPause}", xbmc.LOGERROR)

def TicksToTimestamp(Ticks):
    Ticks = float(Ticks)


    return int((Ticks / 36000000000) % 24), int((Ticks / 600000000) % 60), int((Ticks / 10000000) % 60), int((Ticks / 10000) % 1000), round(Ticks)  # Hours / Minutes / Seconds / Milliseconds / Ticks

def Seek(SeekPositionTicksQuery, Relative=False):
    if PlayerId != -1:
        if not wait_AVStarted():
            xbmc.log(f"EMBY.helper.playerops: Seek: avstart not set: seek={SeekPositionTicksQuery}", xbmc.LOGERROR)
            return

        if XbmcPlayer.isPlaying():
            WarningLogSend = False
            TargetTicks = float(SeekPositionTicksQuery)


            for _ in range(5):
                CurrentPositionTicks = PlayBackPosition()

                if CurrentPositionTicks == 0:

                    return

                if Relative:
                    FinalTicks = CurrentPositionTicks + TargetTicks
                else:
                    FinalTicks = TargetTicks

                Drift = (FinalTicks - CurrentPositionTicks) / 10000.0

                if -500 < Drift < 500:

                    return

                try:
                    XbmcPlayer.seekTime(FinalTicks / 10000000.0)
                    return

                except:
                    if not WarningLogSend:
                        WarningLogSend = True

                xbmc.sleep(100)

            xbmc.log(f"EMBY.helper.playerops: Seek not set: seek={TargetTicks}", xbmc.LOGERROR)
    else:
        xbmc.log(f"EMBY.helper.playerops: Seek failed: PlayerId={PlayerId}", xbmc.LOGERROR)

def PlayBackPosition():
    if XbmcPlayer.isPlaying():
        try:
            return max(int(XbmcPlayer.getTime() * 10000000), 0)
        except:
            return 0

    return 0

def PlayBackDuration():
    if XbmcPlayer.isPlaying():
        try:
            return max(int(XbmcPlayer.getTotalTime() * 10000000), 0)
        except:
            return 0

    return 0

def PlayEmby(ItemIds, PlayCommand, StartIndex, StartPositionTicks, ServerData, API):
    global PlayerId
    global AVStarted
    global PlayerPause

    if not ItemIds:
        xbmc.log("EMBY.helper.playerops: PlayEmby, no ItemIds received", xbmc.LOGWARNING)
        return

    StartIndex = max(StartIndex, 0)
    hasVideo = False

    # Check if content is synced and load item data
    embydb = dbio.DBOpenRO(ServerData['ServerId'], "AddPlaylistItem")
    LoadFromServer = False
    PlaylistItems = len(ItemIds) * [None] # pre allocate memory

    for Index, EmbyID in enumerate(ItemIds):
        KodiId, KodiType = embydb.get_KodiId_by_EmbyId(EmbyID)

        if KodiId: # synced content
            if KodiType != "song":
                hasVideo = True

            PlaylistItems[Index] = [EmbyID, utils.KodiTypeMapping[KodiType], KodiType, KodiId, None, None, None]
        else: # not synced content
            PlaylistItems[Index] = [EmbyID, None, None, None, None, None, None]
            LoadFromServer = True

    dbio.DBCloseRO(ServerData['ServerId'], "AddPlaylistItem")

    # Load Additional data from server check content
    if LoadFromServer:
        Items = len(ItemIds) * [None] # pre allocate memory
        ItemIdsString = [str(ItemId) for ItemId in ItemIds] # Convert Emby Id (integer) to string values

        for Index, Item in enumerate(API.get_Items_Ids(ItemIdsString, ["All"], True, False, "", "", {}, None, False)): # Use "All" to disable sorting by API
            if not Item: # skip empty or synced content item
                continue

            if Item["Type"] not in ("Movie", "Video", "Episode", "MusicVideo", "Audio"):
                return

            if Item["Type"] != "Audio":
                hasVideo = True

            Items[Index] = Item

    # Select player

    if hasVideo:
        PlayerIdPlaylistId = 1
        PlayerId = 1
    else:
        PlayerIdPlaylistId = 0
        PlayerId = 0

    # Load StartIndex item
    if not PlaylistItems[StartIndex][1]: # Load data for unsynced content
        PlaylistItems[StartIndex] = load_Remoteitems(Items[StartIndex], PlaylistItems[StartIndex], ServerData['ServerId'])

    # Prepare music/video playlist for StartIndex item and start playback
    if PlayCommand in ("PlayNow", "PlayNext"):
        KodiPlaylistIndexStartitem = GetPlaylistPosition(PlayerIdPlaylistId) + 1
    elif PlayCommand == "PlayLast":
        KodiPlaylistIndexStartitem = GetPlaylistSize(PlayerIdPlaylistId)
    else:
        return

    if PlaylistItems[StartIndex][2]: # synced item (KodiType available)
        InsertPlaylist(PlayerIdPlaylistId, KodiPlaylistIndexStartitem, PlaylistItems[StartIndex][2], PlaylistItems[StartIndex][3])
    else:
        XbmcPlaylists[PlayerIdPlaylistId].add(PlaylistItems[StartIndex][5], PlaylistItems[StartIndex][4], index=KodiPlaylistIndexStartitem) # Path, ListItem, Index

    if PlayCommand in ("PlayLast", "PlayNext"):
        return

    # Start playback

    AVStarted = False
    PlayerPause = False

    with utils.SafeLock(AVStartedCondition):
        AVStartedCondition.notify_all()

    StartPositionTicks = int(StartPositionTicks)

    if PlaylistItems[StartIndex][2]: # KodiType
        if StartPositionTicks != -1:
            Hours, Minutes, Seconds, Milliseconds, _ = TicksToTimestamp(StartPositionTicks)
            utils.SendJson("Player.Open", f'{{"item": {{"{PlaylistItems[StartIndex][2]}id": {PlaylistItems[StartIndex][3]}}}, "options": {{"resume": {{"hours": {Hours}, "minutes": {Minutes}, "seconds": {Seconds}, "milliseconds": {Milliseconds}}}}}}}', False)
        else:
            utils.SendJson("Player.Open", f'{{"item": {{"{PlaylistItems[StartIndex][2]}id": {PlaylistItems[StartIndex][3]}}}, "options": {{"resume": true}}}}', False)
    else:
        PlayPlaylistItem(PlayerIdPlaylistId, KodiPlaylistIndexStartitem)

        if StartPositionTicks != -1:
            Seek(StartPositionTicks) # Resumeposition not respected by Kodi if "Player.Open" adresses a playlist/playlist position. Use seek as workaround
        else:
            Seek(PlaylistItems[StartIndex][6]) # Resumeposition not respected by Kodi if "Player.Open" adresses a playlist/playlist position. Use seek as workaround

    WindowId = xbmcgui.getCurrentWindowId()

    if PlayerIdPlaylistId == 0 and WindowId != 12006:
        utils.ActivateWindow("visualisation", "", False, 0)
    elif PlayerIdPlaylistId == 1 and WindowId != 12005:
        utils.ActivateWindow("fullscreenvideo", "", False, 0)

    # Load Additional data from server
    if LoadFromServer:
        for Index, Item in enumerate(Items):
            if not Item:
                continue

            InsertPosition = KodiPlaylistIndexStartitem + Index

            if Index == StartIndex:
                continue

            PlaylistItems[Index] = load_Remoteitems(Item, PlaylistItems[Index], ServerData['ServerId'])

            if PlaylistItems[Index][2]: # synced item
                InsertPlaylist(PlayerIdPlaylistId, InsertPosition, PlaylistItems[Index][2], PlaylistItems[Index][3])
            else:
                XbmcPlaylists[PlayerIdPlaylistId].add(PlaylistItems[Index][5], PlaylistItems[Index][4], index=InsertPosition) # Path, ListItem, Index

        del Items


def load_Remoteitems(Item, PlaylistItem, ServerId):
    listitem.set_playback_listitem(Item, ServerId)

    if PlaylistItem[1]: # Kodi content
        PlaylistItem[4] = Item['ListItem']
        PlaylistItem[5] = Item['KodiFullPath']
    else:
        if "UserData" in Item and "PlaybackPositionTicks" in Item["UserData"] and Item["UserData"]["PlaybackPositionTicks"]:
            PlaylistItem = [Item['Id'], Item['Type'], None, None, Item['ListItem'], Item['KodiFullPath'], Item["UserData"]["PlaybackPositionTicks"]]
        else:
            PlaylistItem = [Item['Id'], Item['Type'], None, None, Item['ListItem'], Item['KodiFullPath'], 0]

        cache.add_Item(Item, ServerId)

    return PlaylistItem

def wait_AVStarted():
    Timeout = 100 # 10 seconds

    with utils.SafeLock(AVStartedCondition):

        while not AVStarted:
            if Timeout <= 0:
                xbmc.log("EMBY.helper.playerops: AVstart timeout", xbmc.LOGERROR)
                return False

            AVStartedCondition.wait(timeout=0.1)
            Timeout -= 1

        return True
