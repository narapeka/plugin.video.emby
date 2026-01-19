# STRM Files with ISO Content - Special Case Documentation

## Overview

This document explains why `.strm` files containing local paths to ISO files (DVD/Blu-ray images) can only be played in **Path Substitution** mode and not in **HTTP** mode. This is a special case that requires understanding how the plugin handles ISO files differently from regular video files.

## What are STRM Files?

`.strm` files are text files that contain a single line with a path to a media file. They are commonly used in Kodi/Emby to:
- Reference files stored outside the library structure
- Point to network locations
- Link to files that should be played directly without going through the media server

Example `.strm` file content:
```
C:\Movies\MyMovie.iso
```

or

```
\\server\share\movie.iso
```

## The Problem

When a `.strm` file contains a path to an ISO file (DVD/Blu-ray disc image), the plugin:
1. Detects the ISO file and sets `NativeMode = True`
2. Stores the **local path** in the database (`c22` column) regardless of webservice mode
3. However, the playback behavior differs between modes

**Important Discovery**: The database `c22` column contains the local path (e.g., `H:\电影\原盘特效\SGNB\沉睡魔咒 (2014)...`) for ISO files, regardless of whether HTTP or path substitution mode is used. This is because when `NativeMode = True`, the plugin uses the original path from Emby directly.

**The issue**: Even though `c22` contains the local path, Kodi's playback behavior differs:
- **Path Substitution Mode**: Kodi can successfully mount and play ISO files from the local path
- **HTTP Mode**: Kodi may fail to mount ISO files, even though the path is local. This suggests the issue is not with the stored path, but with how Kodi handles the path during playback initialization or how the plugin intercepts the playback request.

## Database Storage - Important Discovery

**Key Finding**: The database `c22` column stores the **local path** for ISO files regardless of webservice mode (HTTP or path substitution). This is because:

1. When an ISO file is detected, `NativeMode = True` is forced (line 270-271)
2. When `NativeMode = True`, the plugin uses the original path from Emby directly (lines 284-292)
3. `KodiFullPath` is constructed from this local path and stored in `c22`

**Example**: For a `.strm` file containing `H:\电影\原盘特效\SGNB\沉睡魔咒 (2014)`, the `c22` column will contain:
```
H:\电影\原盘特效\SGNB\沉睡魔咒 (2014)...
```

This is the same in both HTTP and path substitution modes.

**The Real Issue**: The difference between modes is not in the database storage, but in how Kodi processes the playback request. The HTTP mode creates a context that interferes with ISO mounting, even though the stored path is local.

## How ISO Files are Detected

### During Library Sync

**Location**: `core/common.py` - `set_path_filename()` function

When the plugin processes a media item from Emby:

1. **STRM File Detection** (lines 228-232):
   ```python
   # Addonmode replace filextensions
   if Item['KodiPath'].endswith('.strm') and 'Container' in Item:
       Item['KodiPath'] = Item['KodiPath'].replace('.strm', "")
       
       if not Item['KodiPath'].endswith(Item['Container']):
           Item['KodiPath'] += f".{Item['Container']}"
   ```
   The plugin removes the `.strm` extension and replaces it with the actual container type (e.g., `.iso`).

2. **ISO File Detection** (lines 270-271):
   ```python
   if Container == 'iso' or KodiPathLower.endswith(".iso"):
       NativeMode = True
   ```
   When an ISO file is detected, `NativeMode` is set to `True`, indicating that the file should be accessed directly.

3. **Path Construction** (lines 284-292 for NativeMode, 293-361 for AddonMode):
   - **If `NativeMode = True`**: The path is used directly from Emby (the original local path from the `.strm` file)
     ```python
     if NativeMode:
         PathSeperator = utils.get_Path_Seperator(Item['KodiPath'])
         Temp = Item['KodiPath'].rsplit(PathSeperator, 1)[1]
         # ...
         Item['KodiPath'] = f"{Item['KodiPath'].replace(Temp, '')}"
     ```
     This means `KodiFullPath` (stored in `c22`) contains the **local path** (e.g., `H:\电影\原盘特效\SGNB\沉睡魔咒 (2014)...`), regardless of webservice mode.
   - **If `NativeMode = False`**: The path is constructed using `AddonModePath` (HTTP, WebDAV, or path substitution)

4. **Metadata Encoding** (lines 314-344):
   The original path from the `.strm` file is encoded into the `MetaFolder`:
   ```python
   MediasourceString = f"{MediaSourceItem.get('Name', 'unknown').replace(':', '<;>')}:{MediaSourceItem['Size'] or 0}:{MediaSourceItem['Id']}:{MediaSourceItem['Path'].replace(':', '<;>')}:..."
   ```
   This ensures the original local path is preserved in the metadata, even though the database path uses the addon mode format.

## Request Flow

### Path Substitution Mode

**Note**: Even though `c22` contains the local path, Kodi may still go through the webservice when initiating playback. The path substitution mechanism affects how Kodi processes the initial request.

1. **Kodi Reads Database**: Kodi reads `c22` which contains the local path (e.g., `H:\电影\原盘特效\SGNB\沉睡魔咒 (2014)...`)

2. **Playback Initiation**: When Kodi tries to play the item, it may:
   - Use the path directly if it recognizes it as a local filesystem path
   - Or go through the webservice if the path format triggers addon mode

3. **If Webservice is Involved** (`hooks/webservice.py`):
   - The webservice receives the request
   - Extracts metadata from the URL path
   - Decodes the original local path from the metadata
   - Detects it's an ISO file (line 712: `if MetaData['MediaType'] == 'i'`)
   - Calls `LoadISO()` function

4. **LoadISO Function** (lines 474-489):
   ```python
   def LoadISO(MetaData, client): # native content
       player.MultiselectionDone = True
       Path = MetaData['MediaSources'][MetaData['SelectionIndexMediaSource']][0]['Path']
       
       if Path.startswith('\\\\'):
           Path = Path.replace('\\\\', "smb://", 1).replace('\\\\', "\\").replace('\\', "/")
       
       MetaData['MediaSources'][MetaData['SelectionIndexMediaSource']][0]['Path'] = Path
       ListItem = player.load_KodiItem("LoadISO", MetaData['KodiId'], MetaData['Type'], Path)
       
       if not ListItem:
           client.send(sendOK)
       else:
           set_QueuedPlayingItem(MetaData, None)
           player.replace_playlist_listitem(ListItem, MetaData['MediaSources'][MetaData['SelectionIndexMediaSource']][0]['Path'])
           set_DelayedContent(MetaData['Payload'], "blank")
   ```
   - Extracts the original local path from metadata
   - Converts Windows UNC paths to `smb://` format if needed
   - Loads the Kodi list item with the **local path** from the database
   - Replaces the playlist item with the local path
   - Kodi can now mount and play the ISO file directly

5. **Why It Works**: 
   - Path substitution mode's path format (`/emby_addon_mode/...`) is more compatible with Kodi's filesystem operations
   - When `LoadISO()` replaces the playlist item, Kodi successfully recognizes and mounts the ISO file
   - The path substitution mechanism doesn't interfere with ISO mounting

### HTTP Mode

**Note**: Even though `c22` contains the local path, HTTP mode still fails for ISO files. This suggests the issue is with how Kodi processes the playback request, not the stored path.

1. **Kodi Reads Database**: Kodi reads `c22` which contains the local path (same as path substitution mode)

2. **Playback Initiation**: When Kodi tries to play the item:
   - The path format or some other mechanism may trigger the webservice
   - Or Kodi may attempt to use the path directly but encounter issues

3. **If Webservice is Involved**:
   - The webservice receives an HTTP request
   - Same processing as path substitution mode up to `LoadISO()`
   - `LoadISO()` extracts the local path and replaces the playlist item

4. **The Problem**:
   - Even though `c22` contains the local path and `LoadISO()` replaces the playlist item with the local path, playback may still fail
   - Possible reasons:
     - Kodi's HTTP handler may have already started processing the request as a network stream before `LoadISO()` can replace it
     - The HTTP URL format in the initial request may cause Kodi to cache or lock the URL format
     - Kodi's ISO mounting logic may check the initial request format and reject HTTP URLs
     - There may be timing issues where Kodi attempts to mount the ISO before the playlist replacement completes
   - The HTTP protocol context may interfere with Kodi's ability to recognize and mount ISO files

5. **Why It Fails**:
   - ISO files need to be mounted as virtual disc drives, requiring filesystem-level access
   - HTTP mode's URL format (`http://127.0.0.1:57342/...`) may create a context where Kodi cannot properly initialize ISO mounting
   - Even though the final path is local, the HTTP request context may prevent successful mounting
   - Path substitution mode avoids this by using a path format that Kodi treats more like a local filesystem path from the start

## Code Flow Analysis

### Metadata Extraction

**Location**: `emby/metadata.py` - `load_MetaData()` function (lines 8-148)

When the webservice receives a request, it extracts the metadata from the URL path:

```python
# Line 64: Decode the base16-encoded metadata
Data[4] = bytes.fromhex(Data[4]).decode('utf-8')

# Lines 66-143: Parse the metadata
MetadataSubs = Data[4].split("<>")

for Index, MetadataSub in enumerate(MetadataSubs):
    MediaDatas = MetadataSub.split("<<")
    MediaSources.append([{}, [], [], []])
    
    for IndexSub, MediaData in enumerate(MediaDatas):
        if IndexSub == 0:
            MediaSourceInfos = MediaData.split(":")
            # ...
            elif MediaSourceInfoIndex == 3:
                MediaSources[Index][0]['Path'] = MediaSourceInfo.replace("<;>", ":")
```

The original path from the `.strm` file is extracted from the metadata and stored in `MediaSources[Index][0]['Path']`.

### ISO Detection in Webservice

**Location**: `hooks/webservice.py` - `GetRequest()` function

1. **Media Type Detection** (line 712):
   ```python
   if MetaData['MediaType'] == 'i':  # 'i' = ISO
   ```
   The media type is determined from the metadata. `'i'` indicates an ISO file.

2. **Path-based Detection** (line 753):
   ```python
   if MetaData['MediaSources'][MetaData['SelectionIndexMediaSource']][0]['Path'].lower().endswith(".iso"):
       LoadISO(MetaData, client)
   ```
   As a fallback, the plugin also checks if the path ends with `.iso`.

### LoadISO Function Details

**Location**: `hooks/webservice.py` (lines 474-489)

The `LoadISO()` function:
1. Extracts the original path from metadata
2. Converts Windows UNC paths (`\\server\share`) to `smb://` format
3. Calls `player.load_KodiItem()` to create a Kodi list item with the local path
4. Replaces the current playlist item with the new list item containing the local path
5. Sets delayed content to "blank" to prevent further webservice processing

**Key Point**: The function replaces the HTTP URL in Kodi's playlist with the actual local path, allowing Kodi to access the ISO file directly.

## Why Path Substitution Works

Path substitution mode works because:

1. **Path Format**: Even though `c22` contains the local path, the path format used during playback initialization (`/emby_addon_mode/...`) is treated more like a local filesystem path by Kodi
2. **Kodi's Path Substitution**: Kodi's native path substitution engine handles the translation internally, creating a context that's more compatible with filesystem operations
3. **ISO Mounting**: When the webservice replaces the playlist item with a local path (from `c22`), Kodi can successfully mount the ISO because:
   - The initial path format doesn't create an HTTP context that interferes with ISO mounting
   - The path substitution mechanism provides a filesystem-like context
   - The local path replacement happens in a context where Kodi can properly recognize and mount ISO files
   - Kodi's path substitution mechanism is more compatible with filesystem operations than HTTP URLs

## Why HTTP Mode Fails

HTTP mode fails because:

1. **URL Format Context**: Even though `c22` contains the local path, the HTTP URL format (`http://127.0.0.1:57342/...`) creates a network stream context that interferes with ISO mounting
2. **ISO Mounting Limitation**: Kodi's ISO mounting requires a filesystem context, not a network stream context:
   - ISO files need to be mounted as virtual disc drives
   - This requires filesystem-level operations, not HTTP stream operations
   - The HTTP request context may prevent Kodi from properly initializing the ISO mounting process
3. **Timing/Context Issues**: Even though `LoadISO()` replaces the playlist item with the local path from `c22`, Kodi may have already:
   - Established an HTTP stream context that cannot be converted to a filesystem context
   - Started processing the request in a way that's incompatible with ISO mounting
   - Encountered errors or locked the playback in HTTP mode before the replacement can take effect
4. **Protocol Context Mismatch**: HTTP creates a streaming protocol context, while ISO mounting requires a filesystem protocol context. Even though the final path is local, the HTTP context may prevent successful mounting.

## DVD and Blu-ray Containers

The plugin also handles DVD and Blu-ray disc structures:

**Location**: `core/common.py` (lines 247-257)

```python
if Container == 'dvd':
    Item['KodiPath'] += "/VIDEO_TS/"
    Item['KodiFilename'] = "VIDEO_TS.IFO"
    Item['KodiFullPath'] = f"{Item['KodiPath']}{Item['KodiFilename']}"
    return

if Container == 'bluray':
    Item['KodiPath'] += "/BDMV/"
    Item['KodiFilename'] = "index.bdmv"
    Item['KodiFullPath'] = f"{Item['KodiPath']}{Item['KodiFilename']}"
    return
```

For DVD and Blu-ray containers, the plugin constructs paths to the appropriate disc structure files (`VIDEO_TS.IFO` for DVD, `index.bdmv` for Blu-ray). These also require direct filesystem access and have the same limitations as ISO files.

## Workarounds and Solutions

### Current Solution

**Use Path Substitution Mode**: For `.strm` files containing ISO paths, users must use path substitution mode. This is the only mode that reliably works for ISO files.

### Alternative Solutions

1. **Use Direct Paths Mode**: If `useDirectPaths = True`, the plugin uses the original paths directly without going through the webservice. This would work for ISO files, but:
   - Requires the paths to be accessible from Kodi
   - Loses addon mode features (transcoding, subtitle management, etc.)

2. **Convert ISO to Regular Video**: Extract the video content from ISO files and store as regular video files (`.mkv`, `.mp4`, etc.). This eliminates the ISO mounting requirement.

3. **Use Network Shares**: Instead of local paths in `.strm` files, use network share paths (`smb://`, `nfs://`) which Kodi can mount directly.

## Code Locations Summary

- **STRM Processing**: `core/common.py` - `set_path_filename()` (lines 228-232)
- **ISO Detection**: `core/common.py` - `set_path_filename()` (lines 270-271)
- **Metadata Encoding**: `core/common.py` - `set_path_filename()` (lines 314-344)
- **Metadata Extraction**: `emby/metadata.py` - `load_MetaData()` (lines 8-148)
- **ISO Loading**: `hooks/webservice.py` - `LoadISO()` (lines 474-489)
- **ISO Detection in Webservice**: `hooks/webservice.py` - `GetRequest()` (lines 712, 753)
- **Kodi Item Loading**: `helper/player.py` - `load_KodiItem()` (lines 693-710)

## Troubleshooting

### ISO Files Not Playing in HTTP Mode

**Symptoms**: ISO files from `.strm` files fail to play in HTTP mode, but work in path substitution mode.

**Cause**: Even though `c22` contains the correct local path, HTTP mode creates a playback context (network stream) that interferes with Kodi's ISO mounting process. The HTTP URL format prevents Kodi from properly initializing filesystem-level operations needed to mount ISO files.

**Solution**: Switch to path substitution mode for items with ISO files. Path substitution mode creates a filesystem-like context that's compatible with ISO mounting.

### ISO Files Not Playing in Path Substitution Mode

**Possible Causes**:
1. Path in `.strm` file is not accessible from Kodi
2. Path format is incorrect (should be absolute path)
3. Network paths not properly formatted (should use `smb://` or `nfs://`)

**Solutions**:
1. Verify the path in the `.strm` file is correct and accessible
2. For network paths, ensure they use proper protocol (`smb://`, `nfs://`)
3. Check Kodi logs for path access errors

### DVD/Blu-ray Structure Files Not Found

**Symptoms**: DVD/Blu-ray content fails to play, errors about missing `VIDEO_TS.IFO` or `index.bdmv`.

**Cause**: The plugin constructs paths to disc structure files, but the actual files may not exist or be accessible.

**Solution**: Ensure the ISO file or disc structure is properly mounted and accessible at the path specified in the `.strm` file.

## Conclusion

`.strm` files containing ISO paths require special handling because:

1. **Database Storage**: The `c22` column stores the local path for ISO files regardless of webservice mode. This is correct and expected behavior.

2. **Playback Context**: The difference between HTTP and path substitution modes is not in the stored path, but in the playback context:
   - HTTP mode creates a network stream context that interferes with ISO mounting
   - Path substitution mode creates a filesystem-like context that allows ISO mounting

3. **ISO Mounting Requirements**: ISO files need filesystem-level access to mount as virtual discs. Even though the database contains the correct local path, the HTTP request context prevents Kodi from successfully mounting the ISO file.

4. **Solution**: Path substitution mode works around this by using Kodi's native path substitution feature, which creates a context that's more compatible with filesystem operations, allowing Kodi to successfully mount ISO files even when the playback goes through the webservice.

**Key Insight**: The issue is not with the stored path (which is correct in both modes), but with the playback request context. HTTP mode's URL format creates a context that's incompatible with ISO mounting, while path substitution mode's path format creates a compatible context.
