import threading
import uuid
from urllib.parse import unquote
import json
import xbmc
from database import dbio
from emby import listitem, metadata, httpcache
from core import common
from dialogs import skipintrocredits
from . import utils, playerops, queue, cache, copy, versions
TrackerPaused = False
PlaylistRemoveItem = -1
Volume = 100
Muted = False
PlayItem = (0, "")
PlayerVolume = utils.SendJson("Application.GetProperties", '{"properties": ["volume", "muted"]}', False).get('result', {})

if PlayerVolume:
    Volume = PlayerVolume.get('volume', 100)
    Muted = PlayerVolume.get('muted', False)

PlaylistKodi = [[], [], []]
PlaylistEmby = [[], [], []]
PlayingItem = {"EmbySessionData": {}, "IntroStartPositionTicks": 0, "IntroEndPositionTicks": 0, "CreditsPositionTicks": 0, "EmbyServer": None, "KodiType": "", "IndexMappingVideoEmby": {}, "IndexMappingVideoKodi": {}, "IndexMappingAudioEmby": {}, "IndexMappingAudioKodi": {}, "IndexMappingSubtitleEmby": {}, "IndexMappingSubtitleKodi": {}, "SubtitleEnabled": False, "SubtitleIndexKodi": 0}
PlayingItemInit = {"EmbySessionData": {}, "IntroStartPositionTicks": 0, "IntroEndPositionTicks": 0, "CreditsPositionTicks": 0, "EmbyServer": None, "KodiType": "", "IndexMappingVideoEmby": {}, "IndexMappingVideoKodi": {}, "IndexMappingAudioEmby": {}, "IndexMappingAudioKodi": {}, "IndexMappingSubtitleEmby": {}, "IndexMappingSubtitleKodi": {}, "SubtitleEnabled": False, "SubtitleIndexKodi": 0}
QueuedPlayingItem = {}
MultiselectionDone = False
EmbyPlaying = False
SkipIntroJumpDone = False
SkipCreditsJumpDone = False
PlayerBusyDelay = 5
ItemKodiSkipUpdate = []
PlayerEventsQueue = queue.Queue()
ItemsUpdateQueue = queue.Queue()
SkipIntroDialog = skipintrocredits.SkipPrompt("script-emby-skipintrodialog.xml", *utils.CustomDialogParameters)
SkipCreditsDialog = skipintrocredits.SkipPrompt("script-emby-skipcreditsdialog.xml", *utils.CustomDialogParameters)
ForceStopKodiId = 0
ForceStopCondition = threading.Condition(threading.Lock())
ProgressBarEnable = -1
PlayerLock = threading.Lock()

# Player events (queued by monitor notifications)
def PlayerCommands():
    global PlayerBusyDelay
    global TrackerPaused
    global SkipIntroJumpDone
    global SkipCreditsJumpDone
    global PlaylistRemoveItem
    global MultiselectionDone
    global QueuedPlayingItem
    global PlayingItemInit
    global EmbyPlaying
    global PlayingItem
    global PlayItem
    global ForceStopKodiId
    global Muted
    global Volume
    global ProgressBarEnable

    while True:
        Commands = PlayerEventsQueue.get()

        with utils.SafeLock(PlayerLock):

            if Commands == "QUIT":
                return

            PlayerBusyDelay = 5

            if Commands[0] == "seek": # {'item': {'id': 33874, 'type': 'episode'}, 'player': {'playerid': 1, 'seekoffset': {'hours': 0, 'milliseconds': 177, 'minutes': 41, 'seconds': 56}, 'speed': 1, 'time': {'hours': 0, 'milliseconds': 550, 'minutes': 47, 'seconds': 3}}}
                # Seekposition might not be exact. Don't use it as critical data e.g. do not use for remote playback seek, but good enough for the progress updates
                EventData = json.loads(Commands[1])
                set_PlayerId(EventData)

                if not PlayingItem["EmbySessionData"]:
                    continue

                if 'player' in EventData and 'time' in EventData['player']:
                    PlayingItem["EmbySessionData"]['PositionTicks'] = (EventData['player']['time']['hours'] * 3600000 + EventData['player']['time']['minutes'] * 60000 + EventData['player']['time']['seconds'] * 1000 + EventData['player']['time']['milliseconds']) * 10000
                    TrackerPaused = True
                    report_progress("TimeUpdate")


            elif Commands[0] == "avchange": # {"item":{"id":12115,"type":"episode"},"player":{"playerid":1,"speed":1}}
                EventData = json.loads(Commands[1])

                if "item" in EventData:
                    if 'id' in EventData['item']:
                        if (ForceStopKodiId == EventData["item"]["id"] and
                                not selected_episode(playerops.GetPlayerFilepath())):
                            playerops.Stop()
                            continue

                set_PlayerId(EventData)

                # Update playback rate
                Speed = float(playerops.GetTempo())

                if Speed != playerops.PlaybackRate[playerops.PlayerId]:
                    playerops.PlaybackRate[playerops.PlayerId] = float(Speed)
                    PlayingItem["EmbySessionData"].update({'PlaybackRate': playerops.PlaybackRate[playerops.PlayerId]})

                    if PlayingItem["EmbyServer"]:
                        TrackerPaused = True
                        report_progress("PlaybackRateChange")


            elif Commands[0] == "avstart": # ('avstart', '{"item":{"id":33874,"type":"episode"},"player":{"playerid":1,"speed":1}}')
                EventData = json.loads(Commands[1])
                KodiId = 0
                KodiType = ""
                FullPath = playerops.GetPlayerFilepath()
                if not FullPath:
                    continue
                EpisodeSelection = selected_episode(FullPath)

                # Dummy (blankwav) played
                if "item" in EventData:
                    if 'id' in EventData['item']:
                        KodiId = EventData['item']['id']
                        KodiType = EventData['item']['type']

                        if ForceStopKodiId == EventData["item"]["id"] and not EpisodeSelection:
                            playerops.Stop(Wait=True)
                            continue

                set_PlayerId(EventData)

                PlaylistPosition = playerops.GetPlaylistPosition(playerops.PlayerId)
                close_SkipIntroDialog()
                close_SkipCreditsDialog()
                SkipIntroJumpDone = False
                SkipCreditsJumpDone = False

                # 3D, ISO etc. content from webserverice (addon mode)
                if PlaylistRemoveItem != -1 and not EpisodeSelection:
                    playerops.RemovePlaylistItem(1, PlaylistRemoveItem)
                PlaylistRemoveItem = -1

                # multiselection done
                if MultiselectionDone and not EpisodeSelection:
                    MultiselectionDone = False
                    continue

                EmbyId = 0
                if EpisodeSelection:
                    from hooks import webservice
                    MultiselectionDone = False
                    if ForceStopKodiId == KodiId:
                        ForceStopKodiId = 0
                    webservice.start_selected_episode(EpisodeSelection)
                    isAddonContent, EmbyType, MediaSources = True, 'Episode', []
                else:
                    SelectedVersion = QueuedPlayingItem.get('SelectedVersion')
                    EmbyId, isAddonContent, isDynamic, EmbyType, MediaSources, CachedItem = find_EmbyContent(FullPath, KodiId, KodiType)

                if PlayingItem["EmbySessionData"] and 'ItemId' in PlayingItem["EmbySessionData"]:
                    cache.update_userdata_Kodi(str(PlayingItem["EmbySessionData"]['ItemId']), PlayingItem["EmbyServer"].ServerData['ServerId'], PlayingItem["EmbySessionData"]['PositionTicks'] / 10000000.0, utils.currenttime(), None, PlayingItem["EmbySessionData"]['RunTimeTicks'] / 10000000.0, None)

                MediaSources = versions.sort_sources(MediaSources)
                if EmbyType and EmbyType != 'Episode':
                    versions.clear_choice()

                # Playback outside the loopback URL (disc or redirected HTTP)
                if not isAddonContent:
                    VersionContext = get_version_context(QueuedPlayingItem['EmbyServer'].ServerData['ServerId'], EmbyId, KodiType, CachedItem) if MediaSources and QueuedPlayingItem else None
                    RememberedIndex = versions.recall_choice(MediaSources, VersionContext)
                    # Multiversion selection
                    if len(MediaSources) > 1:

                        if isDynamic or KodiType != "movie":
                            playerops.Pause()

                            MediaIndex = None
                            if SelectedVersion and SelectedVersion[:2] == (str(QueuedPlayingItem['EmbyServer'].ServerData['ServerId']), str(EmbyId)):
                                MediaIndex = next((Index for Index, Source in enumerate(MediaSources) if Source['Id'] == SelectedVersion[2]), None)
                            if MediaIndex is None:
                                MediaIndex = RememberedIndex
                            if MediaIndex is None and utils.autoSelectHighestPlaybackResolution:
                                MediaIndex = versions.highest_resolution_index(MediaSources)
                            if MediaIndex is None:
                                Selection = []

                                for MediaSourceData in MediaSources:
                                    Selection.append(f"{MediaSourceData['Name']} - {utils.SizeToText(MediaSourceData.get('Size'))} - {MediaSourceData['Path']}")

                                MediaIndex = utils.Dialog.select(utils.Translate(33453), Selection, preselect=0)

                                if MediaIndex == -1:
                                    versions.clear_choice()
                                    Cancel()
                                    continue

                            versions.remember_choice(MediaSources, MediaIndex, VersionContext)
                            if MediaSources[MediaIndex]['Id'] == QueuedPlayingItem['EmbySessionData'].get('MediaSourceId'):
                                playerops.Unpause()
                            else: # Reload new multiversion
                                Path = MediaSources[MediaIndex]['Path']
                                ListItem = load_KodiItem("onAVStarted", KodiId, KodiType, CachedItem, MediaIndex)

                                if not ListItem:
                                    xbmc.log("EMBY.helper.player: --< [ onAVStarted ] no listitem", xbmc.LOGDEBUG)
                                    continue

                                MultiselectionDone = True
                                # Insert Multicontent version into playlist as next item, play next and remove it afterwards
                                PlaylistIndexContent = PlaylistPosition
                                playerops.XbmcPlaylists[1].add(Path, ListItem, PlaylistIndexContent + 1)
                                MediasourcesSelected = MediaSources[MediaIndex]
                                QueuedPlayingItem = {
                                    "EmbySessionData": {
                                        "QueueableMediaTypes": ["Audio", "Video"],
                                        "CanSeek": True,
                                        "IsPaused": False,
                                        "ItemId": EmbyId,
                                        "MediaSourceId": MediasourcesSelected["Id"],
                                        "PlaySessionId": str(uuid.uuid4()).replace("-", ""),
                                        "PositionTicks": 0,
                                        "RunTimeTicks": 0,
                                        "VolumeLevel": Volume,
                                        "PlaybackRate": playerops.PlaybackRate[playerops.PlayerId],
                                        "Shuffle": playerops.Shuffled[playerops.PlayerId],
                                        "RepeatMode": playerops.RepeatMode[playerops.PlayerId],
                                        "IsMuted": Muted
                                    },
                                    "IntroStartPositionTicks": MediasourcesSelected["IntroStartPositionTicks"],
                                    "IntroEndPositionTicks": MediasourcesSelected["IntroEndPositionTicks"],
                                    "CreditsPositionTicks": MediasourcesSelected["CreditsPositionTicks"],
                                    "EmbyServer": QueuedPlayingItem["EmbyServer"],
                                    "KodiType": KodiType,
                                    "IndexMappingVideoEmby": MediasourcesSelected.get('IndexMappingVideoEmby', {}),
                                    "IndexMappingVideoKodi": MediasourcesSelected.get('IndexMappingVideoKodi', {}),
                                    "IndexMappingAudioEmby": MediasourcesSelected.get('IndexMappingAudioEmby', {}),
                                    "IndexMappingAudioKodi": MediasourcesSelected.get('IndexMappingAudioKodi', {}),
                                    "IndexMappingSubtitleEmby": MediasourcesSelected.get('IndexMappingSubtitleEmby', {}),
                                    "IndexMappingSubtitleKodi": MediasourcesSelected.get('IndexMappingSubtitleKodi', {}),
                                    "SubtitleEnabled": False,
                                    "SubtitleIndexKodi": 0
                                }
                                playerops.Next()
                                playerops.RemovePlaylistItem(1, PlaylistIndexContent)

                if not QueuedPlayingItem:
                    continue

                # Update Stream info
                if playerops.PlayerId == 0:
                    QueuedPlayingItem["EmbySessionData"]['AudioStreamIndex'] = 1
                else:
                    AudioIndexKodi, QueuedPlayingItem["SubtitleIndexKodi"], QueuedPlayingItem["SubtitleEnabled"], QueuedPlayingItem["IndexMappingSubtitleEmby"], QueuedPlayingItem["IndexMappingSubtitleKodi"] = playerops.GetStreamInfo(QueuedPlayingItem["IndexMappingSubtitleEmby"], QueuedPlayingItem["IndexMappingSubtitleKodi"])

                    if AudioIndexKodi in QueuedPlayingItem["IndexMappingAudioKodi"]:
                        QueuedPlayingItem["EmbySessionData"].update({'AudioStreamIndex': QueuedPlayingItem["IndexMappingAudioKodi"][AudioIndexKodi]})

                    if QueuedPlayingItem["SubtitleIndexKodi"] in QueuedPlayingItem["IndexMappingSubtitleKodi"] and QueuedPlayingItem["SubtitleEnabled"]:
                        QueuedPlayingItem["EmbySessionData"].update({'SubtitleStreamIndex': QueuedPlayingItem["IndexMappingSubtitleKodi"][QueuedPlayingItem["SubtitleIndexKodi"]]})

                # Load playback data
                load_queuePlayingItem()
                EmbyPlaying = True
                PlayingItem = copy.Object(QueuedPlayingItem)
                QueuedPlayingItem.clear()

                # Init Playback
                init_EmbyPlayback()
                if EpisodeSelection:
                    webservice.AsyncCommandQueue.put((("SUBTITLE", EpisodeSelection),))

            elif Commands[0] == "play": # {"item":{"id":216,"type":"episode"},"player":{"playerid":1,"speed":1}}, '{"item":{"id":1100045814,"type":"song"},"player":{"playerid":-1,"speed":1}
                PlayingItemInit = copy.Object(QueuedPlayingItem)


                if utils.PauseSyncDuringPlayback:
                    utils.update_SyncPause('playing', True)
                    utils.set_SyncLock()

                EventData = json.loads(Commands[1])

                utils.closeall_ProgressBar()
                ProgressBarEnable = -1
                set_PlayerId(EventData)

                if EmbyPlaying:
                    stop_playback(False)

                if "item" in EventData:
                    if 'id' in EventData['item']:
                        ItemKodiSkipUpdate.append([EventData['item']['id'], EventData['item']['type']])
                        PlayItem = (EventData['item']['id'], EventData['item']['type'])
                    else:
                        PlayItem = (999999999, "unknown")


            elif Commands[0] == "pause": # {"item":{"id":22352,"type":"episode"},"player":{"playerid":1,"speed":0}}
                playerops.PlayerPause = True

                if not PlayingItem["EmbySessionData"]:
                    continue

                PositionTicks = playerops.PlayBackPosition()

                if PositionTicks:
                    PlayingItem["EmbySessionData"].update({'PositionTicks': PositionTicks, 'IsPaused': True})
                else:
                    PlayingItem["EmbySessionData"]['IsPaused'] = True

                if PlayingItem["EmbyServer"]:

                    report_progress("Pause")

            elif Commands[0] == "resume": # {"item":{"id":22352,"type":"episode"},"player":{"playerid":1,"speed":1}}
                playerops.PlayerPause = False

                if not PlayingItem["EmbySessionData"]:
                    continue

                if PlayingItem["EmbyServer"]:

                    PlayingItem["EmbySessionData"]['IsPaused'] = False
                    report_progress("Unpause")
                    TrackerPaused = True

            elif Commands[0] == "stop": # {'end': True, 'item': {'id': 33874, 'type': 'episode'}}; '{"end":false,"item":{"id":107446349,"type":"song"}}'
                EventData = json.loads(Commands[1])
                KodiId = 0
                KodiTypeId = 0
                utils.update_SyncPause('playing', False)
                utils.unset_SyncLock()
                ProgressBarEnable = 5
                ResetPlayItem = False

                if "item" in EventData: # remove from skipped items list
                    if 'id' in EventData['item']:
                        KodiId = EventData["item"]["id"]
                        KodiTypeId = EventData["item"]["type"]

                        if (KodiId, KodiTypeId) == PlayItem:
                            ResetPlayItem = True

                if PlayItem[1] =='unknown':
                    ResetPlayItem = True

                if KodiId:
                    if not EventData['end']: # remove from skipped items list
                        ItemsUpdateQueue.put(f'{{"DELETE": [{KodiId}, "{KodiTypeId}"]}}')  # Do not delete the item diectly from utils.ItemKodiSkipUpdate, to keep the events in order

                    # Dummy (blankwav) played
                    if ForceStopKodiId == EventData["item"]["id"]:
                        ForceStopKodiId = 0

                        if ResetPlayItem:
                            PlayItem = (0, "")

                        with utils.SafeLock(ForceStopCondition):
                            ForceStopCondition.notify_all()

                        continue

                playerops.AVStarted = False


                playerops.PlayerPause = False

                with utils.SafeLock(playerops.AVStartedCondition):
                    playerops.AVStartedCondition.notify_all()

                if not PlayingItem["EmbySessionData"]: # Playback never triggered avstart
                    if PlayingItemInit and PlayingItemInit["EmbySessionData"]: # Play was triggered, but avstart never did. This can happen on invalid streams.
                        PlayingItemInitLocal = copy.Object(PlayingItemInit)
                        PlayingItemInit = {"EmbySessionData": {}, "IntroStartPositionTicks": 0, "IntroEndPositionTicks": 0, "CreditsPositionTicks": 0, "EmbyServer": None, "KodiType": "", "IndexMappingVideoEmby": {}, "IndexMappingVideoKodi": {}, "IndexMappingAudioEmby": {}, "IndexMappingAudioKodi": {}, "IndexMappingSubtitleEmby": {}, "IndexMappingSubtitleKodi": {}, "SubtitleEnabled": False, "SubtitleIndexKodi": 0}
                        httpcache.delete(PlayingItemInitLocal["EmbySessionData"]["PlaySessionId"])


                    if ResetPlayItem:
                        PlayItem = (0, "")

                    with utils.SafeLock(ForceStopCondition):
                        ForceStopCondition.notify_all()

                    continue

                if EventData['end'] == "quit":
                    stop_playback(False)
                elif EventData['end']: # finished play and play next playlist item: {"end":true,"item":{"id":215,"type":"episode"}}
                    stop_playback(True)
                else: # stopped in playlist: '{"end":false,"item":{"id":215,"type":"episode"}}'; play next item but playlist is at the end: '{"end":false,"item":{"type":"unknown"}}, -> playback failed
                    stop_playback(False)

                if ResetPlayItem:
                    PlayItem = (0, "")

                with utils.SafeLock(ForceStopCondition):
                    ForceStopCondition.notify_all()

            elif Commands[0] == "volume":
                EventData = json.loads(Commands[1])
                Muted = EventData["muted"]
                Volume = EventData["volume"]

                if not PlayingItem["EmbySessionData"]:
                    continue

                PlayingItem["EmbySessionData"].update({'VolumeLevel': Volume, 'IsMuted': Muted})

                if PlayingItem["EmbyServer"]:
                    TrackerPaused = True
                    report_progress("VolumeChange")
            elif Commands[0] == "propertychanged":
                # {"player":{"playerid":1},"property":{"currentsubtitle":{"codec":"","index":9,"isdefault":false,"isforced":false,"isimpaired":false,"language":"de","name":"2 (External)"}}}
                # {"player":{"playerid":1},"property":{"currentsubtitle":{"codec":"SubRip","index":6,"isdefault":false,"isforced":false,"isimpaired":false,"language":"ja","name":""}}}
                # {"player":{"playerid":1},"property":{"subtitleenabled":false}}
                # {"player":{"playerid":1},"property":{"subtitleenabled":true}}
                # {"player":{"playerid":1},"property":{"currentaudiostream":{"bitrate":0,"channels":1,"codec":"AAC-LC 1.0","index":1,"isdefault":false,"isimpaired":false,"isoriginal":false,"language":"en","name":"Commentary"}}}
                # {"player":{"playerid":1},"property":{"currentaudiostream":{"bitrate":0,"channels":2,"codec":"AAC-LC 2.0","index":0,"isdefault":true,"isimpaired":false,"isoriginal":false,"language":"","name":""}}}
                # {'player': {'playerid': -1}, 'property': {'currentsubtitle': {'codec': '', 'index': 10, 'isdefault': False, 'isforced': False, 'isimpaired': False, 'language': 'de', 'name': '3 (External)'}}}

                if not PlayingItem["EmbySessionData"]:
                    continue

                EventData = json.loads(Commands[1])

                if "currentaudiostream" in EventData['property'] and "index" in EventData['property']["currentaudiostream"] and EventData['property']["currentaudiostream"]["index"] in PlayingItem["IndexMappingAudioKodi"]:
                    PlayingItem["EmbySessionData"].update({'AudioStreamIndex': PlayingItem["IndexMappingAudioKodi"][EventData['property']["currentaudiostream"]["index"]]})
                    TrackerPaused = True
                    report_progress("AudioTrackChange")
                elif "currentsubtitle" in EventData['property'] and "index" in EventData['property']["currentsubtitle"]:
                    PlayingItem["SubtitleIndexKodi"] = EventData['property']["currentsubtitle"]["index"]

                    if PlayingItem["SubtitleEnabled"] and PlayingItem["SubtitleIndexKodi"] in PlayingItem["IndexMappingSubtitleKodi"]:
                        PlayingItem["EmbySessionData"].update({'SubtitleStreamIndex': PlayingItem["IndexMappingSubtitleKodi"][PlayingItem["SubtitleIndexKodi"]]})
                        TrackerPaused = True
                        report_progress("SubtitleTrackChange")
                elif "subtitleenabled" in EventData['property']:
                    PlayingItem["SubtitleEnabled"] = EventData['property']["subtitleenabled"]

                    if not PlayingItem["SubtitleEnabled"]:
                        PlayingItem["EmbySessionData"].update({'SubtitleStreamIndex': -1})
                    elif PlayingItem["SubtitleIndexKodi"] in PlayingItem["IndexMappingSubtitleKodi"]:
                        PlayingItem["EmbySessionData"].update({'SubtitleStreamIndex': PlayingItem["IndexMappingSubtitleKodi"][PlayingItem["SubtitleIndexKodi"]]})

                    TrackerPaused = True
                    report_progress("SubtitleTrackChange")
                elif "repeat" in EventData['property']:
                    Repeat = parse_repeat(EventData['property']['repeat'])
                    playerops.RepeatMode[playerops.PlayerId] = Repeat
                    PlayingItem["EmbySessionData"].update({'RepeatMode': playerops.RepeatMode[playerops.PlayerId]})
                    TrackerPaused = True
                    report_progress("RepeatModeChange")
                elif "shuffled" in EventData['property']:
                    Shuffle = EventData['property']['shuffled']
                    playerops.Shuffled[playerops.PlayerId] = Shuffle
                    PlayingItem["EmbySessionData"].update({'Shuffle': playerops.Shuffled[playerops.PlayerId]})
                    TrackerPaused = True
                    report_progress("ShuffleChange")
            elif Commands[0] == "speedchanged": # {"item":{"id":215,"type":"episode"},"player":{"playerid":1,"speed":2}}
                if not PlayingItem["EmbySessionData"]:
                    continue

                EventData = json.loads(Commands[1])
                playerops.PlaybackRate[playerops.PlayerId] = float(playerops.GetTempo()) # Get real speed. Kodi has two speed params. tempo and speed. Tempo is (with audio, range 0.8 to 1.5). Speed is fast forward and accepts integers.
                PlayingItem["EmbySessionData"].update({'PlaybackRate': playerops.PlaybackRate[playerops.PlayerId]})
                TrackerPaused = True
                report_progress("PlaybackRateChange")
            elif Commands[0] == "clear": # '{"playlistid":1}'
                EventData = json.loads(Commands[1])
                playerops.PlaylistsPosition[EventData['playlistid']] = -1
                PlaylistKodi[EventData['playlistid']] = []

                if not PlayingItem["EmbySessionData"]:
                    continue

                TrackerPaused = True
                report_progress("PlaylistItemRemove")
            elif Commands[0] == "remove": # '{"playlistid":1,"position":0}'

                EventData = json.loads(Commands[1])
                PlaylistId = EventData['playlistid']
                Position = EventData['position']

                if playerops.PlaylistsPosition[PlaylistId] >= Position:
                    playerops.PlaylistsPosition[PlaylistId] -= 1

                if Position < len(PlaylistKodi[PlaylistId]):
                    del PlaylistKodi[PlaylistId][Position]

                if not PlayingItem["EmbySessionData"]:
                    continue

                TrackerPaused = True
                report_progress("PlaylistItemRemove")
            elif Commands[0] == "add": # unsyncd video = '{"item":{"id":1000018721,"type":"episode"},"playlistid":1,"position":0}'; synced video = '{"item":{"id":4268,"type":"episode"},"playlistid":1,"position":2}'; unsynced music = {"item":{"id":1000073262,"type":"song"},"playlistid":0,"position":0}; unsynced music external played e.g. via favorites'{"item":{"album":"Bella stella","artist":["Highland"],"title":"Bella stella","track":1,"type":"song"},"playlistid":0,"position":0}'; synced music = '{"item":{"id":233155,"type":"song"},"playlistid":0,"position":0}')
                EventData = json.loads(Commands[1])

                if playerops.PlaylistsPosition[EventData['playlistid']] >= EventData['position']:
                    playerops.PlaylistsPosition[EventData['playlistid']] += 1

                if 'id' in EventData['item']:
                    PlaylistKodi[EventData['playlistid']].insert(EventData['position'], {"KodiId": EventData['item']['id'], "KodiType": EventData['item']['type']})


def set_PlayerId(EventData):
    LocalPlayerId = -1

    if 'player' in EventData and 'playerid' in EventData['player']: # This can return -1 when no playlist is available. e.g. pleaylist clear during playback
        LocalPlayerId = EventData['player']['playerid']

    if LocalPlayerId == -1 and 'item' in EventData and 'type' in EventData['item']:
        if EventData['item']['type'] == "song":
            LocalPlayerId = 0
        elif EventData['item']['type'] in ("episode", "video", "movie", "musicvideo"):
            LocalPlayerId = 1

    if LocalPlayerId in (0, 1):
        playerops.PlayerId = LocalPlayerId

def parse_repeat(Data):
    if Data == "all":
        return "RepeatAll"

    if Data == "one":
        return "RepeatOne"

    return "RepeatNone"

def stop_playback(PlaybackEnded):
    global TrackerPaused
    global EmbyPlaying
    global PlayingItem

    PlayingItemLocal = copy.Object(PlayingItem)
    TrackerPaused = False
    playerops.PlaybackRate[playerops.PlayerId] = 1.0

    if MultiselectionDone:
        return

    if not PlaybackEnded:
        versions.clear_choice()

    if not PlayingItemLocal["EmbyServer"]:
        return

    EmbyPlaying = False
    PlayingItem = {"EmbySessionData": {}, "IntroStartPositionTicks": 0, "IntroEndPositionTicks": 0, "CreditsPositionTicks": 0, "EmbyServer": None, "KodiType": "", "IndexMappingVideoEmby": {}, "IndexMappingVideoKodi": {}, "IndexMappingAudioEmby": {}, "IndexMappingAudioKodi": {}, "IndexMappingSubtitleEmby": {}, "IndexMappingSubtitleKodi": {}, "SubtitleEnabled": False, "SubtitleIndexKodi": 0}

    if PlaybackEnded and PlayingItemLocal["EmbySessionData"]['RunTimeTicks']:
        PlayingItemLocal["EmbySessionData"]['PositionTicks'] = PlayingItemLocal["EmbySessionData"]['RunTimeTicks']

    if PlaybackEnded:
        KodiPositionSeconds = 0.0
    else:
        KodiPositionSeconds = PlayingItemLocal["EmbySessionData"]['PositionTicks'] / 10000000.0

    if PlayingItemLocal.get("EmbySessionStarted"):
        cache.update_userdata_Kodi(str(PlayingItemLocal["EmbySessionData"]['ItemId']), PlayingItemLocal["EmbyServer"].ServerData['ServerId'], KodiPositionSeconds, utils.currenttime(), PlaybackEnded, PlayingItemLocal["EmbySessionData"]['RunTimeTicks'] / 10000000.0, None)
        utils.ItemSkipUpdate.append(str(PlayingItemLocal["EmbySessionData"]['ItemId'])) # Skip Emby progress updates as Kodi keeps track
        PlayingItemLocal["EmbyServer"].API.session_stop(PlayingItemLocal["EmbySessionData"])
    else:
        httpcache.delete(PlayingItemLocal["EmbySessionData"]["PlaySessionId"])
    close_SkipIntroDialog()
    close_SkipCreditsDialog()


def PositionTracker():
    global PlayerBusyDelay
    global SkipIntroJumpDone
    global SkipCreditsJumpDone
    global TrackerPaused
    global ProgressBarEnable
    LoopCounter = 1
    PlayerBusy = False

    while True:
        # Enable progress bars 5 seconds after playback stop
        if ProgressBarEnable == 0:
            utils.openall_ProgressBar()
            ProgressBarEnable = -1
        elif ProgressBarEnable > 0:
            ProgressBarEnable -= 1

        # Disable sync 2 seconds before stop and for 5 seconds after start
        if PlayerBusyDelay:
            PlayerBusyDelay -= 1

            if not PlayerBusy:
                if utils.PauseSyncDuringPlaybackStateChange:
                    utils.update_SyncPause('playerbusy', True)

                PlayerBusy = True
        elif PlayerBusy:
            utils.update_SyncPause('playerbusy', False)
            PlayerBusy = False

        if utils.sleep(1):
            PlayerBusy = False
            return

        with utils.SafeLock(PlayerLock):
            if not EmbyPlaying or not PlayingItem["EmbySessionData"] or not PlayItem[0]:
                LoopCounter = 1
                continue

            PositionTicks = playerops.PlayBackPosition()
            RunTimeTicks = PlayingItem["EmbySessionData"].get('RunTimeTicks', 0)

            if not RunTimeTicks:
                RunTimeTicks = playerops.PlayBackDuration()
                PlayingItem["EmbySessionData"]['RunTimeTicks'] = RunTimeTicks

            if PositionTicks:
                PlayingItem["EmbySessionData"]['PositionTicks'] = PositionTicks

            if not PlayingItem.get("EmbySessionStarted") and PlayingItem["EmbyServer"]:
                start_EmbyPlayback()
                LoopCounter = 1

            if RunTimeTicks and (PositionTicks + 20000000) > RunTimeTicks: # 2 seconds before playback ends pause updates
                PlayerBusyDelay = 5

            if utils.enableSkipIntro:
                if PlayingItem["IntroStartPositionTicks"] < PositionTicks < PlayingItem["IntroEndPositionTicks"]:
                    if not SkipIntroJumpDone:
                        SkipIntroJumpDone = True

                        if utils.askSkipIntro:
                            SkipIntroDialog.show()
                        else:
                            jump_Intro()
                            LoopCounter = 0
                            continue
                else:
                    close_SkipIntroDialog()

            if utils.enableSkipCredits:
                if PlayingItem["CreditsPositionTicks"] and PositionTicks > PlayingItem["CreditsPositionTicks"]:
                    if not SkipCreditsJumpDone:
                        SkipCreditsJumpDone = True

                        if utils.askSkipCredits:
                            SkipCreditsDialog.show()
                        else:
                            jump_Credits()
                            LoopCounter = 0
                            continue
                else:
                    close_SkipCreditsDialog()
            if LoopCounter % 20 == 0 and PlayingItem["EmbyServer"]: # modulo 50
                if not TrackerPaused:
                    report_progress("TimeUpdate")
                else:
                    TrackerPaused = False

                LoopCounter = 0

            LoopCounter += 1

def jump_Intro():
    global SkipIntroJumpDone
    global TrackerPaused
    xbmc.log(f"EMBY.helper.player: Skip intro jump {PlayingItem['IntroEndPositionTicks']}", xbmc.LOGDEBUG)

    if PlayingItem["EmbyServer"]:
        playerops.Seek(PlayingItem["IntroEndPositionTicks"])
        PlayingItem["EmbySessionData"]['PositionTicks'] = PlayingItem["IntroEndPositionTicks"]
        SkipIntroJumpDone = True
        TrackerPaused = True
        report_progress("TimeUpdate")
    else:
        xbmc.log("EMBY.helper.player: Failed to skip intro", xbmc.LOGERROR)

def jump_Credits():
    global SkipCreditsJumpDone

    if PlayingItem["EmbySessionData"].get('RunTimeTicks', 0):
        xbmc.log(f"EMBY.helper.player: Skip credits jump {PlayingItem['EmbySessionData']['RunTimeTicks']}", xbmc.LOGDEBUG)
        playerops.Seek(PlayingItem["EmbySessionData"]['RunTimeTicks'])
        PlayingItem["EmbySessionData"]['PositionTicks'] = PlayingItem["EmbySessionData"]['RunTimeTicks']
        SkipCreditsJumpDone = True

def close_SkipIntroDialog():
    if SkipIntroDialog.dialog_open:
        SkipIntroDialog.close()

def close_SkipCreditsDialog():
    if SkipCreditsDialog.dialog_open:
        SkipCreditsDialog.close()

def load_queuePlayingItem():
    global PlayerBusyDelay
    PlayerBusyDelay = 5

    if not QueuedPlayingItem.get("Loaded", False):
        if QueuedPlayingItem["IntroStartPositionTicks"]:
            QueuedPlayingItem["IntroStartPositionTicks"] = QueuedPlayingItem["IntroStartPositionTicks"] * 10000000
        else:
            QueuedPlayingItem["IntroStartPositionTicks"] = 0

        if QueuedPlayingItem["IntroEndPositionTicks"]:
            QueuedPlayingItem["IntroEndPositionTicks"] = QueuedPlayingItem["IntroEndPositionTicks"] * 10000000
        else:
            QueuedPlayingItem["IntroEndPositionTicks"] = 0

        if QueuedPlayingItem["CreditsPositionTicks"]:
            QueuedPlayingItem["CreditsPositionTicks"] = QueuedPlayingItem["CreditsPositionTicks"] * 10000000
        else:
            QueuedPlayingItem["CreditsPositionTicks"] = 0

        playerops.AVStarted = False

        with utils.SafeLock(playerops.AVStartedCondition):
            playerops.AVStartedCondition.notify_all()

        QueuedPlayingItem["Loaded"] = True

def Cancel():
    versions.clear_choice()
    playerops.Stop()
    utils.update_SyncPause('playing', False)
    utils.unset_SyncLock()

def load_KodiItem(TaskId, KodiItemId, Type, CachedItem, MediaSourceIndex):
    if CachedItem:
        common.set_path_filename(CachedItem, CachedItem['ServerId'], versions.sort_sources(CachedItem['MediaSources'])[MediaSourceIndex], True)
        return CachedItem['ListItem']

    videodb = dbio.DBOpenRO("video", TaskId)

    if Type == "movie":
        KodiItem = videodb.get_movie_metadata_for_listitem(KodiItemId, "")
    elif Type == "episode":
        KodiItem = videodb.get_episode_metadata_for_listitem(KodiItemId, "")
    elif Type == "musicvideo":
        KodiItem = videodb.get_musicvideos_metadata_for_listitem(KodiItemId, "")
    else:
        KodiItem = {}

    dbio.DBCloseRO("video", TaskId)

    if KodiItem:
        listitem.set_ListItem_from_Kodi_database(KodiItem, "")
        return KodiItem['ListItem']

    return None

def replace_playlist_listitem(ListItem, Path):
    global PlaylistRemoveItem
    PlaylistRemoveItem = playerops.GetPlaylistPosition(1) # old listitem will be removed after play next
    playerops.XbmcPlaylists[1].add(Path, ListItem, PlaylistRemoveItem + 1)
    load_queuePlayingItem()

def get_version_context(ServerId, EmbyId, KodiType, Item=None):
    if KodiType != 'episode':
        versions.clear_choice()
        return None

    Item = Item or cache.get_ItemByEmbyId(EmbyId, ServerId) or {}
    if Item.get('SeriesId') and Item.get('SeasonId'):
        return str(ServerId), str(Item['SeriesId']), str(Item['SeasonId'])

    Server = utils.EmbyServers.get(ServerId)
    if not Server or not Server.library.SettingsLoaded:
        return None

    embydb = dbio.DBOpenRO(ServerId, 'version_context')
    try:
        KodiId = embydb.get_KodiId_by_EmbyId_EmbyType(EmbyId, 'Episode')
        if KodiId is None:
            return None
        videodb = dbio.DBOpenRO('video', 'version_context')
        try:
            Parents = videodb.get_episode_parent_ids(KodiId)
        finally:
            dbio.DBCloseRO('video', 'version_context')
        if Parents:
            SeriesId = embydb.get_EmbyId_by_KodiId_KodiType(Parents[0], 'tvshow')
            SeasonId = embydb.get_EmbyId_by_KodiId_KodiType(Parents[1], 'season')
            if SeriesId is not None and SeasonId is not None:
                return str(ServerId), str(SeriesId), str(SeasonId)
    finally:
        dbio.DBCloseRO(ServerId, 'version_context')
    return None


def selected_episode(Path):
    if not Path.startswith(utils.AddonModePath):
        return {}
    MetaData = metadata.load_selected_episode(Path[len(utils.AddonModePath) - 1:])
    return MetaData if MetaData.get('ServerId') in utils.EmbyServers else {}


def find_EmbyContent(FullPath, KodiId, KodiType):
    global QueuedPlayingItem
    EmbyId = 0
    ServerId = ""
    KodiItem = {}
    isDynamic = False
    MediaSources = []
    CachedItem = None

    if KodiId:
        EmbyId, ServerId = utils.get_EmbyId_ServerId_by_Fake_KodiId(KodiId) # Get Emby data injected by dynamic content

        if EmbyId:
            isDynamic = True

    # Get actual url
    FullPathMod = FullPath

    if FullPath.startswith("bluray://"):
        # Kodi stores each wrapped source as an encoded host, followed by the disc path.
        # Decode only that host per layer, preserving the HTTP source's own escaping.
        for Prefix in ("bluray://", "udf://"):
            if FullPathMod.startswith(Prefix):
                FullPathMod = unquote(FullPathMod[len(Prefix):].split('/', 1)[0])

    # Get cached item
    if EmbyId:
        CachedItem = cache.get_ItemByEmbyId(EmbyId, ServerId)

    if not CachedItem:
        CachedItem = cache.get_ItemByPath(FullPathMod)

    isAddonContent = FullPathMod.startswith("http://127.0.0.1:57342/")

    # happens for m3u playlists and other special content. Kodi does not recognize it's own content even it's in Kodi's database. Check if KodiId is available from addon's database
    # Player's ListItem must be updated
    if not CachedItem and not KodiId:
        # Addon mode
        if isAddonContent: # e.g. playlists played
            # QueuedPlayingItem is fully loaded at this point by webservice.py
            if not QueuedPlayingItem: # Playback was stopped, before
                return 0, isAddonContent, isDynamic, "", [], {}

            EmbyId = QueuedPlayingItem["EmbySessionData"]['ItemId']
            KodiType = QueuedPlayingItem["KodiType"]
            EmbyType = utils.KodiTypeMapping[KodiType]
        else:
            # Recover disc and redirected HTTP playback by path
            # QueuedPlayingItem is not set at this point, needs to be updated
            # No data available, try to load via path from synced content database
            ServerId = ""

            for ServerId, EmbyServer in list(utils.EmbyServers.items()):
                embydb = dbio.DBOpenRO(ServerId, "onAVStarted")
                EmbyId = embydb.get_mediasource_EmbyID_by_path(FullPathMod)

                if EmbyId:
                    KodiIdByMetadata, EmbyType, MediaSources = embydb.get_metadata_by_EmbyId_EmbyType(EmbyId, "")
                    dbio.DBCloseRO(ServerId, "onAVStarted")

                    if not EmbyType or ServerId not in utils.EmbyServers:
                        return 0, isAddonContent, isDynamic, "", [], {}

                    KodiType = utils.EmbyTypeMapping[EmbyType]
                    ActiveSource = versions.playing_source(MediaSources, FullPathMod)
                    QueuedPlayingItem = {
                        "EmbySessionData": {
                            "QueueableMediaTypes": ["Audio", "Video"],
                            "CanSeek": True,
                            "IsPaused": False,
                            "ItemId": EmbyId,
                            "MediaSourceId": ActiveSource["Id"],
                            "PlaySessionId": str(uuid.uuid4()).replace("-", ""),
                            "PositionTicks": 0,
                            "RunTimeTicks": 0,
                            "VolumeLevel": Volume,
                            "PlaybackRate": playerops.PlaybackRate[playerops.PlayerId],
                            "Shuffle": playerops.Shuffled[playerops.PlayerId],
                            "RepeatMode": playerops.RepeatMode[playerops.PlayerId],
                            "IsMuted": Muted
                        },
                        "IntroStartPositionTicks": ActiveSource.get("IntroStartPositionTicks", 0),
                        "IntroEndPositionTicks": ActiveSource.get("IntroEndPositionTicks", 0),
                        "CreditsPositionTicks": ActiveSource.get("CreditsPositionTicks", 0),
                        "EmbyServer": utils.EmbyServers[ServerId],
                        "KodiType": KodiType,
                        "IndexMappingVideoEmby": ActiveSource['IndexMappingVideoEmby'],
                        "IndexMappingVideoKodi": ActiveSource['IndexMappingVideoKodi'],
                        "IndexMappingAudioEmby": ActiveSource['IndexMappingAudioEmby'],
                        "IndexMappingAudioKodi": ActiveSource['IndexMappingAudioKodi'],
                        "IndexMappingSubtitleEmby": ActiveSource['IndexMappingSubtitleEmby'],
                        "IndexMappingSubtitleKodi": ActiveSource['IndexMappingSubtitleKodi'],
                        "SubtitleEnabled": False,
                        "SubtitleIndexKodi": 0
                    }
                    break

                dbio.DBCloseRO(ServerId, "onAVStarted")
            else: # not found
                return 0, isAddonContent, isDynamic, "", [], {}

            if KodiType == 'episode':
                videodb = dbio.DBOpenRO("video", "find_EmbyContent")
                KodiItem = videodb.get_episode_metadata_for_listitem(KodiIdByMetadata, FullPathMod)
                dbio.DBCloseRO("video", "find_EmbyContent")
                listitem.set_ListItem_from_Kodi_database(KodiItem, FullPath)
            elif KodiType == 'musicvideo':
                videodb = dbio.DBOpenRO("video", "find_EmbyContent")
                KodiItem = videodb.get_musicvideos_metadata_for_listitem(KodiIdByMetadata, FullPathMod)
                dbio.DBCloseRO("video", "find_EmbyContent")
                listitem.set_ListItem_from_Kodi_database(KodiItem, FullPath)
            elif KodiType == 'movie':
                videodb = dbio.DBOpenRO("video", "find_EmbyContent")
                KodiItem = videodb.get_movie_metadata_for_listitem(KodiIdByMetadata, FullPathMod)
                dbio.DBCloseRO("video", "find_EmbyContent")
                listitem.set_ListItem_from_Kodi_database(KodiItem, FullPath)
            elif KodiType == 'song':
                musicdb = dbio.DBOpenRO("music", "find_EmbyContent")
                KodiItem = musicdb.get_song_metadata_for_listitem(KodiIdByMetadata)
                dbio.DBCloseRO("music", "find_EmbyContent")
                listitem.set_ListItem_from_Kodi_database(KodiItem, FullPath)

            if 'ListItem' in KodiItem and not playerops.UpdateInfoTag(KodiItem['ListItem']):
                xbmc.log("EMBY.helper.player: UpdateInfoTag failed 1", xbmc.LOGERROR)
                return 0, isAddonContent, isDynamic, "", [], {}

            return EmbyId, isAddonContent, isDynamic, EmbyType, MediaSources, {}

    # found cached item (dynamic content)
    if CachedItem and "ServerId" in CachedItem and "Type" in CachedItem and CachedItem["ServerId"] in utils.EmbyServers:

        if FullPathMod.startswith("http://127.0.0.1:57342/"): # e.g. playlists played
            EmbyType = CachedItem["Type"]
        else: # Recover playback from the cached original path
            KodiType = utils.EmbyTypeMapping[CachedItem["Type"]]
            EmbyType = CachedItem["Type"]
            MediaSources = versions.sort_sources(CachedItem['MediaSources'])
            ActiveSource = versions.playing_source(MediaSources, FullPathMod)
            IndexMappingVideoEmby = {}
            IndexMappingVideoKodi = {}
            IndexMappingAudioEmby = {}
            IndexMappingAudioKodi = {}
            IndexMappingSubtitleEmby = {}
            IndexMappingSubtitleKodi = {}

            for MediaSourceData in (ActiveSource,):
                for IndexKodi, VideoStream in enumerate(MediaSourceData['KodiStreams']['Video']):
                    IndexMappingVideoEmby[str(VideoStream["Index"])] = IndexKodi
                    IndexMappingVideoKodi[IndexKodi] = str(VideoStream["Index"])

                for IndexKodi, AudioStream in enumerate(MediaSourceData['KodiStreams']['Audio']):
                    IndexMappingAudioEmby[str(AudioStream["Index"])] = IndexKodi
                    IndexMappingAudioKodi[IndexKodi] = str(AudioStream["Index"])

                for IndexKodi, SubtitleStream in enumerate(MediaSourceData['KodiStreams']['Subtitle']):
                    IndexMappingSubtitleEmby[str(SubtitleStream["Index"])] = IndexKodi
                    IndexMappingSubtitleKodi[IndexKodi] = str(SubtitleStream["Index"])

            QueuedPlayingItem = {
                "EmbySessionData": {
                    "QueueableMediaTypes": ["Audio", "Video"],
                    "CanSeek": True,
                    "IsPaused": False,
                    "ItemId": CachedItem['Id'],
                    "MediaSourceId": ActiveSource["Id"],
                    "PlaySessionId": str(uuid.uuid4()).replace("-", ""),
                    "PositionTicks": 0,
                    "RunTimeTicks": 0,
                    "VolumeLevel": Volume,
                    "PlaybackRate": playerops.PlaybackRate[playerops.PlayerId],
                    "Shuffle": playerops.Shuffled[playerops.PlayerId],
                    "RepeatMode": playerops.RepeatMode[playerops.PlayerId],
                    "IsMuted": Muted
                },
                "IntroStartPositionTicks": ActiveSource.get("IntroStartPositionTicks", 0),
                "IntroEndPositionTicks": ActiveSource.get("IntroEndPositionTicks", 0),
                "CreditsPositionTicks": ActiveSource.get("CreditsPositionTicks", 0),
                "EmbyServer": utils.EmbyServers[CachedItem["ServerId"]],
                "KodiType": KodiType,
                "IndexMappingVideoEmby": IndexMappingVideoEmby,
                "IndexMappingVideoKodi": IndexMappingVideoKodi,
                "IndexMappingAudioEmby": IndexMappingAudioEmby,
                "IndexMappingAudioKodi": IndexMappingAudioKodi,
                "IndexMappingSubtitleEmby": IndexMappingSubtitleEmby,
                "IndexMappingSubtitleKodi": IndexMappingSubtitleKodi,
                "SubtitleEnabled": False,
                "SubtitleIndexKodi": 0
            }

        return CachedItem['Id'], isAddonContent, isDynamic, EmbyType, MediaSources, CachedItem

    # Playback outside the loopback URL, not cached but with a KodiId
    # QueuedPlayingItem is not set at this point, needs to be updated
    if not isAddonContent and KodiId and not EmbyId:
        # KodiId available but no EmbyId. This is synced content played from Kodi's database. Try to load via KodiId from addon's database
        for ServerId, EmbyServer in list(utils.EmbyServers.items()):
            embydb = dbio.DBOpenRO(ServerId, "onAVStarted")
            EmbyId, EmbyType, IntroStartPosTicks, IntroEndPosTicks, CreditsStartPosTicks = embydb.get_playback_data_by_KodiId_KodiType(KodiId, KodiType)

            if not EmbyId:
                dbio.DBCloseRO(ServerId, "onAVStarted")
                continue

            MediaSourceId = embydb.get_mediasourceid_by_path(FullPathMod)
            _, EmbyType, MediaSources = embydb.get_metadata_by_EmbyId_EmbyType(EmbyId, EmbyType)
            dbio.DBCloseRO(ServerId, "onAVStarted")

            if not EmbyType or ServerId not in utils.EmbyServers:
                return 0, isAddonContent, isDynamic, "", [], {}

            KodiType = utils.EmbyTypeMapping[EmbyType]
            ActiveSource = versions.playing_source(MediaSources, FullPathMod, MediaSourceId)
            QueuedPlayingItem = {
                "EmbySessionData": {
                    "QueueableMediaTypes": ["Audio", "Video"],
                    "CanSeek": True,
                    "IsPaused": False,
                    "ItemId": EmbyId,
                    "MediaSourceId": ActiveSource["Id"],
                    "PlaySessionId": str(uuid.uuid4()).replace("-", ""),
                    "PositionTicks": 0,
                    "RunTimeTicks": 0,
                    "VolumeLevel": Volume,
                    "PlaybackRate": playerops.PlaybackRate[playerops.PlayerId],
                    "Shuffle": playerops.Shuffled[playerops.PlayerId],
                    "RepeatMode": playerops.RepeatMode[playerops.PlayerId],
                    "IsMuted": Muted
                },
                "IntroStartPositionTicks": ActiveSource.get("IntroStartPositionTicks", 0),
                "IntroEndPositionTicks": ActiveSource.get("IntroEndPositionTicks", 0),
                "CreditsPositionTicks": ActiveSource.get("CreditsPositionTicks", 0),
                "EmbyServer": EmbyServer,
                "KodiType": KodiType,
                "IndexMappingVideoEmby": ActiveSource['IndexMappingVideoEmby'],
                "IndexMappingVideoKodi": ActiveSource['IndexMappingVideoKodi'],
                "IndexMappingAudioEmby": ActiveSource['IndexMappingAudioEmby'],
                "IndexMappingAudioKodi": ActiveSource['IndexMappingAudioKodi'],
                "IndexMappingSubtitleEmby": ActiveSource['IndexMappingSubtitleEmby'],
                "IndexMappingSubtitleKodi": ActiveSource['IndexMappingSubtitleKodi'],
                "SubtitleEnabled": False,
                "SubtitleIndexKodi": 0
            }
            return EmbyId, isAddonContent, isDynamic, EmbyType, MediaSources, {}

        return 0, isAddonContent, isDynamic, "", [], {}

    return 0, isAddonContent, isDynamic, "", [], {}

def start_EmbyPlayback():
    global TrackerPaused
    SessionData = PlayingItem["EmbySessionData"]
    IsVideo = playerops.PlayerId == 1
    # Emby's unknown-duration fallback marks even a short playback as watched.
    if IsVideo and (SessionData['RunTimeTicks'] <= 0 or SessionData['PositionTicks'] <= 0):
        return

    utils.ItemSkipUpdate.append(str(SessionData['ItemId']))
    PlaylistEmby[playerops.PlayerId] = PlayingItem["EmbyServer"].API.session_playing(SessionData, PlaylistKodi[playerops.PlayerId], PlaylistEmby[playerops.PlayerId], playerops.PlaylistsPosition[playerops.PlayerId], ReportProgress=IsVideo)
    PlayingItem["EmbySessionStarted"] = True
    TrackerPaused = False


def report_progress(EventName):
    if PlayingItem.get("EmbySessionStarted"):
        PlaylistEmby[playerops.PlayerId] = PlayingItem["EmbyServer"].API.session_progress(PlayingItem["EmbySessionData"], EventName, PlaylistKodi[playerops.PlayerId], PlaylistEmby[playerops.PlayerId], playerops.PlaylistsPosition[playerops.PlayerId])


def init_EmbyPlayback():
    if PlayingItem["EmbySessionData"]:
        RunTimeTicks = playerops.PlayBackDuration()
        PositionTicks = playerops.PlayBackPosition()
        PlayingItem["EmbySessionData"].update({'RunTimeTicks': RunTimeTicks, 'PositionTicks': PositionTicks})

        if PlayingItem["EmbyServer"]:
            playerops.GetPlaylistPosition(playerops.PlayerId)
            start_EmbyPlayback()
        else:
            xbmc.log("EMBY.helper.player: Failed to initialize Emby playback", xbmc.LOGERROR)

        playerops.AVStarted = True

        with utils.SafeLock(playerops.AVStartedCondition):
            playerops.AVStartedCondition.notify_all()

Ret = utils.SendJson("Player.GetProperties", '{"playerid": 0, "properties": ["repeat", "shuffled"]}', False).get('result', {})
playerops.RepeatMode[0] = parse_repeat(Ret.get("repeat", "off"))
playerops.Shuffled[0] = Ret.get("shuffled", False)
Ret = utils.SendJson("Player.GetProperties", '{"playerid": 1, "properties": ["repeat", "shuffled"]}', False).get('result', {})
playerops.RepeatMode[1] = parse_repeat(Ret.get("repeat", "off"))
playerops.Shuffled[1] = Ret.get("shuffled", False)
Ret = utils.SendJson("Player.GetProperties", '{"playerid": 2, "properties": ["repeat", "shuffled"]}', False).get('result', {})
playerops.RepeatMode[2] = parse_repeat(Ret.get("repeat", "off"))
playerops.Shuffled[2] = Ret.get("shuffled", False)
SkipIntroDialog.set_JumpFunction(jump_Intro)
SkipCreditsDialog.set_JumpFunction(jump_Credits)
utils.start_thread(PlayerCommands, ())
utils.start_thread(PositionTracker, ())
