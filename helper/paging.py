"""Internal paging policy. Edit these constants for controlled comparisons.

Full metadata and lightweight queries share the same media-type limits.
These values do not read Kodi settings, including values saved by older builds.
"""

DEFAULT_PAGE_SIZE = 100
PAGE_SIZE_OVERRIDES = {
    "episode": 1000,
    "audio": 1000,
    "musicartist": 1000,
}
MAX_URI_LENGTH = 1500

# Startup change discovery only; detail queries and database workers stay serial.
CHANGE_QUERY_WORKERS = 4


def get_limit(media_type):
    media_type = (media_type or "").lower()
    return PAGE_SIZE_OVERRIDES.get(media_type, DEFAULT_PAGE_SIZE)
