# Path Substitution Mode - Technical Documentation

## Overview

Path substitution is one of three webservice modes available in the Emby for Kodi plugin. It uses Kodi's native path substitution feature to present virtual local paths (`/emby_addon_mode/`) to Kodi, which are then automatically translated to HTTP requests to the plugin's local webservice.

## Key Characteristics

- **Virtual Path Format**: `/emby_addon_mode/`
- **No URL Encoding**: Filenames are stored without URL encoding (unlike HTTP and WebDAV modes)
- **Kodi Native Feature**: Leverages Kodi's built-in path substitution mechanism
- **Chapter Image Support**: Supports chapter image extraction in addon mode
- **Potential Playback Issues**: May cause playback issues on some devices

## Configuration

### User Setting

Path substitution is selected via the `webservicemode` setting in `resources/settings.xml`:

```xml
<setting id="webservicemode" type="string" label="33744" help="">
    <level>2</level>
    <default>http</default>
    <constraints>
        <options>
            <option label="33747">http</option>
            <option label="33745">webdav</option>
            <option label="33746">pathsubstitution</option>
        </options>
    </constraints>
    <control type="spinner" format="string"/>
</setting>
```

### Kodi Advanced Settings Configuration

When path substitution mode is enabled, the plugin automatically configures Kodi's `advancedsettings.xml` file to set up the path substitution rule.

**Location**: `helper/xmls.py` (lines 227-247)

The plugin adds the following configuration to Kodi's `advancedsettings.xml`:

```xml
<pathsubstitution>
    <substitute>
        <from>/emby_addon_mode/</from>
        <to>http://127.0.0.1:57342/|redirect-limit=1000</to>
    </substitute>
</pathsubstitution>
```

This tells Kodi that any path starting with `/emby_addon_mode/` should be automatically translated to `http://127.0.0.1:57342/` (the plugin's local webservice).

### Path Exclusion Configuration

The plugin also configures Kodi to exclude addon-generated paths from library scans and listings:

```xml
<video>
    <excludefromlisting>
        <regexp>^\/emby_addon_mode(?!.*(dynamic|musicvideo|tvshows|video|movies))</regexp>
        <regexp>^http:\/\/127.0.0.1:57342(?!.*(dynamic|musicvideo|tvshows|video|movies))</regexp>
        <regexp>^dav:\/\/127.0.0.1:57342(?!.*(dynamic|musicvideo|tvshows|video|movies))</regexp>
    </excludefromlisting>
    <excludefromscan>
        <regexp>/emby_addon_mode/</regexp>
        <regexp>http://127.0.0.1:57342/</regexp>
        <regexp>dav://127.0.0.1:57342/</regexp>
    </excludefromscan>
    <excludetvshowsfromscan>
        <regexp>/emby_addon_mode/</regexp>
        <regexp>http://127.0.0.1:57342/</regexp>
        <regexp>dav://127.0.0.1:57342/</regexp>
    </excludetvshowsfromscan>
</video>
```

## Initialization Process

### 1. Settings Loading

**Location**: `helper/utils.py` - `InitSettings()` function (lines 1076-1081)

When settings are initialized, the plugin checks the `webservicemode` setting:

```python
if webservicemode == "pathsubstitution":
    globals()["AddonModePath"] = "/emby_addon_mode/"
elif webservicemode == "webdav":
    globals()["AddonModePath"] = "dav://127.0.0.1:57342/"
else:
    globals()["AddonModePath"] = "http://127.0.0.1:57342/"
```

This sets the global `AddonModePath` variable that will be used throughout the plugin to construct media paths.

### 2. Advanced Settings Configuration

**Location**: `helper/xmls.py` - `advanced_settings()` function

The plugin checks if the path substitution configuration exists in Kodi's `advancedsettings.xml` and adds it if missing. This happens during plugin startup and whenever settings change.

### 3. Kodi Metadata Extraction Settings

**Location**: `helper/utils.py` (lines 1137-1142)

For path substitution and WebDAV modes, the plugin disables Kodi's metadata extraction to prevent conflicts:

```python
if not useDirectPaths and webservicemode in ("pathsubstitution", "webdav"):
    SendJson('{"jsonrpc":"2.0", "id":1, "method":"Settings.SetSettingValue", "params": {"setting":"myvideos.extractflags","value":false}}', True)
    SendJson('{"jsonrpc":"2.0", "id":1, "method":"Settings.SetSettingValue", "params": {"setting":"myvideos.extractthumb","value":false}}', True)
    SendJson('{"jsonrpc":"2.0", "id":1, "method":"Settings.SetSettingValue", "params": {"setting":"myvideos.usetags","value":false}}', True)
    SendJson('{"jsonrpc":"2.0", "id":1, "method":"Settings.SetSettingValue", "params": {"setting":"musicfiles.usetags","value":false}}', True)
    SendJson('{"jsonrpc":"2.0", "id":1, "method":"Settings.SetSettingValue", "params": {"setting":"musicfiles.findremotethumbs","value":false}}', True)
    SendJson('{"jsonrpc":"2.0", "id":1, "method":"Settings.SetSettingValue", "params": {"setting":"myvideos.extractchapterthumbs","value":true}}', True)
```

**Note**: Chapter image extraction (`myvideos.extractchapterthumbs`) is **enabled** for path substitution mode, which is one of its key advantages.

## Path Construction

### Media Item Paths

**Location**: `core/common.py` - `set_path_filename()` function (lines 293-361)

When `useDirectPaths` is `False` (addon mode), paths are constructed using `AddonModePath`:

```python
if Item['Type'] == "Series":
    Item['KodiPathParent'] = f"{utils.AddonModePath}{Dynamic}tvshows/{ServerId}/{Item['LibraryId']}/"
    Item['KodiPath'] = f"{utils.AddonModePath}{Dynamic}tvshows/{ServerId}/{Item['LibraryId']}/0/{Item['Id']}/"
elif Item['Type'] == "Episode":
    Item['KodiPath'] = f"{utils.AddonModePath}{Dynamic}tvshows/{ServerId}/{Item['LibraryId']}/{Item['SeriesId']}/{Item['Id']}/{MetaFolder}/"
elif Item['Type'] == "Movie":
    Item['KodiPath'] = f"{utils.AddonModePath}{Dynamic}movies/{ServerId}/{Item['LibraryId']}/0/{Item['Id']}/{MetaFolder}/"
# ... etc
```

For path substitution mode, `AddonModePath` is `/emby_addon_mode/`, so paths look like:
- `/emby_addon_mode/movies/{ServerId}/{LibraryId}/0/{ItemId}/{MetaFolder}/`
- `/emby_addon_mode/tvshows/{ServerId}/{LibraryId}/0/{SeriesId}/{EpisodeId}/{MetaFolder}/`

### Filename Encoding

**Location**: `helper/utils.py` (lines 720-721)

**Critical Difference**: Path substitution mode does **NOT** URL-encode filenames:

```python
if not NativeMode and webservicemode != "pathsubstitution":
    Filename = quote(Filename)
```

This means filenames with special characters are stored as-is in the database, unlike HTTP and WebDAV modes where they are URL-encoded.

## Request Flow

### 1. Kodi Requests Media

When Kodi needs to play a media file, it sees a path like:
```
/emby_addon_mode/movies/123/456/0/789/MetaFolder/movie.mp4
```

### 2. Kodi Path Substitution

Kodi's path substitution engine (configured in `advancedsettings.xml`) automatically translates this to:
```
http://127.0.0.1:57342/movies/123/456/0/789/MetaFolder/movie.mp4|redirect-limit=1000
```

### 3. Local Webservice Processing

**Location**: `hooks/webservice.py`

The plugin's local webservice (listening on `127.0.0.1:57342`) receives the HTTP request and:

1. Parses the path to extract:
   - Server ID
   - Library ID
   - Item ID
   - Media source metadata (encoded in the MetaFolder)
   - Filename

2. Constructs an Emby API request to get playback information:
   - Determines transcoding requirements
   - Selects appropriate media source
   - Handles subtitle selection
   - Manages intro/credit skip positions

3. Sends a `307 Temporary Redirect` to Kodi pointing to the actual Emby streaming URL:
   ```python
   def send_redirect(self, client, EmbyUrl, Headers):
       RedirectUrl = f"{EmbyUrl}|redirect-limit=1000"
       Response = f"HTTP/1.1 307 Temporary Redirect\r\nLocation: {RedirectUrl}\r\n\r\n"
       client.send(Response.encode('utf-8'))
   ```

### 4. Kodi Follows Redirect

Kodi follows the redirect and streams the media directly from the Emby server.

## Database Path Management

### Path Storage

Paths are stored in multiple Kodi database tables:

- **`path` table**: Base path for each media item
- **`files` table**: Full path including filename
- **`movie` table**: `c19` (path ID), `c22` (full path)
- **`episode` table**: `c18` (full path)
- **`musicvideo` table**: `c13` (full path)
- **`song` table**: `strVideoURL` (for music videos linked to songs)

### Path Updates on Mode Change

**Location**: `hooks/monitor.py` - `settingschanged()` function (lines 347-356)

When the user changes the webservice mode, the plugin updates all paths in the database:

```python
# path(substitution) changed, update database pathes
if AddonModePathPreviousValue != utils.AddonModePath:
    SQLs = {}
    dbio.DBOpenRW("video", "settingschanged", SQLs)
    SQLs["video"].toggle_path(AddonModePathPreviousValue, utils.AddonModePath)
    dbio.DBCloseRW("video", "settingschanged", SQLs)
    dbio.DBOpenRW("music", "settingschanged", SQLs)
    SQLs["music"].toggle_path(AddonModePathPreviousValue, utils.AddonModePath)
    dbio.DBCloseRW("music", "settingschanged", SQLs)
    utils.refresh_widgets(True)
    utils.refresh_widgets(False)
```

### Path Toggle Logic

**Location**: `database/common_db.py` - `toggle_path()` function (lines 80-96)

The `toggle_path()` function handles converting paths between different modes:

```python
def toggle_path(CurrentPath, NewPath):
    if NewPath == "http://127.0.0.1:57342/":
        if CurrentPath.startswith("/emby_addon_mode/"):
            return f'{CurrentPath.replace("/emby_addon_mode/", "http://127.0.0.1:57342/")}|redirect-limit=1000'
        return CurrentPath.replace("dav://127.0.0.1:57342/", "http://127.0.0.1:57342/")
    
    if NewPath == "/emby_addon_mode/":
        if CurrentPath.startswith("http://127.0.0.1:57342/"):
            return CurrentPath.replace("http://127.0.0.1:57342/", "/emby_addon_mode/").replace("|redirect-limit=1000", "")
        return CurrentPath.replace("dav://127.0.0.1:57342/", "/emby_addon_mode/").replace("|redirect-limit=1000", "")
    
    # WebDAV mode
    if CurrentPath.startswith("/emby_addon_mode/"):
        return f'{CurrentPath.replace("/emby_addon_mode/", "dav://127.0.0.1:57342/")}|redirect-limit=1000'
    return CurrentPath.replace("http://127.0.0.1:57342/", "dav://127.0.0.1:57342/")
```

**Key Points**:
- When switching TO path substitution: Removes `|redirect-limit=1000` suffix
- When switching FROM path substitution: Adds `|redirect-limit=1000` suffix for HTTP mode

### Filename Encoding/Decoding

**Location**: `database/video_db.py` - `toggle_path()` method (lines 1646-1700)

When toggling paths, the plugin also handles filename encoding:

```python
def toggle_path(self, OldPath, NewPath):
    QuotedNew = NewPath != "/emby_addon_mode/"  # Path substitution doesn't use URL encoding
    QuotedOld = OldPath != "/emby_addon_mode/"
    
    # Update all filenames in the files table
    for FileName in FileNames:
        if QuotedNew:
            if QuotedOld:
                FileNameNew = FileName[1]  # Both encoded, keep as-is
            else:
                FileNameNew = quote(FileName[1])  # Encode when switching TO HTTP/WebDAV
        else:
            if QuotedOld:
                FileNameNew = unquote(FileName[1])  # Decode when switching TO path substitution
            else:
                FileNameNew = FileName[1]  # Both unencoded, keep as-is
```

This ensures that:
- **Switching TO path substitution**: Filenames are URL-decoded (e.g., `movie%20name.mp4` → `movie name.mp4`)
- **Switching FROM path substitution**: Filenames are URL-encoded (e.g., `movie name.mp4` → `movie%20name.mp4`)

## Trigger Points

### 1. Plugin Startup

**Location**: `service.py` → `hooks/monitor.py` - `StartUp()`

When the plugin starts:
1. Settings are loaded (`utils.InitSettings()`)
2. `AddonModePath` is set based on `webservicemode`
3. `advanced_settings()` is called to configure Kodi's path substitution
4. Kodi metadata extraction settings are adjusted

### 2. Settings Change

**Location**: `hooks/monitor.py` - `settingschanged()` function

When the user changes the `webservicemode` setting:
1. Settings are reloaded
2. `AddonModePath` is recalculated
3. If `AddonModePath` changed:
   - All paths in video and music databases are updated via `toggle_path()`
   - Filenames are encoded/decoded as needed
   - Widgets are refreshed

### 3. Library Sync

**Location**: `database/library.py` - `KodiStartSync()`

During library synchronization:
1. Media items are fetched from Emby
2. Paths are constructed using `core/common.py` - `set_path_filename()`
3. Paths are stored in Kodi's database using the current `AddonModePath`

### 4. Media Playback

**Location**: `hooks/webservice.py`

When Kodi requests media playback:
1. Kodi sees path like `/emby_addon_mode/...`
2. Kodi's path substitution translates it to `http://127.0.0.1:57342/...`
3. Plugin's webservice processes the request
4. Plugin redirects Kodi to Emby streaming URL

## Advantages of Path Substitution Mode

1. **Chapter Image Support**: Unlike HTTP mode, path substitution supports chapter image extraction
2. **Native Kodi Integration**: Uses Kodi's built-in path substitution feature
3. **Cleaner Paths**: Paths appear as local filesystem paths to Kodi
4. **No URL Encoding**: Filenames are stored without encoding, making them more readable

## Disadvantages of Path Substitution Mode

1. **Potential Playback Issues**: May cause playback problems on some devices
2. **Requires Kodi Restart**: Changes to `advancedsettings.xml` may require Kodi restart
3. **Filename Limitations**: Special characters in filenames might cause issues without URL encoding
4. **Complexity**: Requires coordination between plugin and Kodi's path substitution engine

## Comparison with Other Modes

| Feature | Path Substitution | HTTP | WebDAV |
|---------|------------------|------|--------|
| Path Format | `/emby_addon_mode/` | `http://127.0.0.1:57342/` | `dav://127.0.0.1:57342/` |
| URL Encoding | No | Yes | Yes |
| Chapter Images | Yes | No | No |
| Kodi Native Feature | Yes (path substitution) | No | Partial (WebDAV support) |
| Playback Issues | Possible | Rare | Possible |
| Redirect Limit | Not needed | Required | Required |

## Code Locations Summary

- **Settings Definition**: `resources/settings.xml`
- **Path Initialization**: `helper/utils.py` - `InitSettings()` (line 1076)
- **Advanced Settings Config**: `helper/xmls.py` - `advanced_settings()` (lines 227-247)
- **Path Construction**: `core/common.py` - `set_path_filename()` (lines 293-361)
- **Filename Encoding**: `helper/utils.py` (lines 720-721)
- **Settings Change Handler**: `hooks/monitor.py` - `settingschanged()` (lines 347-356)
- **Path Toggle Logic**: `database/common_db.py` - `toggle_path()` (lines 80-96)
- **Database Path Updates**: `database/video_db.py` - `toggle_path()` (lines 1646-1700)
- **Webservice Handler**: `hooks/webservice.py`
- **Metadata Extraction Settings**: `helper/utils.py` (lines 1137-1142)

## Troubleshooting

### Paths Not Updating

If paths don't update after changing modes:
1. Check that `advancedsettings.xml` contains the path substitution rule
2. Verify `AddonModePath` is set correctly in `utils.py`
3. Check database for old path format
4. Restart Kodi if `advancedsettings.xml` was modified

### Playback Issues

If playback fails in path substitution mode:
1. Verify the local webservice is running on port 57342
2. Check Kodi logs for path substitution errors
3. Try switching to HTTP mode as a workaround
4. Verify `advancedsettings.xml` configuration is correct

### Filename Issues

If filenames with special characters cause problems:
1. Check if filenames are properly decoded when switching to path substitution
2. Verify `toggle_path()` is encoding/decoding correctly
3. Check database `files` table for filename encoding status
