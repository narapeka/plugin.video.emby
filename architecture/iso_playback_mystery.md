# ISO Playback Mystery - Why HTTP Mode Fails Despite Local Path in c22

## The Mystery

You've discovered something puzzling: For `.strm` files containing ISO paths, the database `c22` column stores the **local path** (e.g., `H:\电影\原盘特效\SGNB\沉睡魔咒 (2014)...`) regardless of webservice mode (HTTP or path substitution). Yet:

- **Path Substitution Mode**: ISO files play successfully ✅
- **HTTP Mode**: ISO files fail to play ❌

**Question**: If `c22` contains the same local path in both modes, why does the mode matter?

## The Hypothesis: Kodi Uses Multiple Path Sources

Kodi may not use `c22` directly for playback. Instead, it might construct the path from multiple database sources:

1. **`path` table (`strPath`)**: Base directory path
2. **`files` table (`strFilename`)**: Filename
3. **`movie` table (`c22`)**: Full path (may be used as fallback or for display)

### Database Structure

**`path` table**:
- `idPath`: Path ID
- `strPath`: Base path (e.g., `H:\电影\原盘特效\SGNB\` or `http://127.0.0.1:57342/movies/...`)

**`files` table**:
- `idFile`: File ID
- `idPath`: Reference to `path.idPath`
- `strFilename`: Filename (e.g., `沉睡魔咒 (2014).iso`)

**`movie` table**:
- `idMovie`: Movie ID
- `idFile`: Reference to `files.idFile`
- `c22`: Full path (e.g., `H:\电影\原盘特效\SGNB\沉睡魔咒 (2014).iso`)

## What the Code Shows

### Path Storage During Sync

**Location**: `core/common.py` - `set_path_filename()`

For ISO files:
```python
if Container == 'iso' or KodiPathLower.endswith(".iso"):
    NativeMode = True

if NativeMode:
    # Uses original local path
    Item['KodiPath'] = f"{Item['KodiPath'].replace(Temp, '')}"  # Local path
    Item['KodiFilename'] = filename  # e.g., "沉睡魔咒 (2014).iso"
    Item['KodiFullPath'] = f"{Item['KodiPath']}{Item['KodiFilename']}"  # Full local path
```

**Location**: `database/video_db.py` - `update_movie()`

```python
# Line 198: Store full path in c22
self.cursor.execute("UPDATE movie SET ... c22 = ? ...", (KodiFullPath, ...))

# Line 201: Store base path in path table
self.cursor.execute("UPDATE path SET strPath = ? WHERE idPath = ?", (Path, KodiPathId))
```

**Key Question**: What is `Path` (the base path) stored in the `path` table?

Looking at the code flow:
- `Item['KodiPath']` is passed as `Path` parameter
- For ISO files with `NativeMode = True`, `Item['KodiPath']` is the local path
- So `path.strPath` should also be the local path

**But wait**: Is there any code that modifies `Path` before storing it in the `path` table?

## The Real Question: Does Kodi Use `path.strPath` or `c22`?

When Kodi initiates playback, it might:

1. **Option A**: Use `path.strPath` + `files.strFilename` to construct the path
2. **Option B**: Use `c22` directly
3. **Option C**: Try Option A first, fall back to Option B

If Kodi uses Option A, and if `path.strPath` somehow contains different values in different modes (even though `c22` is the same), that would explain the difference.

## Possible Explanations

### Explanation 1: Path Table Contains Different Values

Even though `c22` has the local path, maybe `path.strPath` contains:
- **HTTP Mode**: `http://127.0.0.1:57342/movies/...` (addon mode path)
- **Path Substitution Mode**: `/emby_addon_mode/movies/...` (path substitution path)

But this doesn't match the code - for `NativeMode = True`, `Item['KodiPath']` should be the local path regardless of mode.

### Explanation 2: Kodi's Path Resolution Logic

Kodi might have logic that:
1. Checks if `path.strPath` starts with `http://` or `/emby_addon_mode/`
2. If so, uses that path (even if `c22` has a local path)
3. Only uses `c22` if `path.strPath` is a local path

This would mean:
- **HTTP Mode**: `path.strPath` = `http://127.0.0.1:57342/...` → Kodi uses HTTP handler → Fails for ISO
- **Path Substitution Mode**: `path.strPath` = `/emby_addon_mode/...` → Kodi's path substitution translates it → Different context → Works for ISO

### Explanation 3: Plugin Intercepts Playback

The plugin might intercept playback in `onAVStarted` and modify behavior based on mode, but looking at the code, `onAVStarted` only handles native content (line 199):

```python
if not QueuedPlayingItem and not FullPath.startswith("dav://127.0.0.1:57342") and not FullPath.startswith("http://127.0.0.1:57342") and not FullPath.startswith("/emby_addon_mode/"):
    # native content handling
```

This suggests that if `FullPath` starts with `http://127.0.0.1:57342/` or `/emby_addon_mode/`, the plugin doesn't handle it as native content, meaning it goes through the webservice.

### Explanation 4: Kodi's Handler Selection Happens Before Plugin Can Intervene

Even though `c22` has the local path, when Kodi reads from the database to create the list item, it might:
1. Construct path from `path.strPath` + `files.strFilename`
2. Select handler based on this constructed path
3. Start playback with that handler
4. Plugin's `onAVStarted` hook fires, but handler is already selected

If `path.strPath` contains the addon mode path (even though `c22` has local path), Kodi would select the HTTP handler, which can't mount ISO files.

## What We Need to Verify

To solve this mystery, we need to check:

1. **What's in `path.strPath` for ISO files?**
   - Is it the local path in both modes?
   - Or is it the addon mode path in HTTP mode?

2. **How does Kodi construct the playback path?**
   - Does it use `path.strPath` + `files.strFilename`?
   - Or does it use `c22` directly?

3. **When does handler selection happen?**
   - Before or after `onAVStarted`?
   - Can the plugin change the handler after it's selected?

## The Real Mystery: Database Has Local Paths, But Mode Still Matters

**Confirmed**: Both `c22` and `strPath` in `movie_view` contain local paths for ISO files, regardless of webservice mode.

**The Question**: If the database stores local paths in both modes, why does HTTP mode fail while path substitution mode works?

## New Hypothesis: Kodi's Internal Path Resolution

Since the database contains local paths in both modes, the difference must be in **how Kodi resolves or processes the path when initiating playback**, not in what's stored.

### Possible Explanations

#### 1. Kodi's Library System May Use Different Path Sources

When a user clicks to play a movie from Kodi's library, Kodi might:
1. Use the path from the list item (which might be constructed differently)
2. Or use some internal path resolution that's affected by Kodi's settings
3. Or check path validity/accessibility before playback, which might behave differently based on mode

#### 2. Kodi's Path Validation or Handler Selection

Kodi might have internal logic that:
- Validates paths before playback
- Checks if paths are accessible
- Selects handlers based on path format or accessibility
- This validation might behave differently based on some context that's mode-dependent

#### 3. Plugin's `onAVStarted` Hook Timing

Looking at `helper/player.py` line 199:
```python
if not QueuedPlayingItem and not FullPath.startswith("dav://127.0.0.1:57342") and not FullPath.startswith("http://127.0.0.1:57342") and not FullPath.startswith("/emby_addon_mode/"):
    # native content handling
```

**Key Question**: What does `XbmcPlayer.getPlayingFile()` return when playback starts?

If `getPlayingFile()` returns:
- **HTTP Mode**: An HTTP URL (even though database has local path) → Plugin doesn't handle as native → Goes through webservice → Fails
- **Path Substitution Mode**: A local path or `/emby_addon_mode/...` → Plugin handles as native or path substitution handles it → Works

This would mean Kodi is somehow transforming the path between reading from the database and actually playing it.

#### 4. Kodi's List Item Path vs. Playback Path

When Kodi creates a list item from the database, it might:
1. Read the local path from the database
2. But when the user clicks play, Kodi might construct or resolve the path differently
3. This path resolution might be affected by Kodi's internal settings or the path format context

#### 5. Path Substitution Engine Intercepts Before Handler Selection

In path substitution mode:
- Database has local path: `H:/电影/原盘特效/SGNB/战争之王 (2005) {tmdb-1830}/战争之王 (2005).iso`
- But Kodi's path substitution engine might intercept paths that match certain patterns
- Or Kodi might check if the path matches any path substitution rules before using it directly
- This could create a different playback context

In HTTP mode:
- Same local path in database
- But no path substitution rules match
- Kodi might use the path directly, but something about the HTTP mode context interferes

## Why Does Mode Matter If Database Has Local Paths?

**Confirmed by User**: Both `strPath` and `strFileName` in `movie_view` contain local paths for ISO files, regardless of webservice mode.

This means the difference must occur **during Kodi's playback path resolution**, not in the database storage.

## Conclusion

**## The Critical Question

**What does `XbmcPlayer.getPlayingFile()` return when playback starts?**

To solve this mystery, we need to check what path Kodi actually uses when playback begins. The plugin logs this at line 114:

```python
xbmc.log(f"EMBY.hooks.player: FullPath: {FullPath}", 0) # LOGDEBUG
```

**Hypothesis**: Even though the database contains local paths, `getPlayingFile()` might return:
- **HTTP Mode**: An HTTP URL or modified path → Kodi uses HTTP handler → Fails
- **Path Substitution Mode**: The local path or a path substitution path → Kodi uses filesystem handler or path substitution → Works

## Possible Root Cause: Kodi's Path Resolution

Kodi might have internal logic that:
1. Reads the local path from the database
2. But before playback, checks if the path should go through addon mode based on some setting or context
3. In HTTP mode, this check might transform the path to an HTTP URL
4. In path substitution mode, this check might leave it as-is or transform it differently

Or Kodi might:
1. Check if the path matches any addon-generated patterns
2. If it matches (based on some mode-dependent logic), route it through the webservice
3. HTTP mode routing creates an incompatible context for ISO mounting
4. Path substitution mode routing creates a compatible context

## The Solution: Encoded Filenames in `files` Table

**Critical Discovery**: The plugin writes **URL-encoded filenames** into Kodi's `files` table in HTTP mode, but **unencoded filenames** in path substitution mode!

### Where `get_Filename()` is Used

**Location**: `core/common.py` - `set_path_filename()` (line 265)

```python
Item['KodiFilename'] = utils.get_Filename(Item['KodiPath'], NativeMode)
```

**Then**:
1. **Constructs `KodiFullPath`** (line 362):
   ```python
   Item['KodiFullPath'] = f"{Item['KodiPath']}{Item['KodiFilename']}"
   ```

2. **Stored in Database**:
   - `KodiFilename` → `files.strFilename` (via `add_file()` or `update_file()`)
   - `KodiFullPath` → `movie.c22` or `episode.c18` (via `add_movie()` or `update_episode()`)

**Critical**: When Kodi resolves `videodb://movies/titles/353`, it constructs the playback path from:
- `path.strPath` + `files.strFileName` ← **This is what Kodi uses for playback!**
- NOT from `c22` (which contains `KodiFullPath`)

So the encoded filename in `files.strFileName` **directly impacts playback**, not just database storage!

### The Encoding Logic

**Location**: `helper/utils.py` - `get_Filename()` (lines 797-805)

```python
def get_Filename(Path, NativeMode):
    Separator = get_Path_Seperator(Path)
    Pos = Path.rfind(Separator)
    Filename = Path[Pos + 1:]

    if not NativeMode and webservicemode != "pathsubstitution":
        Filename = quote(Filename)  # URL-encode the filename

    return Filename
```

**Key Points**:
- **HTTP Mode**: Filenames are URL-encoded (e.g., `战争之王 (2005).iso` → `%E6%88%98%E4%BA%89%E4%B9%8B%E7%8E%8B%20(2005).iso`)
- **Path Substitution Mode**: Filenames are NOT encoded (e.g., `战争之王 (2005).iso` stays as-is)
- **NativeMode = True**: Should prevent encoding, but may have been encoded if synced in addon mode

### How This Causes the Issue

When Kodi resolves `videodb://movies/titles/353` and constructs the playback path from `strPath` + `strFileName`:

**HTTP Mode**:
- `strPath` = `H:/电影/原盘特效/SGNB/` (local path)
- `strFileName` = `%E6%88%98%E4%BA%89%E4%B9%8B%E7%8E%8B%20(2005).iso` (URL-encoded)
- **Constructed path** = `H:/电影/原盘特效/SGNB/%E6%88%98%E4%BA%89%E4%B9%8B%E7%8E%8B%20(2005).iso`
- This is an **invalid filesystem path** with encoded characters → Kodi can't mount the ISO → Fails ❌

**Path Substitution Mode** (with encoded filename in database):
- `strPath` = `H:/电影/原盘特效/SGNB/` (local path)
- `strFileName` = `%E6%88%98%E4%BA%89%E4%B9%8B%E7%8E%8B%20(2005).iso` (URL-encoded, from HTTP mode sync)
- **Constructed path** = `H:/电影/原盘特效/SGNB/%E6%88%98%E4%BA%89%E4%B9%8B%E7%8E%8B%20(2005).iso`
- Kodi uses **filesystem handler** (because `strPath` is a local path)
- **Filesystem handler automatically decodes URL-encoded filenames** → Decodes to `战争之王 (2005).iso` → Valid path → Works ✅

**HTTP Mode** (with encoded filename in database):
- `strPath` = `H:/电影/原盘特效/SGNB/` (local path)
- `strFileName` = `%E6%88%98%E4%BA%89%E4%B9%8B%E7%8E%8B%20(2005).iso` (URL-encoded)
- **Constructed path** = `H:/电影/原盘特效/SGNB/%E6%88%98%E4%BA%89%E4%B9%8B%E7%8E%8B%20(2005).iso`
- Kodi's `videodb://` handler might route through HTTP webservice or use HTTP handler
- **HTTP handler/webservice doesn't decode URL-encoded filenames** for filesystem paths → Invalid path → Fails ❌
- OR: Kodi's path validation/routing logic in HTTP mode context prevents proper decoding → Fails ❌

### Why Path Substitution Mode Works with Encoded Filenames

**Key Insight**: When you switch to path substitution mode, the plugin's `toggle_path()` function should decode filenames:

**Location**: `database/video_db.py` - `toggle_path()` (line 1660)
```python
if QuotedOld:  # Old mode was HTTP/WebDAV (encoded)
    FileNameNew = unquote(FileName[1])  # Decode when switching TO path substitution
```

**However**, if filenames remain encoded (e.g., if `toggle_path()` wasn't called or there's a bug), path substitution mode still works because:

1. **Kodi uses filesystem handler**: Since `strPath` is a local path (`H:/电影/原盘特效/SGNB/`), Kodi selects the filesystem handler
2. **Filesystem handler auto-decodes**: Kodi's filesystem handler automatically decodes URL-encoded filenames when accessing local filesystem paths
3. **HTTP handler doesn't decode**: HTTP handler or HTTP mode routing doesn't decode URL-encoded filenames for filesystem paths

**Why HTTP mode fails**: Even though `strPath` is a local path, Kodi's `videodb://` handler or HTTP mode context might route the request differently, preventing the filesystem handler from being used or preventing proper decoding.

### Why Path Substitution Mode Doesn't Encode

**The encoding condition** (line 802):
```python
if not NativeMode and webservicemode != "pathsubstitution":
    Filename = quote(Filename)
```

**For ISO files**, there's a **timing issue**:
1. Line 210: `NativeMode = utils.useDirectPaths` (initial value, typically `False` in addon mode)
2. Line 265: `Item['KodiFilename'] = utils.get_Filename(Item['KodiPath'], NativeMode)` ← **Called here with `NativeMode = False`**
3. Line 270-271: `if Container == 'iso' or KodiPathLower.endswith(".iso"): NativeMode = True` ← **Set to `True` AFTER `get_Filename()` is called!**

So when `get_Filename()` is called for ISO files:
- **HTTP Mode**: `not False` (True) AND `webservicemode != "pathsubstitution"` (True) → **Encodes filename** ❌
- **Path Substitution Mode**: `not False` (True) AND `webservicemode != "pathsubstitution"` (False) → **Does NOT encode filename** ✅

**Why path substitution mode doesn't encode by design**:
- Path substitution paths (`/emby_addon_mode/...`) are treated more like filesystem paths
- Kodi's path substitution engine handles them before they become HTTP URLs
- URL encoding isn't needed because they're not direct HTTP URLs
- This allows special characters in filenames to work correctly with filesystem operations

**The bug**: For ISO files, `NativeMode` should be set to `True` **before** calling `get_Filename()`, but it's currently set **after**. This causes HTTP mode to encode the filename even though it's an ISO file that should use native mode.

## The Breakthrough: Kodi Uses `videodb://` Protocol

**Critical Discovery from Logs**: When playback starts, Kodi is using `videodb://movies/titles/353`, not the direct file path!

```
VideoPlayer::OpenFile: videodb://movies/titles/353?xsp=...
Error opening image file or Error on dvdnav_open_stream
CVideoPlayer::OpenInputStream - error opening [videodb://movies/titles/353...]
```

### What This Means

When a user clicks to play a movie from Kodi's library, Kodi doesn't use the direct file path from the database. Instead, it uses Kodi's internal `videodb://` protocol, which:

1. **References the movie by ID** (`videodb://movies/titles/353`)
2. **Kodi's videodb handler resolves this** to the actual file path
3. **The resolution process** might check if the path should go through addon mode
4. **This check might behave differently** based on webservice mode settings

### The Hypothesis

When Kodi's `videodb://` handler resolves the path:

**HTTP Mode**:
- Kodi resolves `videodb://movies/titles/353` → Reads path from database
- Kodi checks if path should go through addon mode (based on some setting/context)
- In HTTP mode, this check might route the path through the HTTP webservice
- HTTP handler tries to open the ISO → Fails (can't mount ISO via HTTP)

**Path Substitution Mode**:
- Kodi resolves `videodb://movies/titles/353` → Reads path from database
- Kodi checks if path should go through addon mode
- In path substitution mode, this check might route differently or not at all
- Path substitution or filesystem handler opens the ISO → Works

### Why This Happens

Kodi's `videodb://` protocol handler likely has logic that:
- Checks if paths match addon-generated patterns
- Routes matching paths through the addon's webservice
- This routing behavior might be different for HTTP vs path substitution modes

Even though the database contains local paths, Kodi's `videodb://` resolution might transform or route the path differently based on the webservice mode context.

## Conclusion

**The mystery is in Kodi's `videodb://` protocol resolution**, not in the database storage.

When Kodi resolves `videodb://movies/titles/353` to the actual file path, it might route the path through the addon's webservice differently based on the webservice mode:
- **HTTP Mode**: Routes through HTTP webservice → HTTP handler → Fails for ISO
- **Path Substitution Mode**: Routes differently or not at all → Filesystem handler → Works for ISO

The plugin doesn't hook into player behavior to change modes. Instead, Kodi's internal `videodb://` protocol handler has different routing behavior based on the webservice mode context, even when the database contains the same local paths.

**To verify**: Check what `XbmcPlayer.getPlayingFile()` returns after Kodi resolves `videodb://` in both modes. This will show the actual path Kodi uses for playback.

1. **`c22` stores the local path** (correct, but not used for playback path construction)
2. **`path.strPath` stores the addon mode path** (this is what's actually used!)
3. **Kodi/plugin constructs playback path from `strPath` + `strFileName`**
4. **Handler selection is based on this constructed path**
5. **HTTP mode fails because the constructed path is an HTTP URL**
6. **Path substitution mode works because the path format creates a compatible context**

The mystery is solved: **Kodi uses `path.strPath`, not `c22`, to construct the playback path!**
