import threading
import uuid
import json
import socket
import sqlite3
from time import monotonic
from urllib.parse import urlsplit
import xbmcvfs
import xbmc
from dialogs import serverconnect, usersconnect, loginconnect, loginmanual, servermanual
from helper import utils, pluginmenu, queue
from database import library
from hooks import websocket
from . import views, api, http_common

Disconnect = threading.Lock()


class EmbyServer:
    def __init__(self, ServerSettings):
        self.ShutdownInProgress = False
        self.EmbySession = []
        self.Found_Servers = []
        self.ServerSettings = ServerSettings
        self.Firstrun = not bool(self.ServerSettings)
        self.ServerData = {'AccessToken': "", 'UserId': "", 'UserName': "", 'UserImageUrl': "", 'ServerName': "", 'ServerId': "", 'ServerUrl': "", 'EmbyConnectExchangeToken': "", 'EmbyConnectUserId': "", 'EmbyConnectUserName': "", 'EmbyConnectAccessToken': "", 'ManualAddress': "", 'RemoteAddress': "", 'LocalAddress': "" ,'AdditionalUsers': {}, "DeviceId": "", "ServerVersion": "", "ServerRemoved": False}
        self.ServerReconnectLock = threading.Lock()
        self.LibrarySynced = []
        self.LibrarySyncedKodiDBs = {}
        self.LibrarySyncedNames = {}
        self.LibrarySyncedContent = {}
        self.ViewItems = {}
        self.WebsocketRunning = [False]
        self.WebsocketMessageQueue = queue.Queue()
        self.HTTPThreadsRunningCondition = threading.Condition(threading.Lock())
        self.http = http_common.HTTPCommon(self.ServerData, self.HTTPThreadsRunningCondition, self.WebsocketRunning, self.WebsocketMessageQueue)
        self.API = api.API(self.ServerData, self.ViewItems, self.LibrarySyncedNames, self.LibrarySyncedContent, self.LibrarySyncedKodiDBs, self.EmbySession, self.http)
        self.Views = views.Views(self.ServerData, self.ViewItems, self.LibrarySynced, self.API)
        self.library = library.Library(self.ServerData, self.API, self.Views, self.LibrarySynced, self.LibrarySyncedNames, self.LibrarySyncedContent, self.LibrarySyncedKodiDBs)
        self.http.HTTP.OnPlaybackReport = self.library.on_playback_report
        self.Websocket = websocket.WebSocket(self.ServerData, self.HTTPThreadsRunningCondition, self.EmbySession, self.API, self.library, self.WebsocketRunning, self.WebsocketMessageQueue)
        self.Online = False

    def ServerReconnect(self, ShowMsg=False):
        if not self.Firstrun and not self.ServerReconnectLock.locked():
            utils.start_thread(self.worker_ServerReconnect, (ShowMsg,))

    def worker_ServerReconnect(self, ShowMsg):
        if not self.ServerReconnectLock.acquire(blocking=False):
            return

        ReconnectingId = f"{self.ServerData['ServerId']}_server_reconnecting"
        try:
            NotifyAfter = monotonic() + 5
            OfflineNotified = False
            utils.update_SyncPause(ReconnectingId, True)
            utils.update_SyncPause(f"{self.ServerData['ServerId']}_server_busy", False)

            while True:
                self.stop()

                if utils.sleep(1) or not self.ServerData['ServerUrl']:
                    break

                Connected = self.ServerHandshake()
                if utils.SystemShutdown:
                    break

                if Connected:
                    if self.start() is False:
                        return
                    if OfflineNotified and utils.offlineMsg and not utils.SystemShutdown:
                        utils.Dialog.notification(heading=utils.addon_name, icon=utils.icon, message=f"{self.ServerData['ServerName']}: {utils.Translate(33915)}", time=utils.displayMessage, sound=False)

                    break

                if ShowMsg and utils.offlineMsg and not OfflineNotified and monotonic() >= NotifyAfter:
                    utils.Dialog.notification(heading=utils.addon_name, icon="DefaultIconError.png", message=f"{self.ServerData['ServerName']}: {utils.Translate(33914)}", time=utils.displayMessage, sound=False)
                    OfflineNotified = True
        finally:
            utils.update_SyncPause(ReconnectingId, False)
            self.ServerReconnectLock.release()

    def start(self):
        # Library was constructed before credentials supplied the server ID.
        StartingId = f"{self.ServerData['ServerId']}_server_starting"
        utils.update_SyncPause(StartingId, True)
        self.Online = False
        try:
            # A bounded DB open attempt may expire while Kodi is still writing.
            # Retry initialization here so first login, startup and reconnect agree.
            while not utils.SystemShutdown and not self.ServerData.get('ServerRemoved', False):
                try:
                    if self.library.load_settings() is False:
                        return False
                    break
                except sqlite3.OperationalError as Error:
                    Code = getattr(Error, "sqlite_errorcode", 0) & 255
                    if Code not in (5, 6) and str(Error).lower() not in ("database is locked", "database table is locked"):
                        raise
                    xbmc.log("EMBY.emby.emby: Database busy; retrying server initialization", xbmc.LOGWARNING)
                    if utils.sleep(1):
                        return False
                except InterruptedError:
                    if not utils.SystemShutdown:
                        raise
                    return False
            else:
                return False

            if utils.SystemShutdown or self.ServerData.get('ServerRemoved', False):
                return False
            self.Online = True
            with utils.SafeLock(utils.EmbyServerOnlineCondition):
                utils.EmbyServerOnlineCondition.notify_all()

            self.Views.update_views()
            self.Views.update_nodes()

            if utils.websocketenabled and not self.WebsocketRunning[0]:
                self.WebsocketMessageQueue.clear()
                utils.start_thread(self.Websocket.Message, ())

            self.http.start()
            utils.start_thread(self.library.KodiStartSync, (self.Firstrun,))
            self.Firstrun = False
            xbmc.log(f"EMBY.emby.emby: Connected to {self.ServerData['ServerName']}", xbmc.LOGINFO)
            return True
        finally:
            utils.update_SyncPause(StartingId, False)

    def stop(self):

        if self.EmbySession and not self.ShutdownInProgress:
            self.ShutdownInProgress = True
            utils.update_SyncPause(f"{self.ServerData['ServerId']}_server_starting", True)
            utils.update_SyncPause(f"{self.ServerData['ServerId']}_server_busy", False)
            self.EmbySession.clear()
            self.Online = False

            with utils.SafeLock(utils.EmbyServerOnlineCondition):
                utils.EmbyServerOnlineCondition.notify_all()

            self.ShutdownInProgress = False

        if utils.websocketenabled:
            self.WebsocketMessageQueue.put("QUIT")

        self.http.stop()

    def add_AdditionalUser(self, UserId, UserName):
        self.ServerData['AdditionalUsers'][UserId] = UserName
        self.save_credentials()
        self.API.session_add_user(self.EmbySession[0]['Id'], UserId, True)

    def remove_AdditionalUser(self, UserId):
        if UserId in self.ServerData['AdditionalUsers']:
            del self.ServerData['AdditionalUsers'][UserId]

        self.save_credentials()
        self.API.session_add_user(self.EmbySession[0]['Id'], UserId, False)

    # Login into server. If server is None, then it will show the proper prompts to login, etc.
    # If a server id is specified then only a login dialog will be shown for that server.
    def ServerInitConnection(self):

        # load credentials from file
        if self.ServerSettings:
            FileData = utils.readFileString(self.ServerSettings)

            if FileData:
                LoadedServerSettings = json.loads(FileData)

                if 'ServerId' in LoadedServerSettings and LoadedServerSettings['ServerId']: # file content is valid
                    self.ServerData.update(LoadedServerSettings)

            utils.DatabaseFiles[self.ServerData['ServerId']] = xbmcvfs.translatePath(f"special://profile/Database/emby_{self.ServerData['ServerId']}.db")
        else:
            self.ServerData["DeviceId"] = str(uuid.uuid4())

        # Refresh EmbyConnect Emby server addresses (dynamic IP)
        if self.ServerData["EmbyConnectAccessToken"]:
            EmbyConnectServers = self.API.get_embyconnect_servers()

            if EmbyConnectServers:
                if not isinstance(EmbyConnectServers, dict):
                    EmbyConnectServers = json.loads(EmbyConnectServers)

                for EmbyConnectServer in EmbyConnectServers:
                    if EmbyConnectServer['SystemId'] == self.ServerData['ServerId']:
                        if self.ServerData['RemoteAddress'] != EmbyConnectServer['Url'] or self.ServerData['LocalAddress'] != EmbyConnectServer['LocalAddress']: # update server settings
                            self.ServerData.update({'RemoteAddress': EmbyConnectServer['Url'], 'LocalAddress': EmbyConnectServer['LocalAddress']})
                            self.save_credentials()

                        break

        if self.Firstrun:
            SignedIn = True
            self.ServerDetect()

            # Menu dialogs
            while True:
                if utils.SystemShutdown:
                    SignedIn = False
                    break

                Dialog = serverconnect.ServerConnect("script-emby-connect-server.xml", *utils.CustomDialogParameters)
                Dialog.Servers = self.Found_Servers
                Dialog.UserImageUrl = self.ServerData['UserImageUrl']
                Dialog.emby_connect = not self.ServerData['UserId']
                Dialog.doModal()
                ConnectionMode = Dialog.ConnectionMode
                self.ServerData.update(Dialog.ServerSelected)
                del Dialog

                if ConnectionMode == "ListSelection":
                    isValid, _, _ = self.TestConnections()

                    if isValid:
                        Password = self.UserSelection()

                        if self.ServerLogin(Password):
                            if self.ServerHandshake():
                                break
                elif ConnectionMode == "ManualAddress":
                    Dialog = servermanual.ServerManual("script-emby-connect-server-manual.xml", *utils.CustomDialogParameters)
                    Dialog.doModal()
                    self.ServerData['ManualAddress'] = Dialog.ManualAddress
                    del Dialog

                    if self.ServerData['ManualAddress']:
                        isValid, _, _ = self.TestConnections()

                        if isValid:
                            Password = self.UserSelection()

                            if self.ServerLogin(Password):
                                if self.ServerHandshake():
                                    break
                elif ConnectionMode == "EmbyConnect":
                    Dialog = loginconnect.LoginConnect("script-emby-connect-login.xml", *utils.CustomDialogParameters)
                    Dialog.doModal()
                    Username, Password = Dialog.Login
                    del Dialog

                    if Username and Password:
                        self.EmbyConnectServers(Username, Password)
                        continue
                else: # cancel
                    SignedIn = False
                    break

            if SignedIn:
                self.save_credentials()
                utils.EmbyServers[self.ServerData['ServerId']] = self
                utils.EmbyServersBan.discard(self.ServerData['ServerId'])

                if self.ServerData['ServerId'] not in utils.EmbyServerIds:
                    utils.EmbyServerIds.append(self.ServerData['ServerId'])

                self.start()

            return

        # re-establish connection
        utils.EmbyServers[self.ServerData['ServerId']] = self
        utils.EmbyServersBan.discard(self.ServerData['ServerId'])

        if self.ServerData['ServerId'] not in utils.EmbyServerIds:
            utils.EmbyServerIds.append(self.ServerData['ServerId'])

        utils.start_thread(self.EstablishExistingConnection, ())

    def EstablishExistingConnection(self):

        while True:
            isValid, Resync, SaveConfig = self.TestConnections()

            if isValid:
                if Resync:
                    pluginmenu.factoryreset(utils.Translate(33905))
                    return

                if self.ServerHandshake():
                    if self.start() is False:
                        return

                    if SaveConfig:
                        self.save_credentials()

                break

            if self.ServerData.get('ServerRemoved', False):
                return

            if utils.sleep(1):
                return

        UserImageUrl = self.ServerData.get('UserImageUrl', "")

        if not xbmcvfs.exists(UserImageUrl):
            UserData = {'Id': self.ServerData['UserId'], 'Name': self.ServerData['UserName'], 'UserImageUrl': UserImageUrl}
            self.get_UserImage(UserData)
            self.ServerData['UserImageUrl'] = UserData['UserImageUrl']

    def save_credentials(self):
        if not self.ServerSettings:
            self.ServerSettings = f"{utils.FolderAddonUserdata}servers_{self.ServerData['ServerId']}.json"

        utils.writeFile(self.ServerSettings, json.dumps(self.ServerData, sort_keys=True, indent=4, ensure_ascii=False))

    def ServerDisconnect(self, AccessRestricted=False):

        with utils.SafeLock(Disconnect):
            if self.ServerData['ServerId'] in utils.EmbyServers:
                if not AccessRestricted:
                    utils.EmbyServers[self.ServerData['ServerId']].API.session_logout()

                utils.EmbyServers[self.ServerData['ServerId']].stop()
                utils.EmbyServersBan.add(self.ServerData['ServerId'])
                del utils.EmbyServers[self.ServerData['ServerId']]

            utils.delFile(f"{utils.FolderAddonUserdata}servers_{self.ServerData['ServerId']}.json")
            self.EmbySession.clear()
            self.Online = False

            with utils.SafeLock(utils.EmbyServerOnlineCondition):
                utils.EmbyServerOnlineCondition.notify_all()

    def ServerHandshake(self):
        self.EmbySession.clear()
        self.EmbySession.extend(self.API.get_device())

        if not self.EmbySession:
            xbmc.log(f"EMBY.emby.emby: No authenticated Emby session for {self.ServerData['ServerId']}", xbmc.LOGERROR)

            if utils.websocketenabled:
                self.WebsocketMessageQueue.put("QUIT")

            self.http.stop()
            return False

        if not self.ServerData['UserName']:
            self.ServerData['UserName'] = self.EmbySession[0]['UserName']

        self.API.post_capabilities()

        for AdditionalUserId in self.ServerData['AdditionalUsers']:
            AddUser = True

            for SessionAdditionalUser in self.EmbySession[0]['AdditionalUsers']:
                if SessionAdditionalUser['UserId'] == AdditionalUserId:
                    AddUser = False
                    break

            if AddUser:
                self.API.session_add_user(self.EmbySession[0]['Id'], AdditionalUserId, True)

        return True

    def UserSelection(self):
        Username = ""
        Users = self.API.get_public_users()

        if Users:
            UsersInfo = []

            for User in Users:
                UserData = User.copy()
                self.get_UserImage(UserData)
                UsersInfo.append(UserData)

            Dialog = usersconnect.UsersConnect("script-emby-connect-users.xml", *utils.CustomDialogParameters)
            Dialog.users = UsersInfo
            Dialog.doModal()
            SelectedUser = Dialog.SelectedUser
            del Dialog

            if SelectedUser and SelectedUser != "MANUAL":
                self.ServerData.update({'UserImageUrl': SelectedUser['UserImageUrl'], 'UserName': SelectedUser['Name']})

                if SelectedUser['HasPassword']:
                    Username = SelectedUser['Name']
                else:
                    self.ServerData["UserName"] = SelectedUser['Name']
                    return ""

        Dialog = loginmanual.LoginManual("script-emby-connect-login-manual.xml", *utils.CustomDialogParameters)
        Dialog.username = Username
        Dialog.doModal()
        SelectedUser = Dialog.SelectedUser
        del Dialog
        self.ServerData["UserName"], Password = SelectedUser
        return Password

    def EmbyConnectServers(self, Username, Password):
        Data = self.API.get_embyconnect_authenticate(Username, Password)

        if not Data:  # Failed to login
            return

        if not isinstance(Data, dict):
            Data = json.loads(Data)

        self.ServerData.update({'EmbyConnectUserId': Data['User']['Id'], 'EmbyConnectUserName': Data['User']['Name'], 'EmbyConnectAccessToken': Data['AccessToken']})
        EmbyConnectServers = self.API.get_embyconnect_servers()

        if not isinstance(EmbyConnectServers, dict):
            EmbyConnectServers = json.loads(EmbyConnectServers)

        if EmbyConnectServers:
            for EmbyConnectServer in EmbyConnectServers:
                self.Found_Servers.append({'ExchangeToken': EmbyConnectServer['AccessKey'], 'ConnectServerId': EmbyConnectServer['Id'], 'Id': EmbyConnectServer['SystemId'], 'Name': f"Emby Connect: {EmbyConnectServer['Name']}", 'RemoteAddress': EmbyConnectServer['Url'], 'LocalAddress': EmbyConnectServer['LocalAddress'], 'UserLinkType': "Guest" if EmbyConnectServer['UserType'].lower() == "guest" else "LinkedUser"})

    def ServerLogin(self, password):

        if not self.ServerData["UserName"]:
            xbmc.log("EMBY.emby.emby: Username cannot be empty", xbmc.LOGERROR)
            return False

        # remove old access token and credential data file
        if self.ServerData['ServerId'] in utils.EmbyServers:
            self.ServerDisconnect()

        Data = self.API.get_authbyname(self.ServerData["UserName"], password)

        if not Data:
            return False

        self.ServerData.update({'UserId': Data['User']['Id'], 'AccessToken': Data['AccessToken']})
        return True

    def ServerDetect(self):
        MULTI_GROUP = ("<broadcast>", 7359)
        MESSAGE = b"who is EmbyServer?"
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1.0)  # This controls the socket.timeout exception
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        found_servers = []

        # get severs via broadcast
        try:
            sock.sendto(MESSAGE, MULTI_GROUP)

            while True:
                try:
                    data, _ = sock.recvfrom(1024)  # buffer size
                    IncomingData = json.loads(data)

                    if IncomingData not in found_servers:
                        found_servers.append(IncomingData)
                except socket.timeout:
                    break
                except Exception as Error:
                    xbmc.log(f"EMBY.emby.emby: Error trying to find servers: {Error}", xbmc.LOGERROR)
                    break
        except Exception as error:
            xbmc.log(f"EMBY.emby.emby: ERROR: {error}", xbmc.LOGERROR)

        self.Found_Servers = []

        for found_server in found_servers:
            server = ""

            if found_server.get('Address') and found_server.get('EndpointAddress'):
                EndpointAddress = found_server['EndpointAddress']
                Address = found_server['Address']
                Endpoint = urlsplit(EndpointAddress if "://" in EndpointAddress else f"//{EndpointAddress}")
                Published = urlsplit(Address if "://" in Address else f"//{Address}")
                if Endpoint.hostname:
                    Scheme = Published.scheme or Endpoint.scheme or "http"
                    Host = f"[{Endpoint.hostname}]" if ":" in Endpoint.hostname else Endpoint.hostname
                    Port = Published.port or (443 if Scheme == "https" else 80)
                    server = f"{Scheme}://{Host}:{Port}{Published.path.rstrip('/')}"

            if not server and not found_server.get('Address'):
                xbmc.log("EMBY.emby.emby: Discovered an Emby server with no address", xbmc.LOGWARNING)
                continue

            self.Found_Servers.append({'Id': found_server['Id'], 'LocalAddress': server or found_server['Address'], 'Name': found_server['Name']})

    def TestConnections(self):
        Resync = ""
        SaveConfig = False

        for Connection in ("ManualAddress", "LocalAddress", "RemoteAddress"):
            if utils.SystemShutdown or self.ServerData.get('ServerRemoved', False):
                return False, Resync, SaveConfig

            if not self.ServerData[Connection]:
                continue

            self.ServerData['ServerUrl'] = self.ServerData[Connection].rstrip('/')
            PublicInfo = self.API.get_publicinfo()

            if PublicInfo:
                if not isinstance(PublicInfo, dict): # Server offline
                    self.Views.update_nodes()
                    self.ServerData['ServerUrl'] = ""
                    continue

                ServerVersion = PublicInfo.get('Version', "")
                ServerVersionPrevious = self.ServerData.get('ServerVersion', "")

                if ServerVersion:
                    if ServerVersionPrevious:
                        if ServerVersionPrevious != ServerVersion:
                            ServerVersionCompare = get_CompareVersion(ServerVersion)
                            EmbyServerVersionPreviousCompare = get_CompareVersion(ServerVersionPrevious)
                            EmbyServerVersionResyncCompare = get_CompareVersion(utils.EmbyServerVersionResync)

                            if (EmbyServerVersionPreviousCompare < EmbyServerVersionResyncCompare <= ServerVersionCompare) or (ServerVersionCompare < EmbyServerVersionResyncCompare <= EmbyServerVersionPreviousCompare):
                                Resync = ServerVersion

                            self.ServerData["ServerVersion"] = ServerVersion
                            SaveConfig = True
                    else:
                        self.ServerData["ServerVersion"] = ServerVersion
                        SaveConfig = True

                xbmc.log(f"EMBY.emby.emby: Server version: {ServerVersion}", xbmc.LOGDEBUG)
                self.ServerData.update({'RemoteAddress': PublicInfo.get('WanAddress', self.ServerData['RemoteAddress']), 'LocalAddress': PublicInfo.get('LocalAddress', self.ServerData['LocalAddress']), 'ServerName': PublicInfo.get('ServerName'), 'ServerId': PublicInfo.get('Id')})
                utils.DatabaseFiles[self.ServerData['ServerId']] = xbmcvfs.translatePath(f"special://profile/Database/emby_{self.ServerData['ServerId']}.db")
                return True, Resync, SaveConfig

            self.Views.update_nodes()
            self.ServerData['ServerUrl'] = ""
            continue

        xbmc.log("EMBY.emby.emby: Tested all connection modes. Failing server connection", xbmc.LOGDEBUG)
        return False, Resync, SaveConfig

    # Use the bundled icon for account selection and connection notifications.
    def get_UserImage(self, UserData):
        UserData['UserImageUrl'] = utils.icon

def get_CompareVersion(Version):
    CompareVersion = ""
    SubVersions = Version.split(".")

    for SubVersion in SubVersions:
        SubVersionInt = int(SubVersion)
        CompareVersion += f"{SubVersionInt:03d}"

    return int(CompareVersion)
