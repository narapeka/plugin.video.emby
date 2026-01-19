# Emby for Kodi Next Gen - Architecture Documentation

## Overview

Emby for Kodi Next Gen is a Kodi service plugin that synchronizes media libraries from Emby Server to Kodi's native database, enabling seamless media playback and management. The plugin acts as a bridge between Emby Server's centralized media management and Kodi's powerful playback engine.

## System Architecture

### High-Level Architecture

```
┌─────────────────┐
│   Emby Server   │
│  (Remote API)   │
└────────┬────────┘
         │ HTTP/WebSocket
         │
┌────────▼─────────────────────────────────────────┐
│         Emby for Kodi Plugin                      │
│  ┌──────────────────────────────────────────┐   │
│  │  Service Layer (service.py)              │   │
│  │  - Entry point                           │   │
│  │  - Event routing                         │   │
│  └──────────────────────────────────────────┘   │
│                                                   │
│  ┌──────────────┐  ┌──────────────┐             │
│  │   Monitor    │  │  WebService  │             │
│  │  (Events)    │  │  (Local API) │             │
│  └──────────────┘  └──────────────┘             │
│                                                   │
│  ┌──────────────┐  ┌──────────────┐             │
│  │  WebSocket   │  │   Library    │             │
│  │  (Realtime)  │  │  (Sync)      │             │
│  └──────────────┘  └──────────────┘             │
│                                                   │
│  ┌──────────────────────────────────────────┐   │
│  │  Database Layer                          │   │
│  │  - Emby DB (mapping)                     │   │
│  │  - Kodi Video/Music DB                   │   │
│  └──────────────────────────────────────────┘   │
└───────────────────────────────────────────────────┘
         │
         │ Native Integration
         │
┌────────▼────────┐
│  Kodi Core      │
│  - Library      │
│  - Player       │
│  - UI           │
└─────────────────┘
```

## Core Components

### 1. Service Layer (`service.py`)

**Purpose**: Main entry point and event router

**Responsibilities**:
- Plugin initialization
- Event routing to webservice
- Context menu actions (record, favorites, multiversion, etc.)

**Key Functions**:
- No parameters: Starts webservice and monitor
- With parameters: Routes events via local socket to webservice

### 2. Monitor System (`hooks/monitor.py`)

**Purpose**: Kodi event monitoring and system lifecycle management

**Key Features**:
- Monitors Kodi player events (play, stop, pause, seek, etc.)
- Handles system events (sleep, wake, quit)
- Manages library scan/clean events
- Settings change detection
- Coordinates server connections

**Event Handling**:
- `Player.OnPlay`, `Player.OnStop`, `Player.OnPause`, `Player.OnSeek`
- `VideoLibrary.OnUpdate`, `VideoLibrary.OnRemove`
- `System.OnSleep`, `System.OnWake`, `System.OnQuit`
- Custom notifications for plugin operations

### 3. WebService (`hooks/webservice.py`)

**Purpose**: Local HTTP/WebDAV server for media streaming

**Architecture**:
- Listens on `127.0.0.1:57342`
- Multi-threaded worker pool (configurable, default 10 workers)
- Handles GET requests for media files
- Redirects to Emby Server API endpoints

**Key Functions**:
- `start()`: Initializes socket and worker threads
- `GetRequest()`: Processes media requests
- `LoadData()`: Handles transcoding decisions
- `send_redirect()`: Redirects to Emby API

**Request Flow**:
1. Kodi requests: `http://127.0.0.1:57342/movies/serverid/.../filename`
2. WebService parses request, extracts Emby item ID
3. Makes transcoding decisions
4. Redirects to: `http://emby-server:8096/emby/videos/itemid/stream?...`

### 4. WebSocket Client (`hooks/websocket.py`)

**Purpose**: Real-time bidirectional communication with Emby Server

**Features**:
- Receives real-time library updates
- Handles remote control commands
- Processes server notifications
- Manages playback session synchronization

**Message Types**:
- `LibraryChanged`: Content added/updated/removed
- `UserDataChanged`: Playback progress, watched status
- `GeneralCommand`: Remote control commands
- `PlaybackStart`, `PlaybackStop`, `PlaybackProgress`

### 5. Emby Server Client (`emby/emby.py`)

**Purpose**: Manages connection and communication with Emby Server

**Components**:
- `HTTP` (`emby/http.py`): Low-level HTTP communication
- `API` (`emby/api.py`): High-level API wrapper
- `Views` (`emby/views.py`): Library views and nodes management

**Key Responsibilities**:
- Server authentication and session management
- API request handling
- Library view synchronization
- Node creation and updates

### 6. Library Synchronization (`database/library.py`)

**Purpose**: Synchronizes Emby library content to Kodi database

**Sync Modes**:
- **Initial Sync**: Full library sync on first connection
- **Incremental Sync**: Only changed items since last sync
- **Realtime Sync**: Immediate updates via WebSocket

**Sync Process**:
1. Query Emby Server for library items
2. Transform Emby metadata to Kodi format
3. Insert/update Kodi database
4. Update Emby mapping database
5. Refresh Kodi library views

### 7. Core Content Handlers (`core/`)

**Purpose**: Type-specific content processing

**Content Types**:
- `movies.py`: Movie metadata and processing
- `series.py`, `season.py`, `episode.py`: TV show hierarchy
- `audio.py`, `musicalbum.py`, `musicartist.py`: Music content
- `musicvideo.py`: Music video content
- `boxsets.py`: Movie collections
- `genre.py`, `musicgenre.py`: Genre organization
- `person.py`: Actor/director information
- `studio.py`: Studio information
- `tag.py`: Custom tags
- `playlist.py`: Playlist management
- `folder.py`: Folder views
- `videos.py`: Generic video content
- `common.py`: Shared utilities and path handling

**Common Pattern**:
Each handler implements:
- `change()`: Process item add/update
- `remove()`: Handle item deletion
- Metadata transformation from Emby to Kodi format

### 8. Database Layer (`database/`)

**Purpose**: Database abstraction and management

**Databases**:
- **Emby DB** (`emby_db.py`): Maps Emby IDs to Kodi IDs, stores sync state
- **Video DB** (`video_db.py`): Kodi video library operations
- **Music DB** (`music_db.py`): Kodi music library operations
- **Texture DB** (`texture_db.py`): Artwork management
- **Addon DB** (`addon_db.py`): Plugin-specific data
- **Common DB** (`common_db.py`): Shared database utilities

**Database I/O** (`dbio.py`):
- Manages read-only (RO) and read-write (RW) connections
- Thread-safe connection pooling
- Automatic connection management
- Database vacuum and maintenance

### 9. Player System (`helper/player.py`, `helper/playerops.py`)

**Purpose**: Media playback management and progress tracking

**Features**:
- Playback session initialization
- Progress tracking and reporting to Emby
- Remote playback support
- Watch together functionality
- Skip intro/credits support
- Multiversion content selection

**Player Events**:
- Tracks playback position
- Reports to Emby Server
- Handles pause/resume/seek
- Manages subtitle selection

### 10. Helper Utilities (`helper/`)

**Key Modules**:
- `utils.py`: Global utilities, settings management, file operations
- `pluginmenu.py`: Plugin menu and navigation
- `context.py`: Context menu actions
- `queue.py`: Thread-safe queue implementation
- `backup.py`: Database backup/restore
- `artworkcache.py`: Artwork caching system
- `xmls.py`: Kodi XML configuration management
- `deduplicate.py`: Content deduplication

## Data Flow

### 1. Initial Synchronization Flow

```
Emby Server
    │
    ├─► HTTP API Request (Library Items)
    │
    ▼
EmbyServer.API.get_Items()
    │
    ├─► Transform Emby Metadata
    │
    ▼
Core Content Handler (e.g., movies.py)
    │
    ├─► Convert to Kodi Format
    │
    ▼
Database Layer
    │
    ├─► Insert into Kodi Video/Music DB
    ├─► Update Emby Mapping DB
    │
    ▼
Kodi Library Refresh
```

### 2. Playback Flow

```
Kodi Player Request
    │
    ├─► Path: http://127.0.0.1:57342/movies/.../filename
    │
    ▼
WebService.GetRequest()
    │
    ├─► Parse Path → Extract Emby Item ID
    ├─► Load Metadata from Emby DB
    ├─► Check Transcoding Requirements
    │
    ▼
LoadData() / send_redirect()
    │
    ├─► Build Emby API URL
    │   http://emby-server/emby/videos/itemid/stream?...
    │
    ▼
HTTP 307 Redirect to Emby Server
    │
    ▼
Kodi Player → Emby Server Stream
```

### 3. Real-time Update Flow

```
Emby Server Event
    │
    ├─► WebSocket Message
    │   (LibraryChanged, UserDataChanged, etc.)
    │
    ▼
WebSocket.Message()
    │
    ├─► Parse Event Type
    │
    ▼
Library Sync Handler
    │
    ├─► Process Add/Update/Remove
    │
    ▼
Core Content Handler
    │
    ├─► Update Kodi Database
    │
    ▼
Kodi Library Refresh (if needed)
```

### 4. Progress Update Flow

```
Kodi Player Event
    │
    ├─► Monitor.onNotification()
    │   (Player.OnPlay, Player.OnSeek, etc.)
    │
    ▼
Player.PlayerEventsQueue
    │
    ├─► PlayerCommands() Thread
    │
    ▼
playerops.Pause() / Seek() / etc.
    │
    ├─► Update Local State
    ├─► Report to Emby Server
    │
    ▼
EmbyServer.API.report_PlaybackProgress()
```

## Key Processes

### 1. Startup Process

1. **Service Initialization** (`service.py`)
   - Check for parameters (context menu actions)
   - If no parameters: Start webservice and monitor

2. **WebService Startup** (`hooks/webservice.py`)
   - Bind to `127.0.0.1:57342`
   - Initialize worker thread pool
   - Start listener thread

3. **Monitor Startup** (`hooks/monitor.py`)
   - Run setup wizard (first run)
   - Initialize Kodi Monitor
   - Start server connection threads

4. **Server Connection** (`emby/emby.py`)
   - Load server settings
   - Authenticate with Emby Server
   - Initialize WebSocket connection
   - Start library synchronization

5. **Library Sync** (`database/library.py`)
   - Load library settings
   - Initialize databases
   - Start initial or incremental sync

### 2. Synchronization Process

**Initial Sync**:
1. Query all libraries from Emby Server
2. For each library:
   - Query all items (paginated)
   - Process each item type
   - Insert into Kodi database
   - Update Emby mapping
3. Refresh Kodi library views

**Incremental Sync**:
1. Query Emby Server for items changed since last sync
2. Process only changed items
3. Update Kodi database
4. Update sync timestamp

**Realtime Sync**:
1. Receive WebSocket event
2. Process immediately (add/update/remove)
3. Update Kodi database
4. Refresh affected views

### 3. Playback Process

1. **Playback Initiation**:
   - User selects media in Kodi
   - Kodi requests file from local webservice
   - WebService identifies Emby item
   - Loads metadata and media sources

2. **Transcoding Decision**:
   - Check codec compatibility
   - Check bitrate limits
   - Check resolution limits
   - Determine if transcoding needed

3. **Stream Setup**:
   - If direct play: Redirect to Emby stream URL
   - If transcoding: Redirect to Emby transcoding URL
   - Initialize playback session with Emby

4. **Playback Monitoring**:
   - Track playback position
   - Report progress to Emby Server
   - Handle pause/resume/seek
   - Update watched status

### 4. Path Handling Process

**Direct Paths Mode** (`useDirectPaths = True`):
- Uses original file paths from Emby Server
- Kodi accesses files directly (SMB, NFS, local)
- No webservice routing
- Better performance for local/network shares

**Addon Mode** (`useDirectPaths = False`):
- Constructs virtual paths using `AddonModePath`
- Routes through local webservice
- WebService redirects to Emby API
- Supports transcoding and remote access

**Path Construction** (`core/common.py`):
- Extracts filename from Emby path
- Encodes metadata in folder structure
- Creates Kodi-compatible paths
- Handles special characters and URL encoding

## Database Architecture

### Emby Mapping Database

**Purpose**: Maps Emby Server items to Kodi database entries

**Key Tables**:
- `Items`: Emby ID ↔ Kodi ID mapping
- `MediaSources`: Media source information
- `VideoStreams`, `AudioStreams`, `Subtitles`: Stream metadata
- `Libraries`: Library configuration
- `Sync`: Sync state and timestamps

### Kodi Database Integration

**Video Library**:
- Movies, TV Shows, Episodes, Music Videos
- Artwork, metadata, cast information
- Playback progress and watched status

**Music Library**:
- Artists, Albums, Songs
- Artwork and metadata
- Playback history

**Texture Database**:
- Cached artwork URLs
- Image thumbnails

## Communication Mechanisms

### 1. HTTP Communication (`emby/http.py`)

**Features**:
- Low-level socket-based HTTP
- Connection pooling and reuse
- Keep-alive support
- SSL/TLS support
- Chunked transfer encoding
- Request/response queuing

**Request Types**:
- GET: Retrieve items, metadata, images
- POST: Playback info, session management
- DELETE: Remove items
- HEAD: Check availability

### 2. WebSocket Communication (`hooks/websocket.py`)

**Purpose**: Real-time bidirectional communication

**Connection Management**:
- Auto-reconnect on disconnect
- Ping/pong keepalive
- Message queue for reliability

**Message Handling**:
- Library change notifications
- User data updates
- Remote control commands
- Playback session events

### 3. Local WebService (`hooks/webservice.py`)

**Protocols Supported**:
- HTTP: `http://127.0.0.1:57342/`
- WebDAV: `dav://127.0.0.1:57342/` (limited support)
- Path Substitution: `/emby_addon_mode/`

**Request Processing**:
- Multi-threaded worker pool
- Request parsing and routing
- Metadata loading
- Redirect generation

## File Structure

```
plugin.video.emby/
├── service.py              # Main entry point
├── addon.xml              # Plugin manifest
│
├── core/                  # Content type handlers
│   ├── common.py         # Shared utilities
│   ├── movies.py         # Movie processing
│   ├── series.py         # TV show processing
│   ├── episode.py        # Episode processing
│   ├── audio.py          # Audio processing
│   └── ...               # Other content types
│
├── database/             # Database layer
│   ├── dbio.py          # Database I/O management
│   ├── emby_db.py       # Emby mapping database
│   ├── video_db.py      # Kodi video database
│   ├── music_db.py      # Kodi music database
│   ├── library.py       # Library synchronization
│   └── ...
│
├── emby/                 # Emby Server client
│   ├── emby.py          # Server connection
│   ├── http.py          # HTTP communication
│   ├── api.py           # API wrapper
│   ├── views.py         # Library views
│   └── metadata.py      # Metadata processing
│
├── hooks/                # Event hooks
│   ├── monitor.py       # Kodi event monitor
│   ├── webservice.py    # Local HTTP server
│   ├── websocket.py     # WebSocket client
│   └── favorites.py     # Favorites sync
│
├── helper/               # Utility modules
│   ├── utils.py         # Global utilities
│   ├── player.py        # Player management
│   ├── playerops.py     # Player operations
│   ├── pluginmenu.py    # Plugin menu
│   └── ...
│
├── dialogs/              # UI dialogs
│   ├── loginconnect.py  # Emby Connect login
│   ├── serverconnect.py # Server connection
│   └── ...
│
└── resources/            # Resources
    ├── settings.xml     # Settings definition
    ├── language/        # Translations
    └── skins/           # UI resources
```

## Key Design Patterns

### 1. Worker Thread Pattern
- Multi-threaded processing for sync operations
- Thread-safe database access
- Queue-based task distribution

### 2. Event-Driven Architecture
- Kodi events → Monitor → Processing
- WebSocket events → Real-time updates
- Player events → Progress tracking

### 3. Proxy/Redirect Pattern
- Local webservice acts as proxy
- Redirects to actual Emby API endpoints
- Enables transcoding and special features

### 4. Database Mapping Pattern
- Emby DB maintains ID mappings
- Kodi DB stores actual content
- Bidirectional lookup support

### 5. Content Handler Pattern
- Each content type has dedicated handler
- Common interface (change, remove)
- Shared utilities in common.py

## Configuration and Settings

### Settings Categories

1. **Connection Settings**:
   - Server addresses (local/remote)
   - Authentication
   - User selection

2. **Sync Settings**:
   - Library selection
   - Content type filters
   - Sync behavior

3. **Playback Settings**:
   - Direct paths vs Addon mode
   - Webservice mode (HTTP/WebDAV/Path Substitution)
   - Transcoding preferences

4. **Advanced Settings**:
   - Metadata extraction
   - Artwork caching
   - Performance tuning

### Configuration Files

- `sources.xml`: Kodi media sources
- `advancedsettings.xml`: Kodi advanced settings
- Server settings: JSON files in addon data directory

## Threading Model

### Thread Types

1. **Main Thread**: Service initialization and monitoring
2. **Worker Threads**: Sync operations, content processing
3. **WebService Workers**: HTTP request handling
4. **WebSocket Thread**: Real-time message processing
5. **Player Thread**: Playback event processing

### Thread Safety

- Database connections: Thread-local or locked
- Global state: Protected by locks
- Queue-based communication between threads

## Error Handling and Recovery

### Connection Recovery
- Automatic reconnection on server disconnect
- Exponential backoff for retries
- Graceful degradation on errors

### Database Recovery
- Transaction-based operations
- Rollback on errors
- Database integrity checks
- Backup/restore functionality

### Sync Recovery
- Resume from last sync timestamp
- Handle partial syncs
- Conflict resolution

## Performance Optimizations

1. **Incremental Sync**: Only sync changed items
2. **Pagination**: Process large libraries in chunks
3. **Caching**: Query cache for dynamic nodes
4. **Connection Pooling**: Reuse HTTP connections
5. **Database Indexing**: Optimized queries
6. **Lazy Loading**: Load metadata on demand
7. **Thread Pooling**: Reuse worker threads

## Security Considerations

1. **Authentication**: Token-based with Emby Server
2. **Local WebService**: Only accessible from localhost
3. **SSL/TLS**: Support for encrypted connections
4. **Credential Storage**: Secure storage in Kodi settings

## Extension Points

1. **Content Handlers**: Add new content types in `core/`
2. **Database Operations**: Extend database classes
3. **Player Features**: Extend player operations
4. **Context Menu**: Add custom actions
5. **Nodes**: Create custom library nodes

## Dependencies

- **Kodi**: Python 3.x, Kodi API
- **External Libraries**:
  - `dateutil`: Date parsing
  - `PIL` (optional): Image processing
- **Kodi Databases**: Video, Music, Texture, EPG, TV

## Version History

- **12.1.0**: WebDAV support introduced (default)
- **12.3.5**: HTTP mode set as default
- **12.3.8**: Current version

---

*This architecture document provides a high-level overview of the Emby for Kodi Next Gen plugin. For implementation details, refer to the source code and inline documentation.*
