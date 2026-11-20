import xbmc
from database import dbio
from emby import listitem, metadata
from . import utils, playerops, cache, player, versions

def load_item(KodiId=None, KodiType=None):
    ServerId = xbmc.getInfoLabel('ListItem.Property(embyserverid)')
    ListItemEmbyId = xbmc.getInfoLabel('ListItem.Property(embyid)')

    if not KodiType:
        KodiType = xbmc.getInfoLabel('ListItem.DBTYPE')

    if not ServerId:
        if not KodiId:
            KodiId = xbmc.getInfoLabel('ListItem.DBID')

        EmbyFavourite = None
        EmbyId = None
        ServerId = None

        for ServerId in utils.EmbyServers:
            embydb = dbio.DBOpenRO(ServerId, "contextmenu_item")
            EmbyId, EmbyFavourite = embydb.get_EmbyId_EmbyFavourite_by_KodiId_KodiType(KodiId, KodiType)
            dbio.DBCloseRO(ServerId, "contextmenu_item")

            if EmbyId:
                break
        else:
            ServerId = None

        return EmbyId, ServerId, EmbyFavourite, KodiType

    return ListItemEmbyId, ServerId, None, KodiType


def multiversion(Path=""):
    if not Path:
        Path = xbmc.getInfoLabel('ListItem.FileNameAndPath')

    if Path.startswith("stack://"):
        Path = Path[len("stack://"):].split(" , ", 1)[0]

    if not Path.startswith(utils.AddonModePath):
        return

    Payload = Path[len(utils.AddonModePath) - 1:].split('|', 1)[0]
    MetaData = metadata.load_MetaData(Payload, False, False)
    if not MetaData or len(MetaData['MediaSources']) < 2:
        return
    Selection = []

    for MediaSource in MetaData['MediaSources']:
        Selection.append(f"{MediaSource[0]['Name']} - {utils.SizeToText(MediaSource[0].get('Size'))} - {MediaSource[0]['Path']}")

    MetaData['SelectionIndexMediaSource'] = utils.Dialog.select(utils.Translate(33453), Selection, preselect=0)

    if MetaData['SelectionIndexMediaSource'] == -1: # Cancel
        metadata.MediaSourceContextMenu = None
        versions.clear_choice()
        return

    metadata.MediaSourceContextMenu = (MetaData['ServerId'], MetaData['EmbyId'], MetaData['MediaSources'][MetaData['SelectionIndexMediaSource']][0]['Id'])
    VersionContext = player.get_version_context(MetaData['ServerId'], MetaData['EmbyId'], MetaData['KodiType'])
    versions.remember_choice(MetaData['MediaSources'], MetaData['SelectionIndexMediaSource'], VersionContext)

    if not MetaData["isDynamic"]:
        videodb = dbio.DBOpenRO("video", "multiversion")

        if MetaData["KodiType"] == "episode":
            ItemKodi = videodb.get_episode_metadata_for_listitem(MetaData["KodiId"], "")
        elif MetaData["KodiType"] == "musicvideo":
            ItemKodi = videodb.get_musicvideos_metadata_for_listitem(MetaData["KodiId"], "")
        elif MetaData["KodiType"] in ("movie", "video"):
            ItemKodi = videodb.get_movie_metadata_for_listitem(MetaData["KodiId"], "")
        else:
            ItemKodi = {}

        dbio.DBCloseRO("video", "multiversion")

        if ItemKodi:
            listitem.set_ListItem_from_Kodi_database(ItemKodi, "")
            playerops.Play(ItemKodi['KodiFullPath'], ItemKodi['ListItem'], False)
    else:
        if MetaData["KodiType"] not in utils.KodiTypeMapping:
            return

        EmbyType = utils.KodiTypeMapping[MetaData["KodiType"]]
        Item = utils.EmbyServers[MetaData["ServerId"]].API.get_Item(MetaData["EmbyId"], (EmbyType,), True, False, False)

        if not Item:
            return

        listitem.set_playback_listitem(Item, MetaData["ServerId"])
        cache.add_Item(Item, MetaData["ServerId"])
        playerops.Play(Item['KodiFullPath'], Item['ListItem'], False)


def refreshitem():
    EmbyId, ServerId, _, KodiType = load_item()

    if not EmbyId:
        return

    utils.EmbyServers[ServerId].API.refresh_item(EmbyId)

    if KodiType in utils.KodiTypeMapping:
        utils.EmbyServers[ServerId].library.updated([(EmbyId, utils.KodiTypeMapping[KodiType], "unknown")], True)
