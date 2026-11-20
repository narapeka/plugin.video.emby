import socket
import ssl
import threading
import xbmc

from helper import utils
from . import http, websocket


class HTTPCommon:
    def __init__(self, ServerData, HTTPThreadsRunningCondition, WebsocketRunning, WebsocketMessageQueue):
        self.ServerData = ServerData
        self.HTTPThreadsRunningCondition = HTTPThreadsRunningCondition
        self.WebsocketRunning = WebsocketRunning
        self.WebsocketMessageQueue = WebsocketMessageQueue
        self.PingRunning = False
        self.Connection = {}
        self.AddrInfo = {}
        self.AddrInfoLock = threading.Lock()
        self.SSLContext = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)

        if utils.sslverify:
            self.SSLContext.verify_mode = ssl.CERT_REQUIRED
        else:
            self.SSLContext.check_hostname = False
            self.SSLContext.verify_mode = ssl.CERT_NONE

        self.HTTP = http.HTTP(self)
        self.WebSocket = websocket.WebSocket(self)
        self.Queues = self.HTTP.Queues
        self.RequestBusy = self.HTTP.RequestBusy
        self.Response = self.HTTP.Response
        self.ResponseLock = self.HTTP.ResponseLock
        self.ResponseCanceled = self.HTTP.ResponseCanceled
        self.HttpIdleEvent = self.HTTP.HttpIdleEvent
        self.ThreadsRunning = self.HTTP.ThreadsRunning

    def start(self):
        if utils.SystemShutdown:
            return

        with utils.SafeLock(self.HTTP.Connecting):
            if not self.HTTP.Running and not utils.SystemShutdown:
                self.HTTP.Running = True

                self.HTTP.start_http()

                if utils.websocketenabled:
                    self.WebSocket.start()

                if not self.PingRunning:
                    self.PingRunning = True
                    utils.start_thread(self.Ping, ())

                with utils.SafeLock(self.HTTPThreadsRunningCondition):
                    self.HTTPThreadsRunningCondition.notify_all()

    def stop(self):

        with utils.SafeLock(self.HTTP.Connecting):
            if self.HTTP.Running:
                self.HTTP.Running = False

                self.HTTP.stop_http()
                self.WebSocket.stop()

                for ConnectionId in list(self.Connection.keys()):
                    if ConnectionId != "ASYNC": # Skip ASYNC as it might include termination info for server (e.g. remote playback disconnects)
                        self.socket_close(ConnectionId, False)

        with utils.SafeLock(self.HTTPThreadsRunningCondition):
            while self.HTTP.ThreadsRunning["ASYNC"] or self.HTTP.ThreadsRunning["QUEUEDREQUESTMAIN"] or self.HTTP.ThreadsRunning["QUEUEDREQUESTMAINFALLBACK"] or self.PingRunning or self.WebSocket.ThreadRunning or self.WebsocketRunning[0]:
                self.HTTPThreadsRunningCondition.wait(timeout=0.1)

        for ConnectionId in list(self.Connection.keys()):
            if ConnectionId != "ASYNC":
                self.socket_del(ConnectionId)

    def request(self, Method, Handler, Params, RequestHeader, Binary, ConnectionString, BusyFunction, ConnectionId):
        return self.HTTP.request(Method, Handler, Params, RequestHeader, Binary, ConnectionString, BusyFunction, ConnectionId)

    def Ping(self):

        while True:
            for Counter in range(4): # ping every 3 seconds
                if not self.HTTP.Running or utils.sleep(1):
                    self.PingRunning = False
                    with utils.SafeLock(self.HTTPThreadsRunningCondition):
                        self.HTTPThreadsRunningCondition.notify_all()
                    return

                if Counter == 1 and not self.HTTP.RequestBusy["MAIN"].locked():
                    self.HTTP.request("POST", "System/Ping", {}, {}, True, "", None, "MAIN")

                if Counter == 2 and not self.HTTP.RequestBusy["MAINFALLBACK"].locked():
                    self.HTTP.request("POST", "System/Ping", {}, {}, True, "", None, "MAINFALLBACK")

                if Counter == 3 and not self.HTTP.RequestBusy["ASYNC"].locked():
                    self.HTTP.Queues["ASYNC"].put((("POST", "System/Ping", {}, False),))

    def socket_addrinfo(self, ConnectionId, Hostname, Force):
        AddrInfoKey = (Hostname, self.Connection[ConnectionId]["Port"])

        with utils.SafeLock(self.AddrInfoLock):
            if AddrInfoKey in self.AddrInfo and not Force:
                return 0

        try:
            AddrInfo = socket.getaddrinfo(Hostname, self.Connection[ConnectionId]["Port"], socket.AF_UNSPEC, socket.SOCK_STREAM, socket.IPPROTO_TCP)

            AddrInfoList = []

            for AddrInfoData in AddrInfo:
                AddrInfoList.append((AddrInfoData[0], AddrInfoData[4]))

            with utils.SafeLock(self.AddrInfoLock):
                self.AddrInfo[AddrInfoKey] = AddrInfoList
        except Exception as error:
            xbmc.log(f"EMBY.emby.http: DNS resolution failed on {ConnectionId}: {type(error).__name__}", xbmc.LOGDEBUG)

            if ConnectionId == "MAIN":
                utils.Dialog.notification(heading=utils.addon_name, icon="DefaultIconError.png", message=utils.Translate(33678), time=utils.displayMessage, sound=False)

            if ConnectionId in self.Connection:
                del self.Connection[ConnectionId]

            return 609

        return 0

    def socket_del(self, ConnectionId):
        if ConnectionId in self.Connection:
            del self.Connection[ConnectionId]

    def socket_open(self, ConnectionString, ConnectionId, CloseConnection, Abort=None):
        while True:
            NewHeader = False

            if ConnectionId not in self.Connection:
                self.Connection[ConnectionId] = {}

            if Abort:
                self.Connection[ConnectionId]["Abort"] = Abort

            if "ConnectionString" not in self.Connection[ConnectionId]:
                self.Connection[ConnectionId]["ConnectionString"] = ConnectionString
                NewHeader = True
            else:
                if self.Connection[ConnectionId]["ConnectionString"] != ConnectionString:
                    self.Connection[ConnectionId]["ConnectionString"] = ConnectionString
                    NewHeader = True

            if NewHeader:
                try:
                    Scheme, self.Connection[ConnectionId]["Hostname"], self.Connection[ConnectionId]["Port"], self.Connection[ConnectionId]["SubUrl"] = utils.get_url_info(ConnectionString)
                except Exception as error:
                    xbmc.log(f"EMBY.emby.http: Invalid connection address on {ConnectionId}: {type(error).__name__}", xbmc.LOGDEBUG)

                    if ConnectionId == "MAIN":
                        utils.Dialog.notification(heading=utils.addon_name, icon="DefaultIconError.png", message=utils.Translate(33678), time=utils.displayMessage, sound=False)

                    self.socket_del(ConnectionId)
                    return 611

                self.Connection[ConnectionId]["SSL"] = bool(Scheme == "https")

                if CloseConnection:
                    ConnectionMode = 'close'
                else:
                    ConnectionMode = 'keep-alive'

                if ":" in self.Connection[ConnectionId]["Hostname"]:
                    HostHeader = f'[{self.Connection[ConnectionId]["Hostname"]}]:{self.Connection[ConnectionId]["Port"]}'
                else:
                    HostHeader = f'{self.Connection[ConnectionId]["Hostname"]}:{self.Connection[ConnectionId]["Port"]}'

                self.Connection[ConnectionId]["RequestHeader"] = {"Host": HostHeader, 'Content-Type': 'application/json; charset=utf-8', 'Accept-Charset': 'utf-8', 'Accept-Encoding': 'gzip,deflate', 'User-Agent': f"{utils.addon_name}/{utils.addon_version}", 'Connection': ConnectionMode, 'Authorization': f'Emby Client="{utils.addon_name}", Device="{utils.device_name}", DeviceId="{self.ServerData["DeviceId"]}", Version="{utils.addon_version}"'}


                StatusCodeSocket = self.socket_addrinfo(ConnectionId, self.Connection[ConnectionId]["Hostname"], False)

                if StatusCodeSocket:
                    self.socket_del(ConnectionId)
                    return StatusCodeSocket

            RetryCounter = 0
            AddrInfoIndex = 0

            while True:
                if Abort and Abort():
                    self.socket_close(ConnectionId)
                    return 601

                try:
                    AddressFamily, Address = self.AddrInfo[(self.Connection[ConnectionId]["Hostname"], self.Connection[ConnectionId]["Port"])][AddrInfoIndex]
                    self.Connection[ConnectionId]["Socket"] = socket.socket(AddressFamily, socket.SOCK_STREAM)
                    self.Connection[ConnectionId]["Socket"].setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

                    self.Connection[ConnectionId]["Socket"].settimeout(3) # set timeout

                    if not self.Connection[ConnectionId]["SSL"]:
                        self.Connection[ConnectionId]["Socket"].connect(Address)
                except TimeoutError:
                    if ConnectionId not in self.Connection:
                        return 699

                    self.Connection[ConnectionId]["Socket"].close()
                    AddrInfoIndex += 1

                    if AddrInfoIndex < len(self.AddrInfo[(self.Connection[ConnectionId]["Hostname"], self.Connection[ConnectionId]["Port"])]):
                        continue

                    AddrInfoIndex = 0
                    RetryCounter += 1

                    if RetryCounter == 1:
                        StatusCodeSocket = self.socket_addrinfo(ConnectionId, self.Connection[ConnectionId]["Hostname"], True)

                        if StatusCodeSocket:
                            self.socket_del(ConnectionId)
                            return StatusCodeSocket

                    if RetryCounter <= 10:
                        continue

                    self.socket_del(ConnectionId)
                    return 606
                except ConnectionRefusedError:
                    if ConnectionId not in self.Connection:
                        return 699

                    self.Connection[ConnectionId]["Socket"].close()
                    AddrInfoIndex += 1

                    if AddrInfoIndex < len(self.AddrInfo[(self.Connection[ConnectionId]["Hostname"], self.Connection[ConnectionId]["Port"])]):
                        continue

                    AddrInfoIndex = 0
                    RetryCounter += 1

                    if RetryCounter == 1:
                        StatusCodeSocket = self.socket_addrinfo(ConnectionId, self.Connection[ConnectionId]["Hostname"], True)

                        if StatusCodeSocket:
                            self.socket_del(ConnectionId)
                            return StatusCodeSocket

                        continue

                    self.socket_del(ConnectionId)
                    return 607
                except Exception as error:
                    if ConnectionId not in self.Connection:
                        return 699

                    self.Connection[ConnectionId]["Socket"].close()
                    AddrInfoIndex += 1

                    if AddrInfoIndex < len(self.AddrInfo[(self.Connection[ConnectionId]["Hostname"], self.Connection[ConnectionId]["Port"])]):
                        continue

                    AddrInfoIndex = 0
                    RetryCounter += 1

                    if RetryCounter == 1:
                        StatusCodeSocket = self.socket_addrinfo(ConnectionId, self.Connection[ConnectionId]["Hostname"], True)

                        if StatusCodeSocket:
                            self.socket_del(ConnectionId)
                            return StatusCodeSocket

                    if str(error).find("timed out") != -1 or str(error).find("timeout") != -1: # workaround when TimeoutError not raised
                        if RetryCounter <= 10:
                            continue

                        self.socket_del(ConnectionId)
                        return 606

                    if RetryCounter == 1:
                        continue

                    if str(error).lower().find("errno 22") != -1 or str(error).lower().find("invalid argument") != -1: # [Errno 22] Invalid argument
                        self.socket_del(ConnectionId)
                        xbmc.log(f"EMBY.emby.http: Socket open {ConnectionId}: Invalid argument", xbmc.LOGWARNING)

                        if ConnectionId == "MAIN":
                            utils.Dialog.notification(heading=utils.addon_name, icon="DefaultIconError.png", message=utils.Translate(33679), time=utils.displayMessage, sound=False)

                        return 610

                    xbmc.log(f"EMBY.emby.http: Socket open failed on {ConnectionId}: {type(error).__name__}", xbmc.LOGWARNING)
                    self.socket_del(ConnectionId)
                    return 699

                if ConnectionId in self.Connection:
                    if self.Connection[ConnectionId]["SSL"]:
                        try:
                            self.Connection[ConnectionId]["Socket"] = self.SSLContext.wrap_socket(self.Connection[ConnectionId]["Socket"], server_hostname=self.Connection[ConnectionId]["Hostname"])
                            self.Connection[ConnectionId]["Socket"].connect(Address)
                            self.Connection[ConnectionId]["Socket"].settimeout(3) # set timeout
                            break
                        except ssl.CertificateError:
                            self.socket_del(ConnectionId)
                            xbmc.log("EMBY.emby.http: socket_open ssl certificate error", xbmc.LOGERROR)

                            if ConnectionId == "MAIN":
                                utils.Dialog.notification(heading=utils.addon_name, message=utils.Translate(33428), time=utils.displayMessage)

                            return 608
                        except TimeoutError:
                            self.Connection[ConnectionId]["Socket"].close()
                            AddrInfoIndex += 1

                            if AddrInfoIndex < len(self.AddrInfo[(self.Connection[ConnectionId]["Hostname"], self.Connection[ConnectionId]["Port"])]):
                                continue

                            AddrInfoIndex = 0
                            RetryCounter += 1

                            if RetryCounter <= 10:
                                if utils.sleep(0.1):
                                    return 699

                                continue

                            self.socket_del(ConnectionId)
                            return 606
                        except Exception as error:
                            self.Connection[ConnectionId]["Socket"].close()
                            AddrInfoIndex += 1

                            if AddrInfoIndex < len(self.AddrInfo[(self.Connection[ConnectionId]["Hostname"], self.Connection[ConnectionId]["Port"])]):
                                continue

                            AddrInfoIndex = 0
                            RetryCounter += 1

                            if RetryCounter <= 10:
                                if utils.sleep(0.1):
                                    return 699

                                continue

                            if str(error).find("timed out") != -1 or str(error).find("timeout") != -1: # workaround when TimeoutError not raised
                                self.socket_del(ConnectionId)
                                return 606

                            self.socket_del(ConnectionId)
                            return 699
                    else:
                        break
                else:
                    self.socket_del(ConnectionId)
                    return 699

            return 0

    def socket_close(self, ConnectionId, DeleteConnection=True):
        if ConnectionId in self.Connection:
            try:
                self.Connection[ConnectionId]["Socket"].close()
            except Exception:
                pass

            try:
                if DeleteConnection:
                    del self.Connection[ConnectionId]
            except Exception:
                pass
        else:
            return

    def socket_io(self, Request, ConnectionId, Timeout):
        IncomingData = b""
        StatusCode = 0
        TimeoutCounter = 0
        BytesSend = 0
        BytesSendTotal = len(Request)
        TimeoutSocket = 0.1
        TimeoutLoops = Timeout * 10
        Abort = self.Connection.get(ConnectionId, {}).get("Abort")

        while True:
            if Abort and Abort():
                return 601, b""

            try:
                self.Connection[ConnectionId]["Socket"].settimeout(TimeoutSocket)

                if Request:
                    while BytesSend < BytesSendTotal:
                        BytesSend += self.Connection[ConnectionId]["Socket"].send(Request[BytesSend:])
                else:
                    IncomingData = self.Connection[ConnectionId]["Socket"].recv(1048576)

                    if not IncomingData or (utils.SystemShutdown and Timeout > 4):
                        StatusCode = 600

                    break

                if BytesSend >= BytesSendTotal:
                    break
            except TimeoutError:
                if not TimeoutLoops:
                    continue

                TimeoutCounter += 1

                if TimeoutCounter < TimeoutLoops:
                    continue

                StatusCode = 603
                break
            except BrokenPipeError:
                StatusCode = 605
                break
            except Exception as error:
                if str(error).find("timed out") != -1 or str(error).find("timeout") != -1: # workaround when TimeoutError not raised
                    if not TimeoutLoops:
                        continue

                    TimeoutCounter += 1

                    if TimeoutCounter <= TimeoutLoops:
                        continue

                    StatusCode = 603
                    break

                xbmc.log(f"EMBY.emby.http: Socket I/O failed on {ConnectionId}: {type(error).__name__}", xbmc.LOGERROR)
                StatusCode = 698
                break

        return StatusCode, IncomingData
