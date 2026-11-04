import json
import threading
from time import monotonic
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit
import uuid
import socket
import sqlite3
import xbmc
import xbmcplugin
from database import dbio
from emby import metadata, httpcache
from helper import utils, context, playerops, pluginmenu, player, xmls, queue, versions, artwork, cache, similar
sendOK = 'HTTP/1.1 200 OK\r\nServer: Emby-Next-Gen\r\nConnection: close\r\nContent-Length: 0\r\n\r\n'.encode()
sendNotFound = 'HTTP/1.1 404 Not Found\r\nServer: Emby-Next-Gen\r\nConnection: close\r\nContent-Length: 0\r\n\r\n'.encode()
sendHeadNotImplemented = 'HTTP/1.1 501 Not Implemented\r\nServer: Emby-Next-Gen\r\nConnection: close\r\n\r\n'.encode()
sendHeadPicture = 'HTTP/1.1 200 OK\r\nServer: Emby-Next-Gen\r\nConnection: close\r\nContent-Type: image/jpeg\r\nAccept-Ranges: none\r\n\r\n'.encode()
sendHeadAudio = 'HTTP/1.1 200 OK\r\nServer: Emby-Next-Gen\r\nConnection: close\r\nContent-Type: audio/unknown\r\nAccept-Ranges: none\r\n\r\n'.encode()
sendHeadVideo = 'HTTP/1.1 200 OK\r\nServer: Emby-Next-Gen\r\nConnection: close\r\nContent-Type: video/unknown\r\nAccept-Ranges: none\r\n\r\n'.encode()
Running = False
Socket = None
DelayedContent = {}
DelayedContentLock = threading.Lock()
EpisodeSelectionLock = threading.Lock()
EpisodeSelections = {}
EpisodeSelectionsByToken = {}
EpisodeVersionRequests = tuple(f"{Method} {metadata.EpisodeVersionApi}".encode() for Method in ("GET", "HEAD"))
SimilarRequests = tuple(f"{Method} {similar.API_PATH}".encode() for Method in ("GET", "HEAD", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"))
EpisodeRetryWindow = 1.0
EpisodeStopTimeout = 0.3
EpisodeResponseLifetime = 5.0
EmbyIdCurrentlyPlaying = 0
MaxWorkers = utils.WebserviceWorkers
WorkerQueue = queue.Queue()
AsyncCommandQueue = queue.Queue()
DelayedContentCondition = threading.Condition(threading.Lock())


class EpisodeSelection:
    def __init__(self, MetaData):
        self.Payload = MetaData['Payload']
        self.KodiId = int(MetaData['KodiId'])
        self.Token = f"episode-{MetaData['ETag']}"
        self.Ready = threading.Event()
        self.Response = sendNotFound
        self.Cancelled = False
        self.ReuseUntil = None
        self.Expires = None

# Load binary files once
BlackMP4 = utils.readFileBinary("special://home/addons/plugin.service.emby-next-gen/resources/black.mp4")
BlackMKV = utils.readFileBinary("special://home/addons/plugin.service.emby-next-gen/resources/black.mkv")
BlackAVI = utils.readFileBinary("special://home/addons/plugin.service.emby-next-gen/resources/black.avi")
BlackWEBM = utils.readFileBinary("special://home/addons/plugin.service.emby-next-gen/resources/black.webm")
BlackMOV = utils.readFileBinary("special://home/addons/plugin.service.emby-next-gen/resources/black.mov")
BlackTS = utils.readFileBinary("special://home/addons/plugin.service.emby-next-gen/resources/black.ts")
BlackMPEG = utils.readFileBinary("special://home/addons/plugin.service.emby-next-gen/resources/black.mpeg")
BlackWMV = utils.readFileBinary("special://home/addons/plugin.service.emby-next-gen/resources/black.wmv")
BlackOGV = utils.readFileBinary("special://home/addons/plugin.service.emby-next-gen/resources/black.ogv")
Black3GP = utils.readFileBinary("special://home/addons/plugin.service.emby-next-gen/resources/black.3gp")
BlackVOB = utils.readFileBinary("special://home/addons/plugin.service.emby-next-gen/resources/black.vob")
BlackFLV = utils.readFileBinary("special://home/addons/plugin.service.emby-next-gen/resources/black.flv")
BlackMXF = utils.readFileBinary("special://home/addons/plugin.service.emby-next-gen/resources/black.mxf")
BlackASF = utils.readFileBinary("special://home/addons/plugin.service.emby-next-gen/resources/black.asf")

# Generate HTTP responses
sendBlackMP4 = f'HTTP/1.1 200 OK\r\nServer: Emby-Next-Gen\r\nConnection: close\r\nContent-Length: {len(BlackMP4)}\r\nContent-Type: video/mp4\r\nAccept-Ranges: none\r\n\r\n'.encode() + BlackMP4
sendBlackMKV = f'HTTP/1.1 200 OK\r\nServer: Emby-Next-Gen\r\nConnection: close\r\nContent-Length: {len(BlackMKV)}\r\nContent-Type: video/x-matroska\r\nAccept-Ranges: none\r\n\r\n'.encode() + BlackMKV
sendBlackAVI = f'HTTP/1.1 200 OK\r\nServer: Emby-Next-Gen\r\nConnection: close\r\nContent-Length: {len(BlackAVI)}\r\nContent-Type: video/x-msvideo\r\nAccept-Ranges: none\r\n\r\n'.encode() + BlackAVI
sendBlackWEBM = f'HTTP/1.1 200 OK\r\nServer: Emby-Next-Gen\r\nConnection: close\r\nContent-Length: {len(BlackWEBM)}\r\nContent-Type: video/webm\r\nAccept-Ranges: none\r\n\r\n'.encode() + BlackWEBM
sendBlackMOV = f'HTTP/1.1 200 OK\r\nServer: Emby-Next-Gen\r\nConnection: close\r\nContent-Length: {len(BlackMOV)}\r\nContent-Type: video/quicktime\r\nAccept-Ranges: none\r\n\r\n'.encode() + BlackMOV
sendBlackTS = f'HTTP/1.1 200 OK\r\nServer: Emby-Next-Gen\r\nConnection: close\r\nContent-Length: {len(BlackTS)}\r\nContent-Type: video/mp2t\r\nAccept-Ranges: none\r\n\r\n'.encode() + BlackTS
sendBlackMPEG = f'HTTP/1.1 200 OK\r\nServer: Emby-Next-Gen\r\nConnection: close\r\nContent-Length: {len(BlackMPEG)}\r\nContent-Type: video/mpeg\r\nAccept-Ranges: none\r\n\r\n'.encode() + BlackMPEG
sendBlackWMV = f'HTTP/1.1 200 OK\r\nServer: Emby-Next-Gen\r\nConnection: close\r\nContent-Length: {len(BlackWMV)}\r\nContent-Type: video/x-ms-wmv\r\nAccept-Ranges: none\r\n\r\n'.encode() + BlackWMV
sendBlackOGV = f'HTTP/1.1 200 OK\r\nServer: Emby-Next-Gen\r\nConnection: close\r\nContent-Length: {len(BlackOGV)}\r\nContent-Type: video/ogg\r\nAccept-Ranges: none\r\n\r\n'.encode() + BlackOGV
sendBlack3GP = f'HTTP/1.1 200 OK\r\nServer: Emby-Next-Gen\r\nConnection: close\r\nContent-Length: {len(Black3GP)}\r\nContent-Type: video/3gpp\r\nAccept-Ranges: none\r\n\r\n'.encode() + Black3GP
sendBlackVOB = f'HTTP/1.1 200 OK\r\nServer: Emby-Next-Gen\r\nConnection: close\r\nContent-Length: {len(BlackVOB)}\r\nContent-Type: video/dvd\r\nAccept-Ranges: none\r\n\r\n'.encode() + BlackVOB
sendBlackFLV = f'HTTP/1.1 200 OK\r\nServer: Emby-Next-Gen\r\nConnection: close\r\nContent-Length: {len(BlackFLV)}\r\nContent-Type: video/x-flv\r\nAccept-Ranges: none\r\n\r\n'.encode() + BlackFLV
sendBlackMXF = f'HTTP/1.1 200 OK\r\nServer: Emby-Next-Gen\r\nConnection: close\r\nContent-Length: {len(BlackMXF)}\r\nContent-Type: application/mxf\r\nAccept-Ranges: none\r\n\r\n'.encode() + BlackMXF
sendBlackASF = f'HTTP/1.1 200 OK\r\nServer: Emby-Next-Gen\r\nConnection: close\r\nContent-Length: {len(BlackASF)}\r\nContent-Type: video/x-ms-asf\r\nAccept-Ranges: none\r\n\r\n'.encode() + BlackASF

def get_MediaHandler(Payload):
    p = Payload.lower()

    if p.endswith(".mp4") or p.endswith(".m4v"):
        return sendBlackMP4

    if p.endswith(".mkv"):
        return sendBlackMKV

    if p.endswith(".avi"):
        return sendBlackAVI

    if p.endswith(".ts") or p.endswith(".m2ts") or p.endswith(".mts"):
        return sendBlackTS

    if p.endswith(".mpg") or p.endswith(".mpeg") or p.endswith(".mpe"):
        return sendBlackMPEG

    if p.endswith(".webm"):
        return sendBlackWEBM

    if p.endswith(".mov"):
        return sendBlackMOV

    if p.endswith(".wmv"):
        return sendBlackWMV

    if p.endswith(".ogv"):
        return sendBlackOGV

    if p.endswith(".3gp"):
        return sendBlack3GP

    if p.endswith(".flv"):
        return sendBlackFLV

    if p.endswith(".mxf"):
        return sendBlackMXF

    if p.endswith(".vob"):
        return sendBlackVOB

    if p.endswith(".asf"):
        return sendBlackASF

    return sendBlackMP4

def start():
    global Running
    global Socket
    Running = True

    try: # intercept multiple start by different threads (just precaution)
        LocalSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        LocalSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        LocalSocket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        LocalSocket.bind(('127.0.0.1', 57342))
        Socket = LocalSocket
    except Exception as Error:
        xbmc.log(f"EMBY.hooks.webservice: Socket start (error) {Error}", xbmc.LOGERROR)
        Running = False
        return False

    # preload simultan workers
    for WorkerNumber in range(MaxWorkers):
        utils.start_thread(worker_Query, (WorkerNumber,))

    utils.start_thread(Listen, ())
    utils.start_thread(AsyncCommands, ())
    return True

def close():
    global Running

    if Running:
        Running = False
        with EpisodeSelectionLock:
            for Selection in EpisodeSelectionsByToken.values():
                Selection.Ready.set()
            EpisodeSelections.clear()
            EpisodeSelectionsByToken.clear()
        AsyncCommandQueue.put("QUIT")

        for _ in range(MaxWorkers):
            WorkerQueue.put("QUIT")

        try:
            Socket.close()
        except Exception:
            pass


def Listen():
    Socket.listen()
    Socket.settimeout(0.1)

    while not utils.SystemShutdown and Running:
        if EpisodeSelectionsByToken:
            expire_episode_selections()

        try:
            ClinetSocket, _ = Socket.accept()
        except:
            continue

        WorkerQueue.put(ClinetSocket)


def worker_Query(WorkerNumber):  # thread by caller

    while Running:
        Data = WorkerQueue.get()

        if Data == "QUIT":
            return

        client = Data
        client.settimeout(None)
        try:
            RequestData = client.recv(16384)
            IsSimilar = RequestData.startswith(SimilarRequests)
            if IsSimilar or RequestData.startswith(EpisodeVersionRequests):
                client.settimeout(1.0)
                # The Similar handler polls for disconnects after the request headers are read.
                RequestEnd = b'\r\n\r\n' if IsSimilar else b'\r\n'
                while RequestEnd not in RequestData and len(RequestData) < 131072:
                    Chunk = client.recv(16384)
                    if not Chunk:
                        break
                    RequestData += Chunk

                if RequestEnd in RequestData and len(RequestData) <= 131072:
                    Method, Path, _ = RequestData.split(b'\r\n', 1)[0].decode().split(' ', 2)
                    if IsSimilar:
                        serve_similar(client, Method, Path)
                    else:
                        serve_episode_version(client, Method, Path)
                client.close()
                continue

            if RequestData.startswith(b"EVENT service;multiversion;"):
                # The clicked item's encoded URL can span more than one socket read.
                client.settimeout(1.0)
                while not RequestData.endswith(b"\n") and len(RequestData) < 65536:
                    Chunk = client.recv(16384)
                    if not Chunk:
                        break
                    RequestData += Chunk

                if not RequestData.endswith(b"\n") or len(RequestData) > 65536:
                    client.close()
                    continue

                RequestData = RequestData[:-1]

            data = RequestData.decode()
        except (OSError, UnicodeError, ValueError):
            client.close()
            continue

        IncomingData = data.split(' ')

        if len(IncomingData) < 2 or (IncomingData[0] != "EVENT" and not IncomingData[1].startswith('/')):
            client.send(sendNotFound)
            client.close()
            continue

        if IncomingData[0] not in ("EVENT", "GET", "HEAD"):
            client.send(sendHeadNotImplemented)
            client.close()
            continue

        # events by event.py
        if IncomingData[0] == "EVENT":
            args = IncomingData[1].split(";")

            if len(args) < 2:
                client.send(sendNotFound)
                client.close()
                continue

            if args[1] == "multiversion":
                client.send(sendOK)
                client.close()
                context.multiversion(unquote(args[2]) if len(args) > 2 else "")
                continue


            if args[1] == "refreshitem":
                client.send(sendOK)
                client.close()
                context.refreshitem()
                continue


            if args[1] == "settings":
                client.send(sendOK)
                client.close()
                xbmc.executebuiltin('Addon.OpenSettings(plugin.service.emby-next-gen)')
                continue

            # Remaining events use a numeric plugin handle. Retired menu actions end here.
            if len(args) < 3 or not args[1].lstrip("-").isdigit():
                client.send(sendNotFound)
                client.close()
                continue

            # no delay
            params = args[2]

            if params.endswith("/&reload="):
                params = params[:-9]
            elif params.endswith("/"):
                params = params[:-1]

            Handle = args[1]
            params = dict(parse_qsl(params[1:]))
            mode = params.get('mode', "")
            ServerId = params.get('server', "")

            if mode == 'settings':  # Simple commands
                client.send(sendOK)
                client.close()
                xbmc.executebuiltin('Addon.OpenSettings(plugin.service.emby-next-gen)')
                continue

            if mode == 'managelibsselection':  # Simple commands
                client.send(sendOK)
                client.close()
                pluginmenu.select_managelibs()
                continue


            if mode == 'nodesreset':  # Simple commands
                client.send(sendOK)
                client.close()
                utils.nodesreset()
                continue


            if mode == 'play':
                client.send(sendOK)
                client.close()
                playerops.PlayEmby((params.get('item'),), "PlayNow", -1, -1, utils.EmbyServers[ServerId].ServerData, utils.EmbyServers[ServerId].API)
                continue

            if mode == 'syncednodes' or (mode == 'browse' and params.get('query') == 'NodesSynced'):
                Media = params.get('media') or {'audio': 'music', 'video': 'video'}.get(params.get('contentsupported'), "")
                pluginmenu.listing(Handle, ServerId, Media)
            elif mode in ('browse', 'search'):
                # Retired URLs must not reopen server-side dynamic browsing.
                xbmcplugin.endOfDirectory(int(Handle), succeeded=False, cacheToDisc=False, updateListing=False)
            elif mode == 'playlist':
                pluginmenu.get_playlist(Handle, ServerId, params['mediatype'], params.get('id', ""), params.get('playlistid', ""))
            elif mode == 'nextepisodes':
                pluginmenu.get_next_episodes(Handle, params['libraryname'])
            elif mode == 'nextepisodesplayed':
                pluginmenu.get_next_episodes_played(Handle, params['libraryname'])
            elif mode == 'favepisodes':
                pluginmenu.favepisodes(Handle)
            elif mode == 'favseasons':
                pluginmenu.favseasons(Handle)
            elif mode == 'inprogressmixed':
                pluginmenu.get_inprogress_mixed(Handle)
            elif mode == 'recentlyaddedmusicvideoalbums':
                pluginmenu.get_recentlyadded_musicvideosalbums(Handle, params.get('libraryname'))
            else:  # 'listing'
                pluginmenu.listing(Handle)

            client.send(sendOK)
            client.close()
            continue

        # Detect content type
        isPicture = False
        isAudio = False
        isVideo = False
        isDelayedContent = IncomingData[1].startswith("/delayed_content/")
        Payload = IncomingData[1].replace("/delayed_content", "")

        if "/picture/" in IncomingData[1]:
            isPicture = True
        elif "/audio/" in IncomingData[1]:
            isAudio = True
        else:
            isVideo = True

        PayloadLower = Payload.lower()

        if PayloadLower.endswith('/') or 'extrafanart' in PayloadLower or 'extrathumbs' in PayloadLower or 'extras/' in PayloadLower or PayloadLower.endswith('.edl') or PayloadLower.endswith('index.bdmv') or PayloadLower.endswith('index.bdm') or PayloadLower.endswith('.txt') or PayloadLower.endswith('.vprj') or PayloadLower.endswith('.xml') or PayloadLower.endswith('.nfo') or (not isPicture and (PayloadLower.endswith('.bmp') or PayloadLower.endswith('.jpg') or PayloadLower.endswith('.jpeg') or PayloadLower.endswith('.ico') or PayloadLower.endswith('.png') or PayloadLower.endswith('.ifo') or PayloadLower.endswith('.gif') or PayloadLower.endswith('.tbn') or PayloadLower.endswith('.tiff'))): # Filter invalid requests
            client.send(sendNotFound)
        else: # Process request
            if IncomingData[0] == "GET":
                GetRequest(client, Payload, isDelayedContent, isPicture, isAudio, isVideo)
            elif IncomingData[0] == "HEAD":
                if isPicture or isAudio:
                    MimeType, _ = utils.get_MimeType(Payload)

                    if not MimeType:
                        if isPicture:
                            client.send(sendHeadPicture)
                        elif isAudio:
                            client.send(sendHeadAudio)
                    else:
                        client.send(f'HTTP/1.1 200 OK\r\nServer: Emby-Next-Gen\r\nConnection: close\r\nContent-Type: {MimeType}\r\nAccept-Ranges: none\r\n\r\n'.encode())
                else: # Send a neutral mime type, otherwise not possible to change it after head request (multi content selection)
                    client.send(sendHeadVideo)
            else:
                client.send(sendOK)

        client.close()
        del client
        del IncomingData


def serve_similar(client, Method, Request):
    Deadline = monotonic() + 10.0
    client.setblocking(False)

    def ClientDisconnected():
        try:
            return not client.recv(1, socket.MSG_PEEK)
        except BlockingIOError:
            return False
        except OSError:
            return True

    def Cancelled():
        return monotonic() >= Deadline or ClientDisconnected()

    Status = 200
    try:
        Path, _, Query = Request.partition('?')
        if Path != f"{similar.API_PATH}similar":
            raise similar.QueryError(404, "not_found")
        if Method != 'GET':
            raise similar.QueryError(405, "method_not_allowed")
        try:
            Pairs = parse_qsl(Query, keep_blank_values=True, strict_parsing=True, max_num_fields=3)
            Params = dict(Pairs)
            if len(Pairs) != len(Params) or set(Params) - {'type', 'dbid', 'limit'}:
                raise ValueError
            KodiType = Params['type']
            if KodiType not in similar.MEDIA_TYPES or not Params['dbid'].isascii() or not Params['dbid'].isdecimal():
                raise ValueError
            KodiId = int(Params['dbid'])
            LimitText = Params.get('limit', str(similar.DEFAULT_LIMIT))
            if not LimitText.isascii() or not LimitText.isdecimal():
                raise ValueError
            Limit = int(LimitText)
            if not 0 < KodiId <= 2147483647 or not 1 <= Limit <= similar.MAX_LIMIT:
                raise ValueError
        except (KeyError, ValueError):
            raise similar.QueryError(400, "invalid_request") from None
        Data = similar.get_items(KodiType, KodiId, Limit, Cancelled)
        if monotonic() >= Deadline:
            raise similar.QueryError(502, "upstream_error")
    except similar.QueryError as Error:
        Status, Data = Error.status, {'error': Error.code}
    except (sqlite3.Error, KeyError):
        Status, Data = 503, {'error': 'unavailable'}
    except Exception as Error:
        xbmc.log(f"EMBY.hooks.webservice: Similar API failed: {type(Error).__name__}", xbmc.LOGERROR)
        Status, Data = 500, {'error': 'internal_error'}

    if ClientDisconnected():
        return

    Reason = {200: 'OK', 400: 'Bad Request', 404: 'Not Found', 405: 'Method Not Allowed',
              500: 'Internal Server Error', 502: 'Bad Gateway', 503: 'Service Unavailable'}[Status]
    Body = json.dumps(Data).encode('utf-8')
    Allow = "Allow: GET\r\n" if Status == 405 else ""
    Header = (f"HTTP/1.1 {Status} {Reason}\r\nConnection: close\r\nContent-Type: application/json\r\n"
              f"Cache-Control: no-store\r\n{Allow}Content-Length: {len(Body)}\r\n\r\n")
    try:
        client.settimeout(1.0)
        client.sendall(Header.encode() + (b'' if Method == 'HEAD' else Body))
    except OSError:
        pass


def episode_source_label(Path):
    if "://" not in Path:
        return Path

    Url = urlsplit(Path.split('|', 1)[0])
    return f"{Url.hostname or ''}{unquote(Url.path)}"


def serve_episode_version(client, Method, Request):
    Path, _, Query = Request.partition('?')
    if Path.startswith(metadata.EpisodeMediaPrefix):
        MetaData = metadata.load_selected_episode(Path)
        if not MetaData or MetaData['ServerId'] not in utils.EmbyServers:
            send_episode_response(client, sendNotFound)
        elif Method == 'HEAD':
            send_episode_response(client, sendHeadVideo)
        else:
            send_redirect(client, MetaData, f"videos/{MetaData['EmbyId']}/stream?static=true", AddCache=False)
        return

    Action = Path.removeprefix(metadata.EpisodeVersionApi)
    Params = dict(parse_qsl(Query))
    if Method != 'GET' or Action not in ('versions', 'resolve') or 'path' not in Params:
        send_episode_response(client, sendNotFound)
        return

    MetaData = metadata.load_episode_versions(Params['path'])
    if not MetaData:
        send_episode_response(client, sendNotFound)
        return

    Sources = MetaData['MediaSources']
    if Action == 'versions':
        Mode = Params.get('mode')
        Preferred = 0 if len(Sources) == 1 else None
        if Preferred is None and Mode != 'select':
            Context = player.get_version_context(MetaData['ServerId'], MetaData['EmbyId'], 'episode')
            Preferred = versions.recall_choice(Sources, Context, clear_mismatch=False)
            if Preferred is None and utils.autoSelectHighestPlaybackResolution:
                Preferred = versions.highest_resolution_index(Sources)
            if Preferred is None and Mode == 'next':
                Preferred = 0
        send_episode_json(client, {'preferred': Preferred, 'versions': [
            {'id': Source[0]['Id'], 'name': Source[0]['Name'],
             'pathLabel': episode_source_label(Source[0]['Path']),
             'size': utils.SizeToText(Source[0]['Size'] or 0),
             'width': Source[1][0]['Width'] if Source[1] else 0}
            for Source in Sources]})
        return

    for Source, *_ in Sources:
        if Source['Id'] == Params.get('source'):
            break
    else:
        send_episode_response(client, sendNotFound)
        return

    Payload = MetaData['Payload'].rsplit('/', 1)[0] + '/stream'
    Selection = f"{metadata.EpisodeMediaPrefix}{uuid.uuid4().hex}/{Source['Id'].encode('utf-8').hex()}{Payload}"
    PlaybackPath = f"http://127.0.0.1:57342{Selection}|redirect-limit=1000&connection-timeout={utils.httpConnectionTimeout}"

    send_episode_json(client, {'path': PlaybackPath})


def send_episode_json(client, Data):
    Body = json.dumps(Data).encode('utf-8')
    Header = f"HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Type: application/json\r\nContent-Length: {len(Body)}\r\n\r\n"
    send_episode_response(client, Header.encode() + Body)


def start_selected_episode(MetaData):
    global EmbyIdCurrentlyPlaying
    EmbyIdCurrentlyPlaying = MetaData['EmbyId']
    Context = player.get_version_context(MetaData['ServerId'], MetaData['EmbyId'], 'episode')
    versions.remember_choice(MetaData['MediaSources'], MetaData['SelectionIndexMediaSource'], Context)
    set_QueuedPlayingItem(MetaData)


def LoadISO(MetaData, client, PlaybackPath=None): # Disc image handed to Kodi
    player.MultiselectionDone = True
    Path = MetaData['MediaSources'][MetaData['SelectionIndexMediaSource']][0]['Path']

    if Path.startswith('\\\\'):
        Path = Path.replace('\\\\', "smb://", 1).replace('\\\\', "\\").replace('\\', "/")

    MetaData['MediaSources'][MetaData['SelectionIndexMediaSource']][0]['Path'] = Path
    ListItem = None
    if PlaybackPath and MetaData['isDynamic']:
        ListItem = cache.get_ItemByEmbyId(MetaData['EmbyId'], MetaData['ServerId']).get('ListItem')
    if not ListItem:
        ListItem = player.load_KodiItem("LoadISO", MetaData['KodiId'], MetaData['KodiType'], None, 0)

    if not ListItem:
        if client is None:
            return sendOK

        client.send(sendOK)
    else:
        set_QueuedPlayingItem(MetaData)
        player.replace_playlist_listitem(ListItem, PlaybackPath or Path)
        Response = get_MediaHandler(MetaData['Payload'])
        if client is None:
            if MetaData['KodiId']:
                player.ForceStopKodiId = int(MetaData['KodiId'])
            return Response

        set_DelayedContent(MetaData['ETag'], Response, 1, MetaData['KodiId'])

def build_Path(MetaData, Data):
    if "?" in Data:
        Parameter = "&"
    else:
        Parameter = "?"

    _, Format = utils.get_MimeType(MetaData['MediaSources'][MetaData['SelectionIndexMediaSource']][0]['Path'])


    if Format != "unknown":

        Data = Data.replace("/stream?", f"/stream.{Format}?")


    Path = f"{utils.EmbyServers[MetaData['ServerId']].ServerData['ServerUrl']}/emby/{Data}{Parameter}MediaSourceId={MetaData['MediaSources'][MetaData['SelectionIndexMediaSource']][0]['Id']}&PlaySessionId={MetaData['PlaySessionId']}&DeviceId={utils.EmbyServers[MetaData['ServerId']].ServerData['DeviceId']}&api_key={utils.EmbyServers[MetaData['ServerId']].ServerData['AccessToken']}"
    return Path

def send_redirect(client, MetaData, Data, AddCache=True):

    if AddCache:
        httpcache.add(MetaData, Data)

    Path = MetaData['MediaSources'][MetaData['SelectionIndexMediaSource']][0]['Path']
    if not Path.lower().startswith(('http://', 'https://')):
        Path = build_Path(MetaData, Data)

    SendData = f"HTTP/1.1 307 Temporary Redirect\r\nServer: Emby-Next-Gen\r\nConnection: close\r\nLocation: {Path}\r\nContent-Length: 0\r\nAccept-Ranges: none\r\n\r\n".encode()

    if client is None:
        return SendData

    if MetaData.get('EpisodeSelection'):
        send_episode_response(client, SendData)
        return

    try:
        client.send(SendData)
    except:
        set_DelayedContent(MetaData['ETag'], SendData, 0, 0)

def GetRequest(client, Payload, isDelayedContent, isPicture, isAudio, isVideo):
    # Delayed contents are used for user inputs (selection box for e.g. multicontent versions)
    # workaround for low Kodi network timeout settings, for long running processes. "delayed_content" folder is actually a redirect to keep timeout below threshold

    # Reuse the playback response when Kodi repeats a request.
    HTTPCache = httpcache.get(Payload) if not metadata.MediaSourceContextMenu else None

    if HTTPCache:
        send_redirect(client, HTTPCache[0], HTTPCache[1], False)
        return

    global EmbyIdCurrentlyPlaying

    # Delayed content used for e.g. multiselection episodes
    if isDelayedContent:
        Etag = Payload[1:]

        if Etag.startswith('episode-'):
            send_episode_selection(client, Etag)
            return

        if send_delayed_content(client, Etag):
            return

        with utils.SafeLock(DelayedContentCondition):
            Wait = int((utils.curltimeouts - 0.5) * 10)

            while Wait > 0:
                if DelayedContentCondition.wait(timeout=0.1):
                    break

                Wait -= 1

            if utils.SystemShutdown:
                client.send(sendNotFound)
                return

            if send_delayed_content(client, Etag):
                return

            client.send(f"HTTP/1.1 307 Temporary Redirect\r\nServer: Emby-Next-Gen\r\nConnection: close\r\nLocation: http://127.0.0.1:57342/delayed_content/{Etag}\r\nAccept-Ranges: none\r\nContent-Length: 0\r\n\r\n".encode())
            return

    # Load parameters from url request
    MetaData = metadata.load_MetaData(Payload, isPicture, isAudio)

    if not MetaData: # Invalid request
        client.send(sendNotFound)
        return

    if isVideo and Payload.endswith(f"/{metadata.SelectedIsoFilename}") and len(MetaData['MediaSources']) == 1:
        if MetaData['MediaSources'][0][0].get('HttpIsoRecord'):
            # LoadISO already queued the session. Disc reads must only resolve its fixed source.
            send_episode_response(client, send_redirect(None, MetaData, "", AddCache=False))
            return

    MultiVersionEpisode = MetaData['KodiType'] == 'episode' and len(MetaData['MediaSources']) > 1
    if MultiVersionEpisode and reuse_episode_selection(MetaData, client):
        return

    MetaData['ETag'] = f'{str(uuid.uuid4()).replace("-", "")}{Payload[-5:]}'

    if MetaData['KodiType'] in ("movie", "episode", "musicvideo", "video"):
        playerops.PlayerId = 1
    elif MetaData['KodiType'] == "audio":
        playerops.PlayerId = 0

    # Set player id
    if isVideo:
        if not MultiVersionEpisode:
            player.PlaylistRemoveItem = -1
        player.set_PlayerId({"player": {"playerid": 1}})
    elif isAudio:
        player.set_PlayerId({"player": {"playerid": 0}})

    # Waiting for Emby connection:
    if not wait_for_Embyserver(client, MetaData['ServerId'], MetaData):
        return

    if MetaData['KodiType'] == 'picture':

        if MetaData['ImageTag'] != "noimage":
            Params = artwork.image_params(MetaData['ImageProfile'], MetaData['ImageTag'])
            Params['api_key'] = utils.EmbyServers[MetaData['ServerId']].ServerData['AccessToken']
            client.send(f"HTTP/1.1 307 Temporary Redirect\r\nServer: Emby-Next-Gen\r\nConnection: close\r\nLocation: {utils.EmbyServers[MetaData['ServerId']].ServerData['ServerUrl']}/emby/Items/{MetaData['EmbyId']}/Images/{MetaData['ImageType']}/{MetaData['ImageIndex']}?{urlencode(Params)}\r\nAccept-Ranges: none\r\nContent-Length: 0\r\n\r\n".encode())
            return

        BinaryData = utils.noimagejpg
        client.send(f"HTTP/1.1 200 OK\r\nServer: Emby-Next-Gen\r\nConnection: close\r\nContent-Length: {len(BinaryData)}\r\nContent-Type: image/jpeg\r\nAccept-Ranges: none\r\n\r\n".encode() + BinaryData)
        return

    if MetaData['KodiType'] == 'audio':
        set_QueuedPlayingItem(MetaData)
        send_redirect(client, MetaData, f"audio/{MetaData['EmbyId']}/stream?static=true")
        return

    EmbyIdCurrentlyPlaying = MetaData['EmbyId']


    VersionContext = player.get_version_context(MetaData['ServerId'], MetaData['EmbyId'], MetaData['KodiType'])
    RememberedIndex = versions.recall_choice(MetaData['MediaSources'], VersionContext)

    if len(MetaData['MediaSources']) == 1 or (MetaData['MediaType'] in ("i", "v", "m") and not MetaData['isDynamic']): # no multiversion select for iso or movie/video -> Kodi takes care
        if MetaData['MediaType'] == 'i':
            if add_DelayedContent(MetaData, client):
                return

            LoadISO(MetaData, client)
            return

        LoadData(MetaData, client)
        return

    # Select multiversion content
    ExplicitChoice = metadata.MediaSourceContextMenu
    metadata.MediaSourceContextMenu = None
    SelectionIndex = None
    if ExplicitChoice and ExplicitChoice[:2] == (MetaData['ServerId'], MetaData['EmbyId']):
        SelectionIndex = next((Index for Index, Source in enumerate(MetaData['MediaSources']) if Source[0]['Id'] == ExplicitChoice[2]), None)
    if SelectionIndex is None:
        SelectionIndex = RememberedIndex

    if MultiVersionEpisode and SelectionIndex is not None and reuse_episode_selection(MetaData, client):
        return

    if SelectionIndex is None and utils.autoSelectHighestPlaybackResolution:
        SelectionIndex = versions.highest_resolution_index(MetaData['MediaSources'])

    if SelectionIndex is None: # Manual select mediasource
        if MultiVersionEpisode:
            select_episode_version(MetaData, client, VersionContext)
            return

        if add_DelayedContent(MetaData, client):
            return

        SelectionIndex = choose_media_source(MetaData)

        if SelectionIndex == -1: # Cancel
            versions.clear_choice()
            set_DelayedContent(MetaData['ETag'], get_MediaHandler(MetaData['Payload']), 1, MetaData['KodiId'])
            playerops.Stop()
            return

    if MultiVersionEpisode:
        player.PlaylistRemoveItem = -1

    play_selected_version(MetaData, client, SelectionIndex, VersionContext)

def choose_media_source(MetaData):
    Choices = [f"{Source[0]['Name']} - {utils.SizeToText(Source[0].get('Size'))} - {Source[0]['Path']}" for Source in MetaData['MediaSources']]
    return utils.Dialog.select(utils.Translate(33453), Choices, preselect=0)

def play_selected_version(MetaData, client, SelectionIndex, VersionContext):
    MetaData['SelectionIndexMediaSource'] = SelectionIndex
    MetaData['VersionSelectionDone'] = True
    versions.remember_choice(MetaData['MediaSources'], SelectionIndex, VersionContext)

    # Hand disc images selected from multiple versions to Kodi
    Source = MetaData['MediaSources'][SelectionIndex][0]
    if Source.get('HttpIsoRecord'):
        Payload = metadata.selected_iso_payload(MetaData['Payload'], Source['HttpIsoRecord'])
        PlaybackPath = f"{utils.AddonModePath}{Payload[1:]}|redirect-limit=1000&failonerror=false&connection-timeout={utils.httpConnectionTimeout}"
        return LoadISO(MetaData, client, PlaybackPath)

    if Source['Path'].lower().endswith(".iso"):
        return LoadISO(MetaData, client)

    return LoadData(MetaData, client)

def get_episode_selection(Payload):
    # Caller holds EpisodeSelectionLock.
    Selection = EpisodeSelections.get(Payload)
    if Selection and (Selection.ReuseUntil is None or monotonic() < Selection.ReuseUntil):
        return Selection
    return None

def reuse_episode_selection(MetaData, client):
    Payload = MetaData['Payload']
    with EpisodeSelectionLock:
        Selection = get_episode_selection(Payload)
        if not Selection:
            return False

        ExplicitChoice = metadata.MediaSourceContextMenu
        if Selection.Ready.is_set() and ExplicitChoice and ExplicitChoice[:2] == (MetaData['ServerId'], MetaData['EmbyId']):
            del EpisodeSelections[Payload]
            return False

    redirect_episode_selection(client, Selection)
    return True

def expire_episode_selections():
    Now = monotonic()
    with EpisodeSelectionLock:
        for Payload, Selection in list(EpisodeSelections.items()):
            if Selection.ReuseUntil is not None and Now >= Selection.ReuseUntil:
                del EpisodeSelections[Payload]

        for Token, Selection in list(EpisodeSelectionsByToken.items()):
            if Selection.Expires is not None and Now >= Selection.Expires:
                del EpisodeSelectionsByToken[Token]

def release_cancelled_episode(KodiId):
    # Keep serving requests with the old token, but allow a new play of the original URL.
    with EpisodeSelectionLock:
        for Payload, Selection in list(EpisodeSelections.items()):
            if Selection.Cancelled and Selection.KodiId == KodiId:
                del EpisodeSelections[Payload]

def send_episode_response(client, Response):
    try:
        client.settimeout(1.0)
        client.sendall(Response)
        return True
    except OSError:
        # Kodi may close its request as soon as playback stops.
        return False

def redirect_episode_selection(client, Selection):
    return send_episode_response(client, f"HTTP/1.1 307 Temporary Redirect\r\nServer: Emby-Next-Gen\r\nLocation: http://127.0.0.1:57342/delayed_content/{Selection.Token}\r\nConnection: close\r\nContent-Length: 0\r\nAccept-Ranges: none\r\n\r\n".encode())

def send_episode_selection(client, Token):
    with EpisodeSelectionLock:
        Selection = EpisodeSelectionsByToken.get(Token)
        if Selection and Selection.Expires is not None and monotonic() >= Selection.Expires:
            Selection = None

    if not Selection or utils.SystemShutdown:
        send_episode_response(client, sendNotFound)
    elif Selection.Ready.wait(timeout=max(0.1, utils.curltimeouts - 0.5)):
        send_episode_response(client, Selection.Response)
    else:
        redirect_episode_selection(client, Selection)

def cancel_episode_selection(Selection):
    with EpisodeSelectionLock:
        Selection.Cancelled = True

    OwnerPaths = (f"http://127.0.0.1:57342{Selection.Payload}",
                  f"http://127.0.0.1:57342/delayed_content/{Selection.Token}")
    if playerops.GetPlayerFilepath().split('|', 1)[0] not in OwnerPaths:
        return sendNotFound

    # Never wait for Kodi to join an HTTP reader that may still need this response.
    xbmc.executebuiltin('PlayerControl(Stop, 1)')
    Deadline = monotonic() + EpisodeStopTimeout
    while monotonic() < Deadline and not utils.sleep(0.05):
        PlayingPath = playerops.GetPlayerFilepath().split('|', 1)[0]
        if not PlayingPath:
            return get_MediaHandler(Selection.Payload)
        if PlayingPath not in OwnerPaths:
            break

    # With no confirmed stop, avoid handing Kodi a playable placeholder.
    return sendNotFound

def select_episode_version(MetaData, client, VersionContext):
    Payload = MetaData['Payload']
    with EpisodeSelectionLock:
        Selection = get_episode_selection(Payload)
        Owner = Selection is None
        if Owner:
            Selection = EpisodeSelection(MetaData)
            EpisodeSelections[Payload] = Selection
            EpisodeSelectionsByToken[Selection.Token] = Selection

    if not Owner:
        redirect_episode_selection(client, Selection)
        return

    Response = sendNotFound
    Reuse = False
    try:
        if not redirect_episode_selection(client, Selection):
            return

        client.close()
        utils.close_busyDialog()
        SelectionIndex = choose_media_source(MetaData)
        if utils.SystemShutdown or not Running:
            return

        if SelectionIndex == -1:
            versions.clear_choice()
            Response = cancel_episode_selection(Selection)
        else:
            player.PlaylistRemoveItem = -1
            MetaData['EpisodeSelection'] = True
            Response = play_selected_version(MetaData, None, SelectionIndex, VersionContext)

        Reuse = True
    finally:
        with EpisodeSelectionLock:
            Now = monotonic()
            Selection.Response = Response
            Selection.ReuseUntil = Now + (EpisodeRetryWindow if Reuse else 0)
            Selection.Expires = Now + EpisodeResponseLifetime
            Selection.Ready.set()

# Load external subtitles
def SubTitlesAdd(MetaData):
    if not MetaData['MediaSources'][MetaData['SelectionIndexMediaSource']][3]:
        return

    DefaultVideoSettings = xmls.load_defaultvideosettings()
    SubtitlesLanguageDefault = DefaultVideoSettings.get("SubtitlesLanguage", "").lower()
    SubtitlesLanguageCode = xbmc.convertLanguage(SubtitlesLanguageDefault, xbmc.ISO_639_2)
    SubtitlesLanguageName = xbmc.convertLanguage(SubtitlesLanguageDefault, xbmc.ENGLISH_NAME).lower() or SubtitlesLanguageDefault
    CounterSubTitle = 0
    SubtitleEnable = DefaultVideoSettings.get('ShowSubtitles', False)
    SubtitleIndexSelect = -1
    SubtitleIndexFallback = -1
    FileSettings = None
    KodiSubtitleState = None

    # Get Subtitle Settings
    if not MetaData['isDynamic']:
        videoDB = dbio.DBOpenRO("video", "SubTitlesAdd")
        FileSettings = videoDB.get_FileSettings(MetaData['KodiFileId'])
        dbio.DBCloseRO("video", "SubTitlesAdd")

        if FileSettings:
            SubtitleEnable = bool(FileSettings[9])
            SubtitleIndexSelect = FileSettings[7]

    for Subtitle in MetaData['MediaSources'][MetaData['SelectionIndexMediaSource']][3]:
        if Subtitle['external']:
            CounterSubTitle += 1

            if Subtitle['language']:
                SubtileLanguage = Subtitle['language']
            else:
                SubtileLanguage = "undefined"

            BinaryData = utils.EmbyServers[MetaData['ServerId']].API.get_Subtitle_Binary(MetaData['EmbyId'], MetaData['MediaSources'][MetaData['SelectionIndexMediaSource']][0]['Id'], Subtitle['Index'], Subtitle['Codec'])

            if (MetaData['EmbyId'] != EmbyIdCurrentlyPlaying or
                    (MetaData.get('PreselectedEpisode') and
                     player.PlayingItem['EmbySessionData'].get('PlaySessionId') != MetaData['PlaySessionId'])):
                del BinaryData
                return

            if BinaryData:
                SubtitleCodec = Subtitle['Codec']
                Path = f"{utils.FolderEmbyTemp}{utils.valid_Filename(f'{CounterSubTitle}.{SubtileLanguage}.{SubtitleCodec}')}"
                utils.writeFile(Path, BinaryData)
                del BinaryData

                if KodiSubtitleState is None:
                    if not playerops.wait_AVStarted():
                        return

                    # Adding an external subtitle changes Kodi's selection and visibility.
                    KodiSubtitleState = utils.SendJson("Player.GetProperties", '{"playerid":1,"properties":["currentsubtitle","subtitleenabled"]}', False).get("result")
                    if not KodiSubtitleState:
                        return

                SubtitleIndexAdded = playerops.AddSubtitle(Path)

                if SubtitleIndexSelect == -1:
                    SubtitleLanguageCode = xbmc.convertLanguage(SubtileLanguage, xbmc.ISO_639_2)

                    if SubtitlesLanguageDefault == "forced_only":
                        if Subtitle.get('Forced', False):
                            SubtitleIndexSelect = SubtitleIndexAdded
                    elif SubtitlesLanguageDefault != "none":
                        if ((SubtitlesLanguageCode and SubtitlesLanguageCode == SubtitleLanguageCode) or
                            (SubtitlesLanguageName and SubtitlesLanguageName in Subtitle['DisplayTitle'].lower())):
                            SubtitleIndexSelect = SubtitleIndexAdded
                        elif SubtitleLanguageCode in ("", "und") and SubtitleIndexFallback == -1:
                            # Keep unknown-language external subtitles as a fallback after language matches.
                            SubtitleIndexFallback = SubtitleIndexAdded

    if SubtitleIndexSelect == -1:
        SubtitleIndexSelect = SubtitleIndexFallback

    if SubtitleIndexSelect != -1:
        playerops.SelectSubtitle(SubtitleIndexSelect)
        playerops.EnableSubtitle(SubtitleEnable)
    elif KodiSubtitleState is not None:
        # No match: keep the state from before external subtitles were added.
        KodiSubtitleIndex = KodiSubtitleState["currentsubtitle"].get("index", -1)

        if KodiSubtitleIndex != -1:
            playerops.SelectSubtitle(KodiSubtitleIndex)

        playerops.EnableSubtitle(KodiSubtitleState["subtitleenabled"])

def LoadData(MetaData, client):
    set_QueuedPlayingItem(MetaData)
    Response = send_redirect(client, MetaData, f"{MetaData['EmbyStreamType']}/{MetaData['EmbyId']}/stream?static=true")
    AsyncCommandQueue.put((("SUBTITLE", MetaData),))
    return Response

def send_delayed_content(client, ETag):

    while not DelayedContentLock.acquire(timeout=0.1):
        pass

    if ETag in DelayedContent:
        DC = DelayedContent[ETag][0]
        DelayedContentLock.release()

        if DC:
            client.send(DC)

            with utils.SafeLock(DelayedContentLock):
                if ETag in DelayedContent:
                    DelayedContent[ETag][1] -= 1

                    if DelayedContent[ETag][1] < 0:
                        del DelayedContent[ETag]

            return True

        return False

    DelayedContentLock.release()
    xbmc.log(f"EMBY.hooks.webservice: Delayed content not found {ETag}", xbmc.LOGERROR)
    client.send(sendNotFound)
    return True

def set_QueuedPlayingItem(MetaData):
    player.PlayerBusyDelay = 5
    if MetaData['KodiType'] != 'episode':
        versions.clear_choice()

    player.QueuedPlayingItem = {
        "EmbySessionData": {
            "QueueableMediaTypes": ["Audio", "Video"],
            "CanSeek": True,
            "IsPaused": False,
            "ItemId": int(MetaData["EmbyId"]),
            "MediaSourceId": MetaData["MediaSources"][MetaData["SelectionIndexMediaSource"]][0]["Id"],
            "PositionTicks": 0,
            "RunTimeTicks": 0,
            "VolumeLevel": player.Volume,
            "PlaybackRate": playerops.PlaybackRate[MetaData["PlayerId"]],
            "Shuffle": playerops.Shuffled[MetaData["PlayerId"]],
            "RepeatMode": playerops.RepeatMode[MetaData["PlayerId"]],
            "IsMuted": player.Muted
        },
        "IntroStartPositionTicks": MetaData["MediaSources"][MetaData["SelectionIndexMediaSource"]][0]["IntroStartPositionTicks"],
        "IntroEndPositionTicks": MetaData["MediaSources"][MetaData["SelectionIndexMediaSource"]][0]["IntroEndPositionTicks"],
        "CreditsPositionTicks": MetaData["MediaSources"][MetaData["SelectionIndexMediaSource"]][0]["CreditsPositionTicks"],
        "EmbyServer": utils.EmbyServers[MetaData["ServerId"]],
        "KodiType": MetaData["KodiType"],
        "IndexMappingVideoEmby": MetaData["MediaSources"][MetaData["SelectionIndexMediaSource"]][0]["IndexMappingVideoEmby"],
        "IndexMappingVideoKodi": MetaData["MediaSources"][MetaData["SelectionIndexMediaSource"]][0]["IndexMappingVideoKodi"],
        "IndexMappingAudioEmby": MetaData["MediaSources"][MetaData["SelectionIndexMediaSource"]][0]["IndexMappingAudioEmby"],
        "IndexMappingAudioKodi": MetaData["MediaSources"][MetaData["SelectionIndexMediaSource"]][0]["IndexMappingAudioKodi"],
        "IndexMappingSubtitleEmby": MetaData["MediaSources"][MetaData["SelectionIndexMediaSource"]][0]["IndexMappingSubtitleEmby"],
        "IndexMappingSubtitleKodi": MetaData["MediaSources"][MetaData["SelectionIndexMediaSource"]][0]["IndexMappingSubtitleKodi"],
        "SubtitleEnabled": False,
        "SubtitleIndexKodi": 0
    }

    if MetaData.get('VersionSelectionDone'):
        player.QueuedPlayingItem['SelectedVersion'] = (str(MetaData['ServerId']), str(MetaData['EmbyId']), MetaData['MediaSources'][MetaData['SelectionIndexMediaSource']][0]['Id'])

    if not MetaData.get('PreselectedEpisode'):
        MetaData['PlaySessionId'] = uuid.uuid4().hex
    player.QueuedPlayingItem["EmbySessionData"]['PlaySessionId'] = MetaData['PlaySessionId']

def add_DelayedContent(MetaData, client):
    if not MetaData['DelayedContentSet']:
        MetaData['DelayedContentSet'] = True

        with utils.SafeLock(DelayedContentLock):
            if MetaData['ETag'] in DelayedContent:
                DelayedContent[MetaData['ETag']][1] += 1
                Added = True
            else:
                DelayedContent[MetaData['ETag']] = [None, 0]
                Added = False

        client.send(f"HTTP/1.1 307 Temporary Redirect\r\nServer: Emby-Next-Gen\r\nConnection: close\r\nLocation: http://127.0.0.1:57342/delayed_content/{MetaData['ETag']}\r\nContent-Length: 0\r\nAccept-Ranges: none\r\n\r\n".encode())
        client.close()
        utils.close_busyDialog()
        return Added

    return False

def set_DelayedContent(ETag, Data, Index, KodiId):
    with utils.SafeLock(DelayedContentLock):
        if Index:
            DelayedContent[ETag] = [Data, Index]
        else:
            DelayedContent[ETag][0] = Data

    if KodiId:
        player.ForceStopKodiId = int(KodiId)

    with utils.SafeLock(DelayedContentCondition):
        DelayedContentCondition.notify_all()

def wait_for_Embyserver(client, ServerId, MetaData):
    if ServerId in utils.EmbyServersBan:
        client.send(sendNotFound)
        return False

    with utils.SafeLock(utils.EmbyServerOnlineCondition):
        CounterRetry = 0

        while ServerId not in utils.EmbyServers or not utils.EmbyServers[ServerId].library.SettingsLoaded:
            if not CounterRetry:

                if not CounterRetry and MetaData:
                    add_DelayedContent(MetaData, client)

            CounterOnlineCondintion = 0

            while CounterOnlineCondintion < 40: # 4 Seconds timeout
                if utils.EmbyServerOnlineCondition.wait(timeout=0.1):
                    break

                CounterOnlineCondintion += 1

            CounterRetry += 1

            if utils.SystemShutdown:

                if CounterRetry > 0 and MetaData:
                    set_DelayedContent(MetaData['ETag'], sendNotFound, 0, 0)
                else:
                    client.send(sendNotFound)

                return False

            utils.sleep(1)

            if ServerId not in utils.EmbyServers:
                if CounterRetry >= 10: # 50 Seconds timeout when ServerId not found
                    utils.EmbyServersBan.add(ServerId)

                    if MetaData:
                        set_DelayedContent(MetaData['ETag'], sendNotFound, 0, 0)
                    else:
                        client.send(sendNotFound)

                    return False

        if CounterRetry:

            if MetaData:
                set_DelayedContent(MetaData['ETag'], f"HTTP/1.1 307 Temporary Redirect\r\nServer: Emby-Next-Gen\r\nLocation: http://127.0.0.1:57342{MetaData['Payload']}\r\nConnection: close\r\nContent-Length: 0\r\nAccept-Ranges: none\r\n\r\n".encode(), 0, 0)
                return False

            return True

        return True


def AsyncCommands():

    while True:
        IncomingCommand = AsyncCommandQueue.get()

        if IncomingCommand == "QUIT":
            return

        if IncomingCommand[0] == "SUBTITLE":
            SubTitlesAdd(IncomingCommand[1])
