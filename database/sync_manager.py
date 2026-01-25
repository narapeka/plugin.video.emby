"""
SyncManager - Central sync coordinator for Emby plugin.

This class provides a single entry point for ALL sync operations:
- Database-backed persistent queues (survives restart)
- Debouncing (2s quiet period before processing)
- Deduplication (same item in queue = merge)
- Widget refresh cascade prevention
- Sequential processing (remove → update → library → userdata)
- Echo prevention (Kodi→Emby→Kodi loops)

Architecture:
    All event sources → SyncManager.queue_xxx() → Database Queue
    → Debounce Timer (2s) → _process_queue() → Workers → Single Widget Refresh
"""
import threading
import xbmc
from helper import utils


class SyncState:
    """Sync state enum"""
    IDLE = "idle"
    SYNCING = "syncing"
    STARTUP_SYNC = "startup_sync"
    PAUSED = "paused"


class SyncManager:
    """
    Central sync coordinator for one Emby server.

    Guarantees:
    - Single entry point for all sync operations
    - Database-backed queue (survives restart)
    - Debouncing (2s quiet period)
    - No widget refresh cascade
    - Sequential processing (remove → update → library → userdata)
    - Single widget refresh at end
    """

    def __init__(self, emby_server):
        """
        Initialize SyncManager for an Emby server.

        Args:
            emby_server: EmbyServer instance this manager coordinates sync for
        """
        xbmc.log(f"EMBY.database.sync_manager: -->[ SyncManager init for server {emby_server.ServerData['ServerId']} ]", 1)  # LOGINFO
        self.emby_server = emby_server
        self.server_id = emby_server.ServerData['ServerId']

        # State management
        self.state = SyncState.IDLE
        self.sync_lock = threading.Lock()
        self._shutdown = False

        # Debouncing
        self.debounce_timer = None
        self.debounce_lock = threading.Lock()
        self.debounce_seconds = 2  # Wait 2 seconds after last event before processing

        # Widget refresh control - prevents cascade
        self.widget_refresh_needed = {"video": False, "music": False}
        self.plugin_scan_active = {"video": False, "music": False}

        # Echo prevention - items to skip when received back from WebSocket
        self.items_skip_update = set()
        self.items_skip_update_lock = threading.Lock()

        # Processing flags
        self._processing_music_content = False

        xbmc.log(f"EMBY.database.sync_manager: --<[ SyncManager init complete for server {self.server_id} ]", 1)  # LOGINFO

    # ═══════════════════════════════════════════════════════════════════════════
    # PUBLIC API - Queue Methods
    # All sync requests should come through these methods
    # ═══════════════════════════════════════════════════════════════════════════

    def queue_removal(self, item_id, library_id=""):
        """
        Queue an item for removal from Kodi.

        Called by:
        - WebSocket LibraryChanged (ItemsRemoved)
        - KodiStartSync (get_sync_queue)

        Args:
            item_id: Emby item ID to remove
            library_id: Optional library ID for partial removal
        """
        if self._shutdown:
            return

        xbmc.log(f"EMBY.database.sync_manager: queue_removal: {item_id}, library: {library_id}", 0)  # LOGDEBUG

        from . import dbio
        SQLs = self._open_db_rw("queue_removal")
        SQLs["emby"].add_RemoveItem(item_id, library_id)
        self._close_db_rw("queue_removal", SQLs)

        self._schedule_processing()

    def queue_update(self, item_id, item_type, library_id):
        """
        Queue an item for update in Kodi.

        Called by:
        - WebSocket LibraryChanged (ItemsUpdated, ItemsAdded)
        - KodiStartSync (MinDateLastSaved query)

        Args:
            item_id: Emby item ID to update
            item_type: Emby item type (Movie, Episode, etc.) or "unknown"
            library_id: Library ID the item belongs to
        """
        if self._shutdown:
            return

        xbmc.log(f"EMBY.database.sync_manager: queue_update: {item_id}, type: {item_type}, library: {library_id}", 0)  # LOGDEBUG

        from . import dbio
        SQLs = self._open_db_rw("queue_update")
        SQLs["emby"].add_UpdateItem(item_id, item_type or "unknown", library_id or "unknown")
        self._close_db_rw("queue_update", SQLs)

        self._schedule_processing()

    def queue_userdata(self, item_id, userdata_dict):
        """
        Queue userdata update for an item.

        Called by:
        - WebSocket UserDataChanged
        - KodiStartSync (MinDateLastSavedForUser query)

        Args:
            item_id: Emby item ID
            userdata_dict: Dict with userdata fields:
                - Type, PlaybackPositionTicks, PlayCount, IsFavorite,
                - Played, LastPlayedDate, PlayedPercentage, UnplayedItemCount
        """
        if self._shutdown:
            return

        # Check if we should skip this (echo prevention)
        if self.should_skip_userdata(str(item_id)):
            xbmc.log(f"EMBY.database.sync_manager: queue_userdata: SKIP (echo) {item_id}", 0)  # LOGDEBUG
            return

        xbmc.log(f"EMBY.database.sync_manager: queue_userdata: {item_id}", 0)  # LOGDEBUG

        from . import dbio
        SQLs = self._open_db_rw("queue_userdata")
        SQLs["emby"].add_Userdata(
            item_id,
            userdata_dict.get('Type', ''),
            userdata_dict.get('PlaybackPositionTicks'),
            userdata_dict.get('PlayCount'),
            userdata_dict.get('IsFavorite'),
            userdata_dict.get('Played'),
            userdata_dict.get('LastPlayedDate'),
            userdata_dict.get('PlayedPercentage'),
            userdata_dict.get('UnplayedItemCount')
        )
        self._close_db_rw("queue_userdata", SQLs)

        self._schedule_processing()

    def queue_library_add(self, library_id, library_name, emby_type, kodi_dbs):
        """
        Queue a library for addition/sync.

        Called by:
        - select_libraries() after user selection

        Args:
            library_id: Emby library ID
            library_name: Library display name
            emby_type: Content type (Movie, Series, etc.)
            kodi_dbs: Target Kodi database(s) ("video", "music", "video,music")
        """
        if self._shutdown:
            return

        xbmc.log(f"EMBY.database.sync_manager: queue_library_add: {library_id}, type: {emby_type}", 1)  # LOGINFO

        from . import dbio
        SQLs = self._open_db_rw("queue_library_add")
        SQLs["emby"].add_LibraryAdd(library_id, library_name, emby_type, kodi_dbs)
        self._close_db_rw("queue_library_add", SQLs)

        self._schedule_processing()

    def queue_library_remove(self, library_id, library_name):
        """
        Queue a library for removal.

        Called by:
        - select_libraries() after user selection

        Args:
            library_id: Emby library ID
            library_name: Library display name
        """
        if self._shutdown:
            return

        xbmc.log(f"EMBY.database.sync_manager: queue_library_remove: {library_id}", 1)  # LOGINFO

        from . import dbio
        SQLs = self._open_db_rw("queue_library_remove")
        SQLs["emby"].add_LibraryRemove(library_id, library_name)
        self._close_db_rw("queue_library_remove", SQLs)

        self._schedule_processing()

    def queue_kodi_to_emby(self, emby_id, update_type, data):
        """
        Queue a Kodi→Emby sync operation.

        Called by:
        - monitor.VideoLibrary_OnUpdate (playcount changes)
        - monitor.VideoLibrary_OnRemove (deletions)

        Args:
            emby_id: Emby item ID
            update_type: "playcount", "progress", or "delete"
            data: Dict with update-specific data
        """
        if self._shutdown or utils.RemoteMode:
            return

        xbmc.log(f"EMBY.database.sync_manager: queue_kodi_to_emby: {emby_id}, type: {update_type}", 0)  # LOGDEBUG

        # Add to skip list to prevent echo
        self.add_item_skip_update(str(emby_id))

        # Perform the API call
        if update_type == "playcount":
            self.emby_server.API.set_played(emby_id, data.get('playcount', 0))
        elif update_type == "progress":
            self.emby_server.API.set_progress(
                emby_id,
                data.get('position_ticks', 0),
                data.get('playcount', 0)
            )
        elif update_type == "delete":
            self.emby_server.API.delete_item(emby_id)

    # ═══════════════════════════════════════════════════════════════════════════
    # PUBLIC API - Sync Control Methods
    # ═══════════════════════════════════════════════════════════════════════════

    def startup_sync(self, first_run=False):
        """
        Run startup/incremental sync.

        This is the main entry point for startup sync, called when:
        - Kodi starts
        - System wakes from sleep
        - Settings change sync date

        Args:
            first_run: If True, show library selection dialog
        """
        xbmc.log(f"EMBY.database.sync_manager: -->[ startup_sync, first_run={first_run} ]", 1)  # LOGINFO

        # Delegate to existing KodiStartSync for now
        # This maintains compatibility while we migrate
        self.emby_server.library.KodiStartSync(first_run)

        xbmc.log(f"EMBY.database.sync_manager: --<[ startup_sync complete ]", 1)  # LOGINFO

    def trigger_sync_check(self):
        """
        Trigger a sync check (called after Emby server operations complete).

        Called by:
        - websocket.EmbyServerSyncCheck after server tasks complete
        """
        xbmc.log(f"EMBY.database.sync_manager: trigger_sync_check", 0)  # LOGDEBUG
        self._schedule_processing()

    def set_server_busy(self, is_busy):
        """
        Set server busy state.

        Called by:
        - websocket.EmbyServerSyncCheck when detecting server activity

        Args:
            is_busy: True if server is busy, False if idle
        """
        utils.SyncPause[f"server_busy_{self.server_id}"] = is_busy
        xbmc.log(f"EMBY.database.sync_manager: set_server_busy: {is_busy}", 0)  # LOGDEBUG

    def on_kodi_scan_finished(self, library):
        """
        Handle Kodi scan finished event.

        Called by:
        - monitor.onScanFinished

        Args:
            library: "video" or "music"
        """
        xbmc.log(f"EMBY.database.sync_manager: on_kodi_scan_finished: {library}", 0)  # LOGDEBUG

        # Check if this was a plugin-initiated scan
        if self.plugin_scan_active.get(library, False):
            self.plugin_scan_active[library] = False
            xbmc.log(f"EMBY.database.sync_manager: Plugin scan finished ({library}), skipping sync", 1)  # LOGINFO
            # Don't trigger sync - this was our own widget refresh
            utils.WidgetRefresh[library] = False

            if not utils.WidgetRefresh['music'] and not utils.WidgetRefresh['video']:
                utils.SyncPause['kodi_rw'] = False
            return

        # User-initiated scan - trigger sync check
        utils.WidgetRefresh[library] = False

        if not utils.WidgetRefresh['music'] and not utils.WidgetRefresh['video']:
            utils.SyncPause['kodi_rw'] = False

            if not utils.RemoteMode:
                self._schedule_processing()

    def on_kodi_clean_finished(self, library):
        """
        Handle Kodi clean finished event.

        Called by:
        - monitor.onCleanFinished

        Args:
            library: "video" or "music"
        """
        xbmc.log(f"EMBY.database.sync_manager: on_kodi_clean_finished: {library}", 0)  # LOGDEBUG

        # Check if this was a plugin-initiated clean
        if self.plugin_scan_active.get(library, False):
            self.plugin_scan_active[library] = False
            xbmc.log(f"EMBY.database.sync_manager: Plugin clean finished ({library}), skipping sync", 1)  # LOGINFO
            utils.WidgetRefresh[library] = False

            if not utils.WidgetRefresh['music'] and not utils.WidgetRefresh['video']:
                utils.SyncPause['kodi_rw'] = False
            return

        # User-initiated clean - trigger sync check
        utils.WidgetRefresh[library] = False

        if not utils.WidgetRefresh['music'] and not utils.WidgetRefresh['video']:
            utils.SyncPause['kodi_rw'] = False

            if not utils.RemoteMode:
                self._schedule_processing()

    def shutdown(self):
        """
        Graceful shutdown - cancel timers, flush pending.

        Called by:
        - EmbyServer.stop()
        """
        xbmc.log(f"EMBY.database.sync_manager: -->[ shutdown ]", 1)  # LOGINFO
        self._shutdown = True

        # Cancel debounce timer
        with self.debounce_lock:
            if self.debounce_timer:
                self.debounce_timer.cancel()
                self.debounce_timer = None

        # Wait for any in-progress sync to complete
        # Note: We don't force stop - let it finish naturally
        if self.sync_lock.locked():
            xbmc.log(f"EMBY.database.sync_manager: Waiting for sync to complete...", 1)  # LOGINFO
            # Give it a reasonable timeout
            acquired = self.sync_lock.acquire(timeout=30)
            if acquired:
                self.sync_lock.release()

        xbmc.log(f"EMBY.database.sync_manager: --<[ shutdown complete ]", 1)  # LOGINFO

    # ═══════════════════════════════════════════════════════════════════════════
    # PUBLIC API - Echo Prevention
    # ═══════════════════════════════════════════════════════════════════════════

    def add_item_skip_update(self, emby_id, duration_seconds=5):
        """
        Add item to skip list to prevent echo from our own updates.

        When we update an item (Kodi→Emby), Emby sends back a WebSocket event.
        We need to ignore this "echo" to prevent infinite loops.

        Args:
            emby_id: Emby item ID (as string)
            duration_seconds: How long to skip updates for this item
        """
        with self.items_skip_update_lock:
            self.items_skip_update.add(str(emby_id))

        # Remove from skip list after duration
        def remove_skip():
            with self.items_skip_update_lock:
                self.items_skip_update.discard(str(emby_id))

        timer = threading.Timer(duration_seconds, remove_skip)
        timer.daemon = True
        timer.start()

    def should_skip_userdata(self, emby_id):
        """
        Check if userdata update should be skipped (echo prevention).

        Args:
            emby_id: Emby item ID (as string)

        Returns:
            True if this update should be skipped
        """
        with self.items_skip_update_lock:
            return str(emby_id) in self.items_skip_update

    # ═══════════════════════════════════════════════════════════════════════════
    # INTERNAL - Debouncing
    # ═══════════════════════════════════════════════════════════════════════════

    def _schedule_processing(self):
        """
        Schedule queue processing with debounce.

        Resets the debounce timer - processing starts after 2s of quiet.
        """
        if self._shutdown:
            return

        with self.debounce_lock:
            # Cancel existing timer
            if self.debounce_timer:
                self.debounce_timer.cancel()

            # Start new timer
            self.debounce_timer = threading.Timer(
                self.debounce_seconds,
                self._process_queue_wrapper
            )
            self.debounce_timer.daemon = True
            self.debounce_timer.start()

    def _process_queue_wrapper(self):
        """
        Wrapper to run _process_queue in a thread-safe manner.
        """
        if self._shutdown:
            return

        # Start in a new thread to not block the timer thread
        utils.start_thread(self._process_queue, ())

    # ═══════════════════════════════════════════════════════════════════════════
    # INTERNAL - Queue Processing
    # ═══════════════════════════════════════════════════════════════════════════

    def _process_queue(self):
        """
        Process all queued items in correct order.

        This is the main sync processing method that:
        1. Acquires sync lock (only one sync at a time)
        2. Processes removals
        3. Processes updates
        4. Processes library changes
        5. Processes userdata
        6. Refreshes widgets once at end
        """
        if self._shutdown:
            return

        # Only one sync at a time
        if not self.sync_lock.acquire(blocking=False):
            xbmc.log(f"EMBY.database.sync_manager: _process_queue: Sync already in progress, scheduling retry", 0)  # LOGDEBUG
            # Schedule retry after debounce
            self._schedule_processing()
            return

        try:
            self.state = SyncState.SYNCING
            xbmc.log(f"EMBY.database.sync_manager: -->[ _process_queue ]", 0)  # LOGDEBUG

            # Check if paused
            if self._is_paused():
                xbmc.log(f"EMBY.database.sync_manager: _process_queue: Paused, will retry", 0)  # LOGDEBUG
                self._schedule_processing()
                return

            # Check if there's anything to process
            if not self._has_pending_items():
                xbmc.log(f"EMBY.database.sync_manager: _process_queue: No pending items", 0)  # LOGDEBUG
                return

            # Delegate to existing RunJobs for now
            # This maintains compatibility while we migrate
            # The existing workers handle all the complex logic
            self.emby_server.library.RunJobs(True)

            xbmc.log(f"EMBY.database.sync_manager: --<[ _process_queue complete ]", 0)  # LOGDEBUG

        except Exception as e:
            xbmc.log(f"EMBY.database.sync_manager: _process_queue ERROR: {e}", 3)  # LOGERROR
        finally:
            self.state = SyncState.IDLE
            self.sync_lock.release()

    def _has_pending_items(self):
        """
        Check if there are any items pending in the queues.

        Returns:
            True if any queue has items
        """
        from . import dbio

        embydb = dbio.DBOpenRO(self.server_id, "has_pending_items")
        try:
            # Check each queue
            has_remove = embydb.count_RemoveItems() > 0
            has_update = embydb.count_UpdateItems() > 0
            has_userdata = embydb.count_UserdataItems() > 0
            has_library_add = embydb.count_LibraryAdd() > 0
            has_library_remove = embydb.count_LibraryRemove() > 0

            return has_remove or has_update or has_userdata or has_library_add or has_library_remove
        finally:
            dbio.DBCloseRO(self.server_id, "has_pending_items")

    def _is_paused(self):
        """
        Check if sync should be paused.

        Returns:
            True if sync should pause
        """
        # Check standard pause conditions
        for key, busy in list(utils.SyncPause.items()):
            if busy:
                # Skip conditions that don't apply to this server
                if key.startswith("server_") and not key.endswith(self.server_id):
                    continue
                if key.startswith("database_init_") and not key.endswith(self.server_id):
                    continue

                xbmc.log(f"EMBY.database.sync_manager: _is_paused: True ({key})", 0)  # LOGDEBUG
                return True

        return False

    # ═══════════════════════════════════════════════════════════════════════════
    # INTERNAL - Widget Refresh Control
    # ═══════════════════════════════════════════════════════════════════════════

    def _refresh_widgets_once(self, refresh_video=False, refresh_audio=False):
        """
        Refresh widgets once, tracking that it's a plugin-initiated scan.

        This prevents the widget refresh cascade where:
        onScanFinished → syncEmby → RunJobs → refresh_widgets → onScanFinished...

        Args:
            refresh_video: Whether to refresh video widgets
            refresh_audio: Whether to refresh audio widgets
        """
        if refresh_video:
            self.plugin_scan_active['video'] = True
            self.widget_refresh_needed['video'] = False
            utils.refresh_widgets(True)

        if refresh_audio:
            self.plugin_scan_active['music'] = True
            self.widget_refresh_needed['music'] = False
            utils.refresh_widgets(False)

    # ═══════════════════════════════════════════════════════════════════════════
    # INTERNAL - Database Helpers
    # ═══════════════════════════════════════════════════════════════════════════

    def _open_db_rw(self, operation_name):
        """
        Open Emby database for read-write.

        Args:
            operation_name: Name for logging

        Returns:
            SQLs dict with database connection
        """
        return self.emby_server.library.open_EmbyDBRW(operation_name, True)

    def _close_db_rw(self, operation_name, SQLs):
        """
        Close Emby database read-write connection.

        Args:
            operation_name: Name for logging
            SQLs: Database connections dict
        """
        self.emby_server.library.close_EmbyDBRW(operation_name, SQLs)

    # ═══════════════════════════════════════════════════════════════════════════
    # CONVENIENCE METHODS - Expose Library Functions
    # ═══════════════════════════════════════════════════════════════════════════

    def refresh_boxsets(self):
        """
        Convenience method to trigger boxset refresh.

        Called by: UI/manual trigger
        """
        self.emby_server.library.refresh_boxsets()

    def sync_livetv(self):
        """
        Convenience method to trigger LiveTV sync.

        Called by: UI/manual trigger
        """
        self.emby_server.library.SyncLiveTV()

    def sync_livetv_epg(self, channel_sync=True):
        """
        Convenience method to trigger LiveTV EPG sync.

        Called by:
        - websocket.EmbyServerSyncCheck when EPGRefresh detected
        - KodiStartSync

        Args:
            channel_sync: Whether to also sync channels
        """
        self.emby_server.library.SyncLiveTVEPG(channel_sync)

    def sync_themes(self):
        """
        Convenience method to trigger theme sync.

        Called by: UI/manual trigger
        """
        self.emby_server.library.SyncThemes()

    def select_libraries(self, mode):
        """
        Convenience method to trigger library selection.

        Called by: UI/settings

        Args:
            mode: Selection mode (AddLibrarySelection, RepairLibrarySelection, etc.)
        """
        self.emby_server.library.select_libraries(mode)
