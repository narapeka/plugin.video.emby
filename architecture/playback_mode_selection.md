# Playback Mode Selection - How the Plugin Controls Kodi's Playback Behavior

## Overview

The plugin doesn't explicitly "tell" Kodi which mode to use. Instead, it uses **path format** to implicitly control Kodi's playback behavior. The path format stored in the database determines which handler Kodi uses when playback starts.

## Key Concept: Path Format Determines Mode

Kodi automatically selects the appropriate handler based on the path format:

- **HTTP URLs** (`http://...` or `https://...`) → Kodi uses HTTP handler
- **WebDAV URLs** (`dav://...` or `davs://...`) → Kodi uses WebDAV handler  
- **Path Substitution Paths** (`/emby_addon_mode/...`) → Kodi's path substitution engine translates to HTTP
- **Local/Network Paths** (`C:\...`, `smb://...`, `nfs://...`) → Kodi uses filesystem handler

## How Paths are Constructed During Library Sync

**Location**: `core/common.py` - `set_path_filename()` function

### 1. Mode Selection

The plugin determines the path format based on `AddonModePath`, which is set during settings initialization:

**Location**: `helper/utils.py` - `InitSettings()` (lines 1076-1081)

```python
if webservicemode == "pathsubstitution":
    globals()["AddonModePath"] = "/emby_addon_mode/"
elif webservicemode == "webdav":
    globals()["AddonModePath"] = "dav://127.0.0.1:57342/"
else:
    globals()["AddonModePath"] = "http://127.0.0.1:57342/"
```

### 2. Path Construction

For addon mode (when `useDirectPaths = False`), paths are constructed using `AddonModePath`:

**Location**: `core/common.py` (lines 346-360)

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

**Resulting Path Formats**:

- **HTTP Mode**: `http://127.0.0.1:57342/movies/{ServerId}/{LibraryId}/0/{ItemId}/{MetaFolder}/`
- **WebDAV Mode**: `dav://127.0.0.1:57342/movies/{ServerId}/{LibraryId}/0/{ItemId}/{MetaFolder}/`
- **Path Substitution Mode**: `/emby_addon_mode/movies/{ServerId}/{LibraryId}/0/{ItemId}/{MetaFolder}/`

### 3. Full Path Construction

The full path (including filename) is stored in `c22` (movies) or `c18` (episodes):

**Location**: `core/common.py` (line 362)

```python
Item['KodiFullPath'] = f"{Item['KodiPath']}{Item['KodiFilename']}"
```

### 4. Redirect Limit Addition

For HTTP and WebDAV modes, `|redirect-limit=1000` is appended:

**Location**: `core/common.py` (lines 364-369)

```python
if (Item['KodiPath'].startswith("http://127.0.0.1:57342/") or Item['KodiPath'].startswith("dav://127.0.0.1:57342/")) and Item['Type'] != "Audio":
    Item['KodiFullPath'] += "|redirect-limit=1000"
    Item['KodiPath'] += "|redirect-limit=1000"
```

**Note**: Path substitution mode does NOT get `|redirect-limit=1000` at this stage because it's not an HTTP/WebDAV URL yet.

## Database Storage

**Location**: `database/video_db.py`

The constructed `KodiFullPath` is stored in the database:

- **Movies**: Stored in `c22` column
- **Episodes**: Stored in `c18` column

**Example Database Values**:

- **HTTP Mode**: `http://127.0.0.1:57342/movies/123/456/0/789/MetaFolder/movie.mp4|redirect-limit=1000`
- **WebDAV Mode**: `dav://127.0.0.1:57342/movies/123/456/0/789/MetaFolder/movie.mp4|redirect-limit=1000`
- **Path Substitution Mode**: `/emby_addon_mode/movies/123/456/0/789/MetaFolder/movie.mp4`

## How Kodi Determines Mode During Playback

### 1. Kodi Reads Path from Database

When a user selects a media item for playback, Kodi:

1. Reads the path from the database (`c22` for movies, `c18` for episodes)
2. Examines the path format
3. Selects the appropriate handler based on the path prefix

### 2. Handler Selection

Kodi's internal logic:

```python
# Pseudocode of Kodi's handler selection
if path.startswith("http://") or path.startswith("https://"):
    use_http_handler()
elif path.startswith("dav://") or path.startswith("davs://"):
    use_webdav_handler()
elif path.startswith("/emby_addon_mode/"):
    # Path substitution mode - Kodi's path substitution engine processes it
    translated_path = path_substitution.translate(path)  # → http://127.0.0.1:57342/...
    use_http_handler(translated_path)
else:
    use_filesystem_handler()  # Local paths, SMB, NFS, etc.
```

### 3. Path Substitution Processing

**Location**: Kodi's `advancedsettings.xml` (configured by plugin)

For path substitution mode, Kodi's path substitution engine automatically translates:

```
/emby_addon_mode/movies/123/456/0/789/MetaFolder/movie.mp4
```

to:

```
http://127.0.0.1:57342/movies/123/456/0/789/MetaFolder/movie.mp4|redirect-limit=1000
```

This translation happens **before** Kodi selects the handler, so it effectively becomes an HTTP request.

## Special Case: ISO Files

**Important**: For ISO files, the database stores the **local path** regardless of mode:

**Location**: `core/common.py` (lines 270-271, 284-292)

```python
if Container == 'iso' or KodiPathLower.endswith(".iso"):
    NativeMode = True

if NativeMode:
    # Uses original path from Emby directly
    Item['KodiPath'] = f"{Item['KodiPath'].replace(Temp, '')}"
    # Result: Local path like H:\电影\原盘特效\SGNB\沉睡魔咒 (2014)...
```

However, the mode still matters because:

1. **Path Substitution Mode**: The path format `/emby_addon_mode/...` (even though `c22` contains local path) may trigger path substitution, which creates a filesystem-like context that's compatible with ISO mounting.

2. **HTTP Mode**: Even though `c22` contains the local path, if Kodi goes through the webservice (which may happen based on how the item is selected), the HTTP context interferes with ISO mounting.

## Playback Flow by Mode

### HTTP Mode

1. **Database Path**: `http://127.0.0.1:57342/movies/123/456/0/789/MetaFolder/movie.mp4|redirect-limit=1000`
2. **Kodi Handler**: HTTP handler
3. **Request**: Kodi sends HTTP GET request to `http://127.0.0.1:57342/...`
4. **Webservice**: Plugin's webservice receives request, processes it, redirects to Emby
5. **Result**: Kodi follows redirect to Emby streaming URL

### WebDAV Mode

1. **Database Path**: `dav://127.0.0.1:57342/movies/123/456/0/789/MetaFolder/movie.mp4|redirect-limit=1000`
2. **Kodi Handler**: WebDAV handler
3. **Request**: Kodi sends WebDAV request (PROPFIND, GET, etc.) to `dav://127.0.0.1:57342/...`
4. **Webservice**: Plugin's webservice receives request (only GET is supported), processes it, redirects to Emby
5. **Result**: Kodi follows redirect to Emby streaming URL

### Path Substitution Mode

1. **Database Path**: `/emby_addon_mode/movies/123/456/0/789/MetaFolder/movie.mp4`
2. **Kodi Path Substitution**: Kodi's path substitution engine translates to `http://127.0.0.1:57342/...|redirect-limit=1000`
3. **Kodi Handler**: HTTP handler (after translation)
4. **Request**: Kodi sends HTTP GET request to `http://127.0.0.1:57342/...`
5. **Webservice**: Plugin's webservice receives request, processes it, redirects to Emby
6. **Result**: Kodi follows redirect to Emby streaming URL

**Key Difference**: Path substitution mode uses Kodi's native path substitution feature, which creates a different context than direct HTTP URLs.

## How the Plugin Controls This

The plugin controls which mode is used by:

1. **Settings**: User selects `webservicemode` in settings (HTTP, WebDAV, or path substitution)
2. **Path Construction**: Plugin constructs paths using the appropriate `AddonModePath` during library sync
3. **Database Storage**: Paths are stored in the database with the appropriate format
4. **Kodi Behavior**: Kodi automatically uses the correct handler based on the path format

**The plugin doesn't need to explicitly tell Kodi which mode to use** - the path format does this implicitly.

## Code Flow Summary

### During Library Sync

1. `core/common.py` - `set_path_filename()`:
   - Determines `NativeMode` based on file type and path
   - Constructs path using `AddonModePath` (if not `NativeMode`)
   - Creates `KodiFullPath` with appropriate format

2. `core/movies.py` / `core/episode.py` / etc.:
   - Calls database update functions with `KodiFullPath`

3. `database/video_db.py`:
   - Stores `KodiFullPath` in `c22` (movies) or `c18` (episodes)

### During Playback

1. **User Selection**: User selects media item in Kodi UI

2. **Kodi Reads Database**: Kodi retrieves path from `c22` or `c18`

3. **Handler Selection**: Kodi examines path format and selects handler:
   - HTTP URLs → HTTP handler
   - WebDAV URLs → WebDAV handler
   - `/emby_addon_mode/` → Path substitution → HTTP handler
   - Local paths → Filesystem handler

4. **Request Processing**:
   - HTTP/WebDAV: Kodi sends request to `127.0.0.1:57342`
   - Path Substitution: Kodi translates path, then sends HTTP request
   - Local: Kodi accesses file directly

5. **Webservice** (if applicable):
   - Receives request
   - Extracts metadata from path
   - Determines playback requirements
   - Redirects to Emby streaming URL

6. **Playback**: Kodi streams from Emby server

## Key Takeaways

1. **Path Format is the Control Mechanism**: The plugin controls Kodi's behavior by constructing different path formats, not by explicitly setting modes.

2. **Kodi Handles Mode Selection Automatically**: Kodi's handler selection is based on path format, not plugin instructions.

3. **Path Substitution is Special**: It uses Kodi's native feature to translate paths before handler selection, creating a different context.

4. **Database Stores the Format**: The path format stored in the database determines future playback behavior.

5. **Mode Changes Require Resync**: Changing `webservicemode` requires updating all paths in the database (via `toggle_path()`), which happens automatically when settings change.

## Code Locations

- **Path Construction**: `core/common.py` - `set_path_filename()` (lines 185-378)
- **Mode Path Setting**: `helper/utils.py` - `InitSettings()` (lines 1076-1081)
- **Database Storage**: `database/video_db.py` - `update_movie()`, `update_episode()` (lines 197-198, 717-718)
- **Path Retrieval**: `database/video_db.py` - `get_movie_metadata_for_listitem()`, `get_episode_metadata_for_listitem()` (lines 220-239, 754+)
- **Path Substitution Config**: `helper/xmls.py` - `advanced_settings()` (lines 227-247)
- **Playback Initiation**: `helper/player.py` - `load_KodiItem()` (lines 693-710)
- **List Item Creation**: `emby/listitem.py` - `set_ListItem_from_Kodi_database()` (lines 15-152)
