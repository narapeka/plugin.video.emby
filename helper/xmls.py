import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from xml.etree import ElementTree
import xbmc
import xbmcvfs
from . import utils


# Create master lock compatible sources.
# Also add the kodi.emby.tv source.
def get_Section(FileData, Id):
    PosStart = FileData.find(f"<{Id}>")

    if PosStart != -1:
        PosEnd = FileData.find(f"</{Id}>")

        if PosEnd == -1:
            xbmc.log(f"EMBY.helper.xmls: special://profile/sources.xml file corrupted, {Id} section", xbmc.LOGERROR)
        else:
            return FileData[PosStart + len(f"<{Id}>"):PosEnd]

    return ""

def replace_Section(Id, SectionReplace, SectionMain):
    PosStart = SectionMain.find(f"<{Id}>")
    PosEnd = SectionMain.find(f"</{Id}>")
    return SectionMain[:PosStart + len(f"<{Id}>")] + "\n" + SectionReplace + "\n    " + SectionMain[PosEnd:]

def add_replace_Section(Id, IdSub, SectionReplace, SectionMain):
    PosSubStart = SectionMain.find(f"<{IdSub}>") + len(f"<{IdSub}>")
    PosSubEnd = SectionMain.find(f"</{IdSub}>", PosSubStart)
    PosStart = SectionMain.find(f"<{Id}>", PosSubStart, PosSubEnd)

    if PosStart == -1:
        return SectionMain[:PosSubEnd] + "\n        " + SectionReplace + "\n    " + SectionMain[PosSubEnd:]

    PosEnd = SectionMain.find(f"</{Id}>", PosStart, PosSubEnd)
    return SectionMain[:PosStart] + SectionReplace + SectionMain[PosEnd + len(f"</{Id}>"):]

def get_value(Id, Data):
    Pos = Data.find(Id)

    if Pos != -1:
        Value = Data[Pos:]
        Value = Value[Value.find(">") + 1:]
        return Value[:Value.find("<")]

    return ""

def sources():
    Filepath = 'special://profile/sources.xml'
    FileData = utils.readFileString(Filepath)
    Changed = False
    SectionMain = get_Section(FileData, "sources")
    SectionData = get_Section(SectionMain, "files")

    if not SectionData:
        SectionMain += '\n    <files>'
        SectionMain += '\n        <source>'
        SectionMain += '\n            <name>kodi.emby.tv</name>'
        SectionMain += '\n            <path pathversion="1">http://kodi.emby.tv</path>'
        SectionMain += '\n            <allowsharing>false</allowsharing>'
        SectionMain += '\n        </source>'
        SectionMain += '\n    </files>'
        Changed = True
    else:
        if '<name>kodi.emby.tv</name>' not in SectionData:
            SectionData += '\n        <source>'
            SectionData += '\n            <name>kodi.emby.tv</name>'
            SectionData += '\n            <path pathversion="1">http://kodi.emby.tv</path>'
            SectionData += '\n            <allowsharing>false</allowsharing>'
            SectionData += '\n        </source>'
            SectionMain = replace_Section("files", SectionData, SectionMain)
            Changed = True

    SectionData = get_Section(SectionMain, "video")

    if not SectionData:
        SectionMain += '\n    <video>'
        SectionMain += '\n        <source>'
        SectionMain += '\n            <name>emby-for-kodi-next-gen-addon-video</name>'
        SectionMain += '\n            <path pathversion="1">http://127.0.0.1:57342/</path>'
        SectionMain += '\n            <allowsharing>false</allowsharing>'
        SectionMain += '\n        </source>'
        SectionMain += '\n    </video>'
        Changed = True
    else:
        SectionChanged = False

        if '<name>emby-for-kodi-next-gen-addon-video</name>' not in SectionData:
            SectionData += '\n        <source>'
            SectionData += '\n            <name>emby-for-kodi-next-gen-addon-video</name>'
            SectionData += '\n            <path pathversion="1">http://127.0.0.1:57342/</path>'
            SectionData += '\n            <allowsharing>false</allowsharing>'
            SectionData += '\n        </source>'
            SectionChanged = True

        if SectionChanged:
            SectionMain = replace_Section("video", SectionData, SectionMain)
            Changed = True

    SectionData = get_Section(SectionMain, "music")

    if not SectionData:
        SectionMain += '\n    <music>'
        SectionMain += '\n        <source>'
        SectionMain += '\n            <name>emby-for-kodi-next-gen-addon-music</name>'
        SectionMain += '\n            <path pathversion="1">http://127.0.0.1:57342/</path>'
        SectionMain += '\n            <allowsharing>false</allowsharing>'
        SectionMain += '\n        </source>'
        SectionMain += '\n    </music>'
        Changed = True
    else:
        SectionChanged = False

        if '<name>emby-for-kodi-next-gen-addon-music</name>' not in SectionData:
            SectionData += '\n        <source>'
            SectionData += '\n            <name>emby-for-kodi-next-gen-addon-music</name>'
            SectionData += '\n            <path pathversion="1">http://127.0.0.1:57342/</path>'
            SectionData += '\n            <allowsharing>false</allowsharing>'
            SectionData += '\n        </source>'
            SectionChanged = True

        if SectionChanged:
            SectionMain = replace_Section("music", SectionData, SectionMain)
            Changed = True

    if Changed:
        SectionMain = f'<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>\n<sources>\n{SectionMain}\n</sources>'
        utils.writeFile(Filepath, SectionMain.encode("utf-8"))

# Settings table for audio and subtitle tracks.
def load_defaultvideosettings():
    FileData = utils.readFileString('special://profile/guisettings.xml')

    if FileData:
        SubtitlesLanguage = get_value("subtitles.languages", FileData)
        LocalSubtitlesLanguage = get_value("locale.subtitlelanguage", FileData)
        ShowSubtitles = bool(get_Section(FileData, "showsubtitles") == 'true')

        if LocalSubtitlesLanguage == "default":
            SubtitlesLanguage = xbmc.getLanguage(xbmc.ISO_639_2)
        elif LocalSubtitlesLanguage != "original":
            SubtitlesLanguage = LocalSubtitlesLanguage

        return {'SubtitlesLanguage': SubtitlesLanguage, 'ShowSubtitles': ShowSubtitles}

    return {}

def load_video_resume_limits():
    IgnoreStartSeconds = 180
    IgnoreEndPercent = 8.0
    ProfileSettings = "special://profile/advancedsettings.xml"
    if not xbmcvfs.exists(ProfileSettings):
        ProfileSettings = "special://masterprofile/advancedsettings.xml"

    for Filepath in ("special://xbmc/system/advancedsettings.xml", ProfileSettings):
        FileData = utils.readFileString(Filepath)
        if not FileData:
            continue

        try:
            Video = ElementTree.fromstring(FileData).find("video")
        except ElementTree.ParseError:
            continue

        if Video is None:
            continue

        try:
            IgnoreStartSeconds = min(900, max(0, int(Video.findtext("ignoresecondsatstart", IgnoreStartSeconds))))
        except ValueError:
            pass

        try:
            IgnoreEndPercent = min(100.0, max(0.0, float(Video.findtext("ignorepercentatend", IgnoreEndPercent))))
        except ValueError:
            pass

    return IgnoreStartSeconds, IgnoreEndPercent


def advanced_settings(CurlTimeout=None):
    if CurlTimeout is None:
        CurlTimeout = utils.curltimeouts

    Changed = False
    Filepath = 'special://profile/advancedsettings.xml'
    FileData = utils.readFileString(Filepath)

    SectionMain = get_Section(FileData, "advancedsettings")
    SectionData = get_Section(SectionMain, "network")

    if not SectionData:
        SectionMain += '\n    <network>'
        SectionMain += f'\n        <curlclienttimeout>{CurlTimeout}</curlclienttimeout>'
        SectionMain += '\n    </network>'
        Changed = True
    else:
        SectionData = get_Section(SectionData, "curlclienttimeout")

        if str(CurlTimeout) != SectionData:
            SectionMain = add_replace_Section("curlclienttimeout", "network", f"<curlclienttimeout>{CurlTimeout}</curlclienttimeout>", SectionMain)
            Changed = True

    SectionData = get_Section(SectionMain, "videolibrary")

    if not SectionData:
        SectionMain += '\n  <videolibrary>'
        SectionMain += '\n      <dateadded>0</dateadded>' # Disable read dateadded from files, this results in blocking stat/HEAD request in webservice.py
        SectionMain += '\n  </videolibrary>'
        Changed = True
    else:
        SectionData = get_Section(SectionData, "dateadded")

        if "0" != SectionData:
            SectionMain = add_replace_Section("dateadded", "videolibrary", "<dateadded>0</dateadded>", SectionMain)
            Changed = True

    SectionData = get_Section(SectionMain, "musiclibrary")

    if not SectionData:
        SectionMain += '\n  <musiclibrary>'
        SectionMain += '\n      <dateadded>0</dateadded>'
        SectionMain += '\n  </musiclibrary>'
        Changed = True
    else:
        SectionData = get_Section(SectionData, "dateadded")

        if "0" != SectionData:
            SectionMain = add_replace_Section("dateadded", "musiclibrary", "<dateadded>0</dateadded>", SectionMain)
            Changed = True

    SectionData = get_Section(SectionMain, "video")

    if not SectionData:
        SectionMain += '\n    <video>'
        SectionMain += '\n        <excludefromlisting>'
        SectionMain += '\n            <regexp>^http:\\/\\/127.0.0.1:57342(?!.*(dynamic|musicvideo|tvshows|video|movies))</regexp>'
        SectionMain += '\n        </excludefromlisting>'
        SectionMain += '\n        <excludefromscan>'
        SectionMain += '\n            <regexp>http://127.0.0.1:57342/</regexp>'
        SectionMain += '\n        </excludefromscan>'
        SectionMain += '\n        <excludetvshowsfromscan>'
        SectionMain += '\n            <regexp>http://127.0.0.1:57342/</regexp>'
        SectionMain += '\n        </excludetvshowsfromscan>'
        SectionMain += '\n    </video>'
        Changed = True
    elif "<regexp>http://127.0.0.1:57342/</regexp>" not in SectionData:
        SectionData += '\n        <excludefromlisting>'
        SectionData += '\n            <regexp>^http:\\/\\/127.0.0.1:57342(?!.*(dynamic|musicvideo|tvshows|video|movies))</regexp>'
        SectionData += '\n        </excludefromlisting>'
        SectionData += '\n        <excludefromscan>'
        SectionData += '\n            <regexp>http://127.0.0.1:57342/</regexp>'
        SectionData += '\n        </excludefromscan>'
        SectionData += '\n        <excludetvshowsfromscan>'
        SectionData += '\n            <regexp>http://127.0.0.1:57342/</regexp>'
        SectionData += '\n        </excludetvshowsfromscan>'
        SectionMain = replace_Section("video", SectionData, SectionMain)
        Changed = True

    SectionData = get_Section(SectionMain, "audio")

    if not SectionData:
        SectionMain += '\n    <audio>'
        SectionMain += '\n        <excludefromlisting>'
        SectionMain += '\n            <regexp>^http:\\/\\/127.0.0.1:57342(?!.*(dynamic|audio))</regexp>'
        SectionMain += '\n        </excludefromlisting>'
        SectionMain += '\n        <excludefromscan>'
        SectionMain += '\n            <regexp>http://127.0.0.1:57342/</regexp>'
        SectionMain += '\n        </excludefromscan>'
        SectionMain += '\n    </audio>'
        Changed = True
    elif "<regexp>http://127.0.0.1:57342/</regexp>" not in SectionData:
        SectionData += '\n        <excludefromlisting>'
        SectionData += '\n            <regexp>^http:\\/\\/127.0.0.1:57342(?!.*(dynamic|audio))</regexp>'
        SectionData += '\n        </excludefromlisting>'
        SectionData += '\n        <excludefromscan>'
        SectionData += '\n            <regexp>http://127.0.0.1:57342/</regexp>'
        SectionData += '\n        </excludefromscan>'
        SectionMain = replace_Section("audio", SectionData, SectionMain)
        Changed = True

    if Changed:
        SectionMain = f'<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>\n<advancedsettings>\n{SectionMain}\n</advancedsettings>'
        utils.writeFile(Filepath, SectionMain.encode("utf-8"))

    return Changed


def reset_configuration():
    sources = {
        "files": ("kodi.emby.tv", "http://kodi.emby.tv"),
        "video": ("emby-for-kodi-next-gen-addon-video", utils.AddonModePath),
        "music": ("emby-for-kodi-next-gen-addon-music", utils.AddonModePath),
    }
    rules = {
        "network/curlclienttimeout": str(utils.curltimeouts),
        "videolibrary/dateadded": "0",
        "musiclibrary/dateadded": "0",
        "video/excludefromlisting/regexp": r"^http:\/\/127.0.0.1:57342(?!.*(dynamic|musicvideo|tvshows|video|movies))",
        "audio/excludefromlisting/regexp": r"^http:\/\/127.0.0.1:57342(?!.*(dynamic|audio))",
        "video/excludefromscan/regexp": utils.AddonModePath,
        "video/excludetvshowsfromscan/regexp": utils.AddonModePath,
        "audio/excludefromscan/regexp": utils.AddonModePath,
    }

    changes = []
    for name in ("sources", "advancedsettings"):
        path = Path(xbmcvfs.translatePath(f"special://profile/{name}.xml"))
        if not path.is_file():
            continue

        parser = ElementTree.XMLParser(target=ElementTree.TreeBuilder(insert_comments=True, insert_pis=True))
        tree = ElementTree.parse(path, parser=parser)
        root = tree.getroot()
        if root.tag != name:
            raise ValueError(f"Unexpected root in {path}")

        changed_sections = set()
        if name == "sources":
            for section, (source_name, source_path) in sources.items():
                for parent in root.findall(section):
                    for source in parent.findall("source"):
                        if source.findtext("name") == source_name and [item.text for item in source.findall("path")] == [source_path]:
                            parent.remove(source)
                            changed_sections.add(parent)
        else:
            for key, value in rules.items():
                section, tag = key.rsplit("/", 1)
                for parent in root.findall(section):
                    for entry in parent.findall(tag):
                        if (entry.text or "").strip() == value:
                            parent.remove(entry)
                            changed_sections.add(parent)

        if changed_sections:
            parents = {child: parent for parent in root.iter() for child in parent}
            for section in changed_sections:
                while section is not root and not len(section) and not section.attrib and not (section.text or "").strip():
                    parent = parents[section]
                    parent.remove(section)
                    section = parent
            changes.append((path, tree))

    for path, tree in changes:
        with NamedTemporaryFile(dir=path.parent, delete=False) as output:
            temporary = Path(output.name)

        try:
            tree.write(temporary, encoding="utf-8", xml_declaration=True)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
