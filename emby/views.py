from urllib.parse import urlencode

import xbmcvfs
from database import dbio
from helper import utils


PLUGIN_PATH = "plugin://plugin.service.emby-next-gen/?"
XML_HEADER = '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>\n'
PLAYLIST_NODE_FOLDERS = (
    "special://profile/library/music/emby_playlistsaudio_Playlists/",
    "special://profile/library/video/emby_playlistsvideo_Playlists/",
)

SyncNodes = {
    'tvshows': [
        ('letter', utils.Translate(33611), 'special://home/addons/plugin.service.emby-next-gen/resources/letter.png', "tvshows", (("tag", "is", "LIBRARYTAG"), ("sorttitle", "startswith")), ("ascending", "sorttitle"), False, False, ("letter", "LETTER")),
        ('all', "LIBRARYNAME", 'DefaultTVShows.png', "tvshows", (("tag", "is", "LIBRARYTAG"),), ("ascending", "sorttitle"), False, False),
        ('recentlyadded', utils.Translate(30170), 'DefaultRecentlyAddedEpisodes.png', "tvshows", (("tag", "is", "LIBRARYTAG"), ("playcount", "is", "0")), ("descending", "dateadded"), True, False),
        ('recentlyaddedepisodes', utils.Translate(30175), 'DefaultRecentlyAddedEpisodes.png', "episodes", (("tag", "is", "LIBRARYTAG"), ("playcount", "is", "0")), ("descending", "dateadded"), True, False),
        ('inprogress', utils.Translate(33169), 'DefaultInProgressShows.png', "tvshows", (("tag", "is", "LIBRARYTAG"), ("inprogress", "true")), ("descending", "lastplayed"), False, False),
        ('inprogressepisodes', utils.Translate(30178), 'DefaultInProgressShows.png', "episodes", (("tag", "is", "LIBRARYTAG"), ("inprogress", "true")), ("descending", "lastplayed"), False, False),
        ('genres', utils.Translate(33248), 'DefaultGenre.png', "tvshows", (("tag", "is", "LIBRARYTAG"),), ("ascending", "sorttitle"), False, "genres"),
        ('random', utils.Translate(33883), 'special://home/addons/plugin.service.emby-next-gen/resources/random.png', "tvshows", (("tag", "is", "LIBRARYTAG"),), ("random",), True, False),
        ('recommended', utils.Translate(33884), 'DefaultFavourites.png', "tvshows", (("tag", "is", "LIBRARYTAG"), ("inprogress", "false"), ("playcount", "is", "0"), ("rating", "greaterthan", "7")), ("descending", "rating"), True, None),
        ('years', utils.Translate(33218), 'DefaultYear.png', "tvshows", (("tag", "is", "LIBRARYTAG"),), ("descending", "year"), False, "years"),
        ('actors', utils.Translate(33219), 'DefaultActor.png', "tvshows", (("tag", "is", "LIBRARYTAG"),), ("ascending", "title"), False, "actors"),
        ('tags', utils.Translate(33220), 'DefaultTags.png', "tvshows", (("tag", "is", "LIBRARYTAG"),), ("ascending", "title"), False, "tags"),
        ('favorites', utils.Translate(33558), 'DefaultTags.png', "tvshows", (("tag", "is", "LIBRARYTAG"), ("tag", "endswith", "(Favorites)")), ("ascending", "title"), False, False),
        ('unwatched', utils.Translate(33170), 'OverlayUnwatched.png', "tvshows", (("tag", "is", "LIBRARYTAG"), ("inprogress", "false"), ("playcount", "is", "0")), ("random",), True, False),
        ('unwatchedepisodes', utils.Translate(33344), 'OverlayUnwatched.png', "episodes", (("tag", "is", "LIBRARYTAG"), ("inprogress", "false"), ("playcount", "is", "0")), ("random",), False, False),
        ('studios', utils.Translate(33249), 'DefaultStudios.png', "tvshows", (("tag", "is", "LIBRARYTAG"),), ("ascending", "title"), False, "studios"),
        ('recentlyplayed', utils.Translate(33347), 'DefaultMusicRecentlyPlayed.png', "tvshows", (("tag", "is", "LIBRARYTAG"), ("inprogress", "false"), ("playcount", "greaterthan", "0")), ("descending", "lastplayed"), True, None),
        ('recentlyplayedepisodes', utils.Translate(33351), 'DefaultMusicRecentlyPlayed.png', "episodes", (("tag", "is", "LIBRARYTAG"), ("inprogress", "false"), ("playcount", "greaterthan", "0")), ("descending", "lastplayed"), True, None),
        ('nextepisodes', utils.Translate(30179), 'DefaultInProgressShows.png', "tvshows", (("PLUGIN", "nextepisodes", "episode"),)),
        ('nextepisodesplayed', utils.Translate(33667), 'DefaultInProgressShows.png', "tvshows", (("PLUGIN", "nextepisodesplayed", "episode"),)),
    ],
    'movies': [
        ('letter', utils.Translate(33611), 'special://home/addons/plugin.service.emby-next-gen/resources/letter.png', "movies", (("tag", "is", "LIBRARYTAG"), ("sorttitle", "startswith"),), ("ascending", "sorttitle"), False, False, ("letter", "LETTER")),
        ('all', "LIBRARYNAME", 'DefaultMovies.png', "movies", (("tag", "is", "LIBRARYTAG"),), ("ascending", "sorttitle"), False, False),
        ('recentlyadded', utils.Translate(33896), 'DefaultRecentlyAddedMovies.png', "movies", (("tag", "is", "LIBRARYTAG"), ("playcount", "is", "0")), ("descending", "dateadded"), True, False),
        ('recentlyreleased', utils.Translate(33619), 'DefaultRecentlyAddedMovies.png', "movies", (("tag", "is", "LIBRARYTAG"),), ("descending", "year"), True, False),
        ('inprogress', utils.Translate(33169), 'DefaultInProgressShows.png', "movies", (("tag", "is", "LIBRARYTAG"), ("inprogress", "true")), ("descending", "lastplayed"), False, False),
        ('unwatched', utils.Translate(33170), 'OverlayUnwatched.png', "movies", (("tag", "is", "LIBRARYTAG"), ("inprogress", "false"), ("playcount", "is", "0")), ("random",), True, False),
        ('recentlyreleasedunwatched', utils.Translate(33618), 'OverlayUnwatched.png', "movies", (("tag", "is", "LIBRARYTAG"), ("playcount", "is", "0")), ("descending", "year"), True, False),
        ('sets', utils.Translate(30185), 'DefaultSets.png', "movies", (("tag", "is", "LIBRARYTAG"),), ("ascending", "sorttitle"), False, "sets"),
        ('genres', utils.Translate(33248), 'DefaultGenre.png', "movies", (("tag", "is", "LIBRARYTAG"),), ("ascending", "sorttitle"), False, "genres"),
        ('random', utils.Translate(33883), 'special://home/addons/plugin.service.emby-next-gen/resources/random.png', "movies", (("tag", "is", "LIBRARYTAG"),), ("random",), True, False),
        ('recommended', utils.Translate(33884), 'DefaultFavourites.png', "movies", (("tag", "is", "LIBRARYTAG"), ("inprogress", "false"), ("playcount", "is", "0"), ("rating", "greaterthan", "7")), ("descending", "rating"), True, False),
        ('years', utils.Translate(33218), 'DefaultYear.png', "movies", (("tag", "is", "LIBRARYTAG"),), ("descending", "year"), False, "years"),
        ('actors', utils.Translate(33219), 'DefaultActor.png', "movies", (("tag", "is", "LIBRARYTAG"),), ("ascending", "title"), False, "actors"),
        ('tags', utils.Translate(33220), 'DefaultTags.png', "movies", (("tag", "is", "LIBRARYTAG"),), ("ascending", "title"), False, "tags"),
        ('collections', utils.Translate(33612), 'DefaultSets.png', "movies", (("tag", "is", "LIBRARYTAG"),), ("ascending", "sorttitle"), False, "sets"),
        ('favorites', utils.Translate(33558), 'DefaultTags.png', "movies", (("tag", "is", "LIBRARYTAG"), ("tag", "endswith", "(Favorites)")), ("ascending", "title"), False, False),
        ('studios', utils.Translate(33249), 'DefaultStudios.png', "movies", (("tag", "is", "LIBRARYTAG"),), ("ascending", "title"), False, "studios"),
        ('recentlyplayed', utils.Translate(33350), 'DefaultMusicRecentlyPlayed.png', "movies", (("tag", "is", "LIBRARYTAG"), ("inprogress", "false"), ("playcount", "greaterthan", "0")), ("descending", "lastplayed"), True, False),
        ('directors', utils.Translate(33352), 'DefaultDirector.png', "movies", (("tag", "is", "LIBRARYTAG"),), ("ascending", "title"), False, "directors"),
        ('countries', utils.Translate(33358), 'DefaultCountry.png', "movies", (("tag", "is", "LIBRARYTAG"),), ("ascending", "title"), False, "countries"),
        ('resolutionhd', utils.Translate(33359), 'DefaultIconInfo.png', "movies", (("tag", "is", "LIBRARYTAG"), ("videoresolution", "is", "1080")), ("ascending", "sorttitle"), False, False),
        ('resolutionsd', utils.Translate(33360), 'DefaultIconInfo.png', "movies", (("tag", "is", "LIBRARYTAG"), ("videoresolution", "lessthan", "1080")), ("ascending", "sorttitle"), False, False),
        ('resolution4k', utils.Translate(33361), 'DefaultIconInfo.png', "movies", (("tag", "is", "LIBRARYTAG"), ("videoresolution", "greaterthan", "1080")), ("ascending", "sorttitle"), False, False)
    ],
    'musicvideos': [
        ('letter', utils.Translate(33611), 'special://home/addons/plugin.service.emby-next-gen/resources/letter.png', "musicvideos", (("tag", "is", "LIBRARYTAG"), ("artist", "startswith")), ("ascending", "sorttitle"), False, False, ("letter", "LETTER")),
        ('all', "LIBRARYNAME", 'DefaultMusicVideos.png', "musicvideos", (("tag", "is", "LIBRARYTAG"),), ("ascending", "artist"), False, False),
        ('recentlyadded', utils.Translate(33867), 'DefaultRecentlyAddedMusicVideos.png', "musicvideos", (("tag", "is", "LIBRARYTAG"), ("playcount", "is", "0")), ("descending", "dateadded"), True, False),
        ('recentlyaddedmusicvideoalbums', utils.Translate(33388), 'DefaultRecentlyAddedMusicVideos.png', "musicvideos", (("PLUGIN", "recentlyaddedmusicvideoalbums", "musicvideo"),)),
        ('years', utils.Translate(33218), 'DefaultMusicYears.png', "musicvideos", (("tag", "is", "LIBRARYTAG"),), ("descending", "year"), False, "years"),
        ('genres', utils.Translate(33248), 'DefaultGenre.png', "musicvideos", (("tag", "is", "LIBRARYTAG"),), ("ascending", "sorttitle"), False, "genres"),
        ('albums', utils.Translate(33362), 'DefaultMusicAlbums.png', "musicvideos", (("tag", "is", "LIBRARYTAG"),), ("ascending", "sorttitle"), False, "albums"),
        ('inprogress', utils.Translate(33169), 'DefaultInProgressShows.png', "musicvideos", (("tag", "is", "LIBRARYTAG"), ("inprogress", "true")), ("descending", "lastplayed"), False, False),
        ('random', utils.Translate(33883), 'special://home/addons/plugin.service.emby-next-gen/resources/random.png', "musicvideos", (("tag", "is", "LIBRARYTAG"),), ("random",), True, False),
        ('unwatched', utils.Translate(33170), 'OverlayUnwatched.png', "musicvideos", (("tag", "is", "LIBRARYTAG"), ("inprogress", "false"), ("playcount", "is", "0")), ("random",), True, False),
        ('artists', utils.Translate(33343), 'DefaultMusicArtists.png', "musicvideos", (("tag", "is", "LIBRARYTAG"),), ("ascending", "artists"), False, "artists"),
        ('tags', utils.Translate(33220), 'DefaultTags.png', "musicvideos", (("tag", "is", "LIBRARYTAG"),), ("ascending", "title"), False, "tags"),
        ('favorites', utils.Translate(33558), 'DefaultTags.png', "musicvideos", (("tag", "is", "LIBRARYTAG"), ("tag", "endswith", "(Favorites)")), ("ascending", "title"), False, False),
        ('recentlyplayed', utils.Translate(33350), 'DefaultMusicRecentlyPlayed.png', "musicvideos", (("tag", "is", "LIBRARYTAG"), ("inprogress", "false"), ("playcount", "greaterthan", "0")), ("descending", "lastplayed"), True, False),
        ('resolutionhd', utils.Translate(33359), 'DefaultIconInfo.png', "musicvideos", (("tag", "is", "LIBRARYTAG"), ("videoresolution", "is", "1080")), ("ascending", "sorttitle"), False, False),
        ('resolutionsd', utils.Translate(33360), 'DefaultIconInfo.png', "musicvideos", (("tag", "is", "LIBRARYTAG"), ("videoresolution", "lessthan", "1080")), ("ascending", "sorttitle"), False, False),
        ('resolution4k', utils.Translate(33361), 'DefaultIconInfo.png', "musicvideos", (("tag", "is", "LIBRARYTAG"), ("videoresolution", "greaterthan", "1080")), ("ascending", "sorttitle"), False, False)
    ],
    'homevideos': [
        ('letter', utils.Translate(33611), 'special://home/addons/plugin.service.emby-next-gen/resources/letter.png', "movies", (("tag", "is", "LIBRARYTAG"), ("sorttitle", "startswith")), ("ascending", "sorttitle"), False, False, ("letter", "LETTER")),
        ('all', "LIBRARYNAME", 'DefaultMusicVideos.png', "movies", (("tag", "is", "LIBRARYTAG"),), ("ascending", "sorttitle"), False, False),
        ('recentlyadded', utils.Translate(33896), 'DefaultRecentlyAddedMusicVideos.png', "movies", (("tag", "is", "LIBRARYTAG"), ("playcount", "is", "0")), ("descending", "dateadded"), True, False),
        ('years', utils.Translate(33218), 'DefaultMusicYears.png', "movies", (("tag", "is", "LIBRARYTAG"),), ("descending", "year"), False, "years"),
        ('genres', utils.Translate(33248), 'DefaultGenre.png', "movies", (("tag", "is", "LIBRARYTAG"),), ("ascending", "sorttitle"), False, "genres"),
        ('inprogress', utils.Translate(33169), 'DefaultInProgressShows.png', "movies", (("tag", "is", "LIBRARYTAG"), ("inprogress", "true")), ("descending", "lastplayed"), False, False),
        ('random', utils.Translate(33883), 'special://home/addons/plugin.service.emby-next-gen/resources/random.png', "movies", (("tag", "is", "LIBRARYTAG"),), ("random",), True, False),
        ('unwatched', utils.Translate(33170), 'OverlayUnwatched.png', "movies", (("tag", "is", "LIBRARYTAG"), ("inprogress", "false"), ("playcount", "is", "0")), ("random",), True, False),
        ('tags', utils.Translate(33220), 'DefaultTags.png', "movies", (("tag", "is", "LIBRARYTAG"),), ("ascending", "title"), False, "tags"),
        ('collections', utils.Translate(33612), 'DefaultSets.png', "movies", (("tag", "is", "LIBRARYTAG"),), ("ascending", "sorttitle"), False, "sets"),
        ('favorites', utils.Translate(33558), 'DefaultTags.png', "movies", (("tag", "is", "LIBRARYTAG"), ("tag", "endswith", "(Favorites)")), ("ascending", "title"), False, False),
        ('recentlyplayed', utils.Translate(33350), 'DefaultMusicRecentlyPlayed.png', "movies", (("tag", "is", "LIBRARYTAG"), ("inprogress", "false"), ("playcount", "greaterthan", "0")), ("descending", "lastplayed"), True, False),
        ('resolutionhd', utils.Translate(33359), 'DefaultIconInfo.png', "movies", (("tag", "is", "LIBRARYTAG"), ("videoresolution", "is", "1080")), ("ascending", "sorttitle"), False, False),
        ('resolutionsd', utils.Translate(33360), 'DefaultIconInfo.png', "movies", (("tag", "is", "LIBRARYTAG"), ("videoresolution", "lessthan", "1080")), ("ascending", "sorttitle"), False, False),
        ('resolution4k', utils.Translate(33361), 'DefaultIconInfo.png', "movies", (("tag", "is", "LIBRARYTAG"), ("videoresolution", "greaterthan", "1080")), ("ascending", "sorttitle"), False, False)
    ],
    'music': [
        ('letter', utils.Translate(33611), 'special://home/addons/plugin.service.emby-next-gen/resources/letter.png', "artists", (("disambiguation", "is", "LIBRARYTAG"), ("artist", "startswith")), ("ascending", "artist"), False, False, ("letter", "LETTER")),
        ('all', "LIBRARYNAME", 'DefaultAddonMusic.png', "artists", (("disambiguation", "is", "LIBRARYTAG"),), ("ascending", "sorttitle"), False, False),
        ('years', utils.Translate(33697), 'DefaultMusicYears.png', "albums", (("type", "is", "LIBRARYTAG"),), ("descending", "year"), False, "years"),
        ('singlesyears', utils.Translate(33698), 'DefaultMusicYears.png', "songs", (("comment", "contains", "LIBRARYTAG"),), ("descending", "year"), True, "singles"),
        ('genres', utils.Translate(33248), 'DefaultMusicGenres.png', "artists", (("disambiguation", "is", "LIBRARYTAG"),), ("ascending", "sorttitle"), False, "genres"),
        ('songsbygenres', utils.Translate(33435), 'DefaultMusicGenres.png', "songs", (("comment", "contains", "LIBRARYTAG"), ("genre", "is")), ("ascending", "title"), True, False, ("genres", "DBMUSICGENRE")),
        ('artists', utils.Translate(33343), 'DefaultMusicArtists.png', "artists", (("disambiguation", "is", "LIBRARYTAG"), ("role", "is", "artist")), ("ascending", "artists"), False, False),
        ('composers', utils.Translate(33426), 'DefaultMusicArtists.png', "artists", (("disambiguation", "is", "LIBRARYTAG"), ("role", "is", "composer")), ("ascending", "artists"), False, False),
        ('albums', utils.Translate(33362), 'DefaultMusicAlbums.png', "albums", (("type", "is", "LIBRARYTAG"),), ("descending", "title"), False, "albums"),
        ('singles', utils.Translate(33699), 'DefaultMusicAlbums.png', "songs", (("comment", "contains", "LIBRARYTAG"),), ("descending", "title"), False, "singles"),
        ('recentlyaddedalbums', utils.Translate(33388), 'DefaultMusicRecentlyAdded.png', "albums", (("type", "is", "LIBRARYTAG"),), ("descending", "dateadded"), True, False),
        ('recentlyaddedsingles', utils.Translate(33700), 'DefaultMusicRecentlyAdded.png', "songs", (("comment", "contains", "LIBRARYTAG"),), ("descending", "dateadded"), False, "singles"),
        ('recentlyadded', utils.Translate(33390), 'DefaultMusicRecentlyAdded.png', "songs", (("comment", "contains", "LIBRARYTAG"), ("playcount", "is", "0")), ("descending", "dateadded"), True, False),
        ('recentlyplayedmusic', utils.Translate(33350), 'DefaultMusicRecentlyPlayed.png', "songs", (("comment", "contains", "LIBRARYTAG"), ("playcount", "greaterthan", "0")), ("descending", "lastplayed"), True, False),
        ('randomalbums', utils.Translate(33391), 'special://home/addons/plugin.service.emby-next-gen/resources/random.png', "albums", (("type", "is", "LIBRARYTAG"),), ("random",), True, False),
        ('randomsingles', utils.Translate(33701), 'special://home/addons/plugin.service.emby-next-gen/resources/random.png', "songs", (("comment", "contains", "LIBRARYTAG"),), ("random",), True, "singles"),
        ('random', utils.Translate(33392), 'special://home/addons/plugin.service.emby-next-gen/resources/random.png', "songs", (("comment", "contains", "LIBRARYTAG"),), ("random",), True, False)
    ],
    'audiobooks': [
        ('letter', utils.Translate(33611), 'special://home/addons/plugin.service.emby-next-gen/resources/letter.png', "artists", (("disambiguation", "is", "LIBRARYTAG"), ("artist", "startswith")), ("ascending", "artist"), False, False, ("letter", "LETTER")),
        ('all', "LIBRARYNAME", 'DefaultAddonMusic.png', "artists", (("disambiguation", "is", "LIBRARYTAG"),), ("ascending", "sorttitle"), False, False),
        ('years', utils.Translate(33218), 'DefaultMusicYears.png', "albums", (("type", "is", "LIBRARYTAG"),), ("descending", "year"), False, "years"),
        ('singlesyears', utils.Translate(33698), 'DefaultMusicYears.png', "songs", (("comment", "contains", "LIBRARYTAG"),), ("descending", "year"), True, "singles"),
        ('genres', utils.Translate(33248), 'DefaultMusicGenres.png', "artists", (("disambiguation", "is", "LIBRARYTAG"),), ("ascending", "sorttitle"), False, "genres"),
        ('artists', utils.Translate(33343), 'DefaultMusicArtists.png', "artists", (("disambiguation", "is", "LIBRARYTAG"), ("role", "is", "artist")), ("ascending", "artists"), False, False),
        ('albums', utils.Translate(33362), 'DefaultMusicAlbums.png', "albums", (("type", "is", "LIBRARYTAG"),), ("descending", "title"), False, "albums"),
        ('singles', utils.Translate(33699), 'DefaultMusicAlbums.png', "songs", (("comment", "contains", "LIBRARYTAG"),), ("descending", "title"), False, "singles"),
        ('recentlyaddedalbums', utils.Translate(33388), 'DefaultMusicRecentlyAdded.png', "albums", (("type", "is", "LIBRARYTAG"),), ("descending", "dateadded"), True, False),
        ('recentlyaddedsingles', utils.Translate(33700), 'DefaultMusicRecentlyAdded.png', "songs", (("comment", "contains", "LIBRARYTAG"),), ("descending", "dateadded"), False, "singles"),
        ('recentlyadded', utils.Translate(33389), 'DefaultMusicRecentlyAdded.png', "songs", (("comment", "contains", "LIBRARYTAG"), ("playcount", "is", "0")), ("descending", "dateadded"), True, False),
        ('recentlyplayedmusic', utils.Translate(33350), 'DefaultMusicRecentlyPlayed.png', "songs", (("comment", "contains", "LIBRARYTAG"), ("playcount", "greaterthan", "0")), ("descending", "lastplayed"), True, False),
        ('randomalbums', utils.Translate(33391), 'special://home/addons/plugin.service.emby-next-gen/resources/random.png', "albums", (("type", "is", "LIBRARYTAG"),), ("random",), True, False),
        ('randomsingles', utils.Translate(33701), 'special://home/addons/plugin.service.emby-next-gen/resources/random.png', "songs", (("comment", "contains", "LIBRARYTAG"),), ("random",), True, "singles"),
        ('random', utils.Translate(33393), 'special://home/addons/plugin.service.emby-next-gen/resources/random.png', "songs", (("comment", "contains", "LIBRARYTAG"),), ("random",), True, False)
    ],
    'podcasts': [
        ('letter', utils.Translate(33611), 'special://home/addons/plugin.service.emby-next-gen/resources/letter.png', "artists", (("disambiguation", "is", "LIBRARYTAG"), ("artist", "startswith")), ("ascending", "artist"), False, False, ("letter", "LETTER")),
        ('all', "LIBRARYNAME", 'DefaultAddonMusic.png', "artists", (("disambiguation", "is", "LIBRARYTAG"),), ("ascending", "sorttitle"), False, False),
        ('years', utils.Translate(33218), 'DefaultMusicYears.png', "albums", (("type", "is", "LIBRARYTAG"),), ("descending", "year"), False, "years"),
        ('genres', utils.Translate(33248), 'DefaultMusicGenres.png', "artists", (("disambiguation", "is", "LIBRARYTAG"),), ("ascending", "sorttitle"), False, "genres"),
        ('artists', utils.Translate(33343), 'DefaultMusicArtists.png', "artists", (("disambiguation", "is", "LIBRARYTAG"), ("role", "is", "artist")), ("ascending", "artists"), False, False),
        ('albums', utils.Translate(33362), 'DefaultMusicAlbums.png', "albums", (("type", "is", "LIBRARYTAG"),), ("descending", "title"), False, "albums"),
        ('recentlyaddedalbums', utils.Translate(33388), 'DefaultMusicRecentlyAdded.png', "albums", (("type", "is", "LIBRARYTAG"),), ("descending", "dateadded"), True, False),
        ('recentlyadded', utils.Translate(33395), 'DefaultMusicRecentlyAdded.png', "songs", (("comment", "contains", "LIBRARYTAG"), ("playcount", "is", "0")), ("descending", "dateadded"), True, False),
        ('recentlyplayedmusic', utils.Translate(33350), 'DefaultMusicRecentlyPlayed.png', "songs", (("comment", "contains", "LIBRARYTAG"), ("playcount", "greaterthan", "0")), ("descending", "lastplayed"), True, False),
        ('randomalbums', utils.Translate(33391), 'special://home/addons/plugin.service.emby-next-gen/resources/random.png', "albums", (("type", "is", "LIBRARYTAG"),), ("random",), True, False),
        ('random', utils.Translate(33394), 'special://home/addons/plugin.service.emby-next-gen/resources/random.png', "songs", (("comment", "contains", "LIBRARYTAG"),), ("random",), True, False)
    ],
    'rootaudio': [
        ('emby_inprogressmixed', f"EMBY: {utils.Translate(33628)}", 'DefaultInProgressShows.png', "mixed", (("PLUGIN", "inprogressmixed", "mixed"),))
    ],
    'rootvideo': [
        ('emby_playlists', f"EMBY: {utils.Translate(33796)}", 'DefaultMusicPlaylists.png', "video", (("PLUGIN", "playlist", "video"),), (), False, True),
        ('emby_inprogressmixed', f"EMBY: {utils.Translate(33628)}", 'DefaultInProgressShows.png', "mixed", (("PLUGIN", "inprogressmixed", "mixed"),)),
        ('emby_nextepisodes', f"EMBY: {utils.Translate(33665)}", 'DefaultInProgressShows.png', "tvshows", (("PLUGIN", "nextepisodes", "episode"),)),
        ('emby_nextepisodesplayed', f"EMBY: {utils.Translate(33666)}", 'DefaultInProgressShows.png', "tvshows", (("PLUGIN", "nextepisodesplayed", "episode"),)),
        ('emby_favorite_movies', f"EMBY: {utils.Translate(33862)}", 'DefaultFavourites.png', "movies", (("tag", "is", "Movies (Favorites)"),), ("ascending", "sorttitle"), False, False),
        ('emby_favorite_series', f"EMBY: {utils.Translate(30181)}", 'DefaultFavourites.png', "tvshows", (("tag", "is", "TVShows (Favorites)"),), ("ascending", "sorttitle"), False, False),
        ('emby_favorite_episodes', f"EMBY: {utils.Translate(30182)}", 'DefaultFavourites.png', "episodes", (("PLUGIN", "favepisodes", "episode"),)),
        ('emby_favorite_seasons', f"EMBY: {utils.Translate(33576)}", 'DefaultFavourites.png', "seasons", (("PLUGIN", "favseasons", "season"),)),
        ('emby_favorite_musicvideos', f"EMBY: {utils.Translate(33385)}", 'DefaultFavourites.png', "musicvideos", (("tag", "is", "Musicvideos (Favorites)"),), ("ascending", "sorttitle"), False, False),
        ('emby_collections_movies', f"EMBY: {utils.Translate(33555)}", 'DefaultTags.png', "movies", (), ("ascending", "sorttitle"), False, "sets"),
    ],
    'playlistsaudio': [],
    'playlistsvideo': [],
}


class Views:
    def __init__(self, ServerData, ViewItems, LibrarySynced, API):
        self.ServerData = ServerData
        self.LibrarySynced = LibrarySynced
        self.API = API
        self.ViewItems = ViewItems
        self.NodesSynced = []

    def update_nodes(self, RemoveEmpty=False):
        Synced = {}
        for LibraryId, _, ItemType, _ in self.LibrarySynced:
            Synced.setdefault(str(LibraryId), set()).add(ItemType)

        Nodes = []

        for LibraryId, Data in list(self.ViewItems.items()):
            if utils.SystemShutdown:
                return

            Name, LibraryType, Icon = Data
            Types = Synced.get(str(LibraryId))
            if not Types:
                continue

            if LibraryType == "mixed":
                ContentTypes = []
                if Types.intersection(("Movie", "Video")):
                    ContentTypes.append("movies")
                if "Series" in Types:
                    ContentTypes.append("tvshows")
                if Types.intersection(("Audio", "MusicAlbum", "MusicArtist")):
                    ContentTypes.append("music")
            elif LibraryType == "homevideos":
                ContentTypes = ("movies",)
            elif LibraryType == "playlists":
                ContentTypes = ("playlistsaudio", "playlistsvideo")
                self.restore_playlist_nodes()
            elif LibraryType in SyncNodes:
                ContentTypes = (LibraryType,)
            else:
                continue

            for ContentType in ContentTypes:
                Label = f"{Name} ({ContentType})" if LibraryType == "mixed" and ContentType != "music" else Name
                Tag = f"EmbyLibraryId-{LibraryId}" if ContentType in ("music", "audiobooks", "podcasts") else Name
                FolderName = "Playlists" if LibraryType == "playlists" else Name
                Nodes.extend(self.add_nodes(ContentType, FolderName, Label, Tag, Icon, LibraryId))

        if self.ServerData["ServerId"] and Nodes:
            Nodes.extend(self.add_nodes("rootvideo"))
            Nodes.extend(self.add_nodes("rootaudio"))
            self.restore_musicgenre_nodes()
        elif self.ServerData["ServerId"] and RemoveEmpty:
            self.delete_root_nodes()
        self.NodesSynced = Nodes

    def delete_root_nodes(self):
        for Media, Content in (("video", "rootvideo"), ("music", "rootaudio")):
            for Node in SyncNodes[Content]:
                utils.delFile(f"special://profile/library/{Media}/{Node[0]}_{self.ServerData['ServerId']}.xml")

    def add_nodes(self, ContentType, Name="", Label="", Tag="", Icon="", LibraryId=None):
        Media = "music" if utils.ContentTypes[ContentType] == "audio" else "video"
        Folder = f"special://profile/library/{Media}/"
        Nodes = []
        Root = ContentType in ("rootvideo", "rootaudio")
        if not Root:
            Directory = f"emby_{ContentType}_{utils.valid_Filename(Name)}/"
            Folder += Directory
            Icon = Icon or {"movies": "DefaultMovies.png", "tvshows": "DefaultTVShows.png",
                            "musicvideos": "DefaultMusicVideos.png"}.get(ContentType, "DefaultMusicSongs.png")
            write_index(Folder, f"EMBY: {Label} ({ContentType})", Icon)
            Nodes.append((Label, f"library://{Media}/{Directory}", Icon))

        Order = 0
        for Node in SyncNodes[ContentType]:
            Order += 1
            if Root:
                Filename = f"{Node[0]}_{self.ServerData['ServerId']}"
                Nodes.append((Node[1][6:], f"library://{Media}/{Filename}.xml", Node[2]))
                self.set_synced_node(Folder, Filename, Node, Label, Tag, Order)
            elif len(Node) == 9:
                Order = self.add_group_nodes(Folder, Node, Tag, LibraryId, Order)
            else:
                self.set_synced_node(Folder, Node[0], Node, Label, Tag, Order)
        return Nodes

    def add_group_nodes(self, Folder, Node, Tag, LibraryId, Order):
        Subfolder, Group = Node[8]
        Folder += f"{Subfolder}/"
        if Group == "LETTER":
            Entries = [(Letter, Letter, Letter) for Letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
            Entries.insert(0, ("0-9", "0-9", tuple("0123456789&ÄÖÜ!()@#$*-+=}{[]?:;,.~<>\"'")))
        else:
            if "music" not in utils.DatabaseFiles:
                return Order
            MusicDB = dbio.DBOpenRO("music", "node_songsbygenres")
            try:
                Genres = MusicDB.get_genre(LibraryId)
            finally:
                dbio.DBCloseRO("music", "node_songsbygenres")
            Entries = [(utils.valid_Filename(Genre), Genre, Genre) for Genre in Genres]
            _, Files = xbmcvfs.listdir(Folder)
            CurrentFiles = {f"{Filename}.xml" for Filename, _, _ in Entries}
            for Filename in Files:
                if Filename.endswith(".xml") and Filename != "index.xml" and Filename not in CurrentFiles:
                    utils.delFile(f"{Folder}{Filename}")

        write_index(Folder, Node[1], Node[2])
        for Filename, Label, Value in Entries:
            Rules = (Node[4][0], Node[4][1] + (Value,))
            Subnode = (Filename, Label, *Node[2:4], Rules, *Node[5:8])
            self.set_synced_node(Folder, Filename, Subnode, Label, Tag, Order, 10 if Group != "LETTER" else 1)
            Order += 1
        return Order

    def set_synced_node(self, Folder, Filename, Node, LibraryName, Tag, Order, LimitFactor=1):
        _, Label, Icon, Content, Rules, *Options = Node
        Label = LibraryName if Label == "LIBRARYNAME" else Label
        EncodedLabel = utils.encode_XML(Label.strip())
        if EncodedLabel.isnumeric():
            EncodedLabel += "&#8203;"

        Plugin = Rules and Rules[0][0] == "PLUGIN"
        XML = XML_HEADER + f'<node order="{Order}" type="{"folder" if Plugin else "filter"}">\n'
        XML += f"    <label>{EncodedLabel}</label>\n    <icon>{utils.encode_XML(Icon)}</icon>\n"
        if Plugin:
            _, Mode, MediaType = Rules[0]
            Params = urlencode({"mode": Mode, "mediatype": MediaType,
                                "libraryname": Tag or LibraryName or "unknown", "server": self.ServerData["ServerId"]})
            XML += f"    <path>{utils.encode_XML(PLUGIN_PATH + Params)}</path>\n"
            if len(Options) == 3 and Options[2]:
                XML += "    <group/>\n"
        else:
            Sort, UseLimit, Group = Options
            XML += f"    <content>{Content}</content>\n"
            if len(Rules) > 1:
                XML += "    <match>all</match>\n"
            for Field, Operator, *Rule in Rules:
                Prefix = f'    <rule field="{Field}" operator="{Operator}"'
                if not Rule:
                    XML += f"{Prefix}/>\n"
                elif isinstance(Rule[0], tuple):
                    XML += f"{Prefix}>\n"
                    XML += "".join(f"        <value>{utils.encode_XML(Value)}</value>\n" for Value in Rule[0])
                    XML += "    </rule>\n"
                else:
                    Value = Tag if Rule[0] == "LIBRARYTAG" else Rule[0]
                    XML += f"{Prefix}>{utils.encode_XML(Value)}</rule>\n"
            if len(Sort) == 2:
                XML += f'    <order direction="{Sort[0]}">{Sort[1]}</order>\n'
            elif Sort:
                XML += f"    <order>{Sort[0]}</order>\n"
            if UseLimit:
                XML += f"    <limit>{utils.maxnodeitems * LimitFactor}</limit>\n"
            if Group:
                XML += f"    <group>{Group}</group>\n"

        write_node(Folder, f"{Filename}.xml", XML + "</node>")

    def restore_playlist_nodes(self):
        ServerId = self.ServerData["ServerId"]
        if ServerId not in utils.DatabaseFiles:
            return
        EmbyDB = dbio.DBOpenRO(ServerId, "playlist_nodes")
        try:
            Playlists = EmbyDB.get_Records_by_EmbyType("Playlist")
        finally:
            dbio.DBCloseRO(ServerId, "playlist_nodes")
        for ItemId, _, _, Icon, LinkedIds, Name in Playlists:
            self.update_playlist_nodes(ItemId, Name, Icon, LinkedIds)

    def update_playlist_nodes(self, ItemId, Name, Icon, LinkedIds):
        Filename = f"{self.ServerData['ServerId']}_{ItemId}"
        Audio, _, _, _, MusicVideos = (LinkedIds or ";;;;").split(";")[:5]
        for Folder, HasItems, Content, Rule, DefaultIcon in (
            (PLAYLIST_NODE_FOLDERS[0], Audio, "songs", ("comment", "contains", f"EmbyPlaylistId-{ItemId}"), "DefaultMusicSongs.png"),
            (PLAYLIST_NODE_FOLDERS[1], MusicVideos, "musicvideos", ("tag", "is", Name), "DefaultMusicVideos.png"),
        ):
            if HasItems:
                Node = (Filename, Name, Icon or DefaultIcon, Content, (Rule,), ("ascending", "track"), False, False)
                self.set_synced_node(Folder, Filename, Node, Name, "", ItemId)
            elif xbmcvfs.exists(f"{Folder}{Filename}.xml"):
                utils.delFile(f"{Folder}{Filename}.xml")

    def delete_playlist_nodes(self, ItemId):
        for Folder in PLAYLIST_NODE_FOLDERS:
            utils.delFile(f"{Folder}{self.ServerData['ServerId']}_{ItemId}.xml")

    def musicgenre_folder(self, LibraryId, Media):
        if LibraryId not in self.ViewItems:
            return None
        Name, Content, _ = self.ViewItems[LibraryId]
        if Media == "music":
            if Content == "mixed":
                Content = "music"
            if Content not in ("music", "audiobooks", "podcasts"):
                return None
        elif Content != "musicvideos":
            return None
        return f"special://profile/library/{Media}/emby_{Content}_{utils.valid_Filename(Name)}/genrenodes/"

    def update_musicgenre_node(self, LibraryId, Media, ItemId, Name, Icon):
        Folder = self.musicgenre_folder(LibraryId, Media)
        if not Folder:
            return
        LibraryName = self.ViewItems[LibraryId][0]
        Content, Rule, Tag = ("artists", "disambiguation", f"EmbyLibraryId-{LibraryId}") if Media == "music" else (
            "musicvideos", "tag", LibraryName)
        Filename = f"{utils.valid_Filename(Name)}-{ItemId}"
        Node = (Filename, Name, Icon or "DefaultGenre.png", Content, ((Rule, "is", "LIBRARYTAG"),
                ("genre", "is", Name)), ("ascending", "title"), False, False)
        write_index(Folder, utils.Translate(33730), "DefaultGenre.png", 9999)
        self.set_synced_node(Folder, Filename, Node, LibraryName, Tag, genre_node_order(Name))

    def delete_musicgenre_node(self, LibraryId, Media, ItemId, Name):
        Folder = self.musicgenre_folder(LibraryId, Media)
        if Folder and Name:
            utils.delFile(f"{Folder}{utils.valid_Filename(Name)}-{ItemId}.xml")

    def restore_musicgenre_nodes(self):
        ServerId = self.ServerData["ServerId"]
        if ServerId not in utils.DatabaseFiles or not any(Item[2] == "MusicGenre" for Item in self.LibrarySynced):
            return
        EmbyDB = dbio.DBOpenRO(ServerId, "musicgenre_nodes")
        try:
            Genres = EmbyDB.get_Records_by_EmbyType("MusicGenre")
        finally:
            dbio.DBCloseRO(ServerId, "musicgenre_nodes")

        for Index, Media in enumerate(("music", "video")):
            if Media not in utils.DatabaseFiles:
                continue
            SyncedLibraries = {str(LibraryId) for LibraryId, _, ItemType, Databases in self.LibrarySynced
                               if ItemType == "MusicGenre" and Media in Databases.split(",")
                               and self.musicgenre_folder(str(LibraryId), Media)}
            if not SyncedLibraries:
                continue
            KodiDB = dbio.DBOpenRO(Media, "musicgenre_nodes")
            try:
                for ItemId, KodiIds, _, LibraryIds, Icon in Genres:
                    KodiId = (KodiIds or ";").split(";")[Index]
                    Libraries = (LibraryIds or ";").split(";")[Index].split(",")
                    if KodiId and any(LibraryId in SyncedLibraries for LibraryId in Libraries):
                        Name = KodiDB.get_genre_name(KodiId)
                        if Name:
                            for LibraryId in Libraries:
                                if LibraryId in SyncedLibraries:
                                    self.update_musicgenre_node(LibraryId, Media, ItemId, Name, Icon)
            finally:
                dbio.DBCloseRO(Media, "musicgenre_nodes")

    def update_views(self):
        Data = self.API.get_views()

        if 'Items' in Data:
            Libraries = Data['Items']
        else:
            return

        for library in Libraries:
            if library['Type'] == 'Channel':
                continue

            IconPath = ""

            library['ContentType'] = library.get('CollectionType', "mixed")

            if "Primary" in library["ImageTags"]:
                IconPath = utils.image_url(self.ServerData['ServerId'], library['Id'], 'Primary', library['ImageTags']['Primary'], "Library")

            self.ViewItems[library['Id']] = [utils.decode_XML(library['Name']), library['ContentType'], IconPath]

    def delete_node_by_id(self, LibraryId):
        if LibraryId not in self.ViewItems:
            return

        Name, LibraryType, _ = self.ViewItems[LibraryId]
        if LibraryType == "mixed":
            ContentTypes = ("movies", "tvshows", "music")
        elif LibraryType == "homevideos":
            ContentTypes = ("movies",)
        elif LibraryType == "playlists":
            Name = "Playlists"
            ContentTypes = ("playlistsaudio", "playlistsvideo")
        else:
            ContentTypes = (LibraryType,)

        for ContentType in ContentTypes:
            Media = "music" if utils.ContentTypes.get(ContentType) == "audio" else "video"
            Filename = f"emby_{ContentType}_{utils.valid_Filename(Name)}"
            Folder = f"special://profile/library/{Media}/{Filename}/"
            if LibraryType == "playlists":
                _, Files = xbmcvfs.listdir(Folder)
                for File in Files:
                    if File.startswith(f"{self.ServerData['ServerId']}_") and File.endswith(".xml"):
                        utils.delFile(Folder + File)
            else:
                utils.delFolder(Folder)


def genre_node_order(Name):
    if Name == "--NO INFO--":
        return 0
    Name = Name.lower().replace("the ", "").replace("der ", "").replace("die ", "").replace("das ", "")
    Alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    return int("".join(f"{Alphabet.find(Letter) + 2:02d}" for Letter in Name[:4].ljust(4)))


def write_index(Folder, Label, Icon, Order=0):
    XML = XML_HEADER + f'<node order="{Order}">\n'
    XML += f"    <label>{utils.encode_XML(Label)}</label>\n    <icon>{utils.encode_XML(Icon)}</icon>\n</node>"
    write_node(Folder, "index.xml", XML)


def write_node(Folder, Filename, XML):
    Path = f"{Folder}{Filename}"
    if not xbmcvfs.exists(Path) or utils.readFileString(Path) != XML:
        utils.mkDir(Folder)
        utils.writeFile(Path, XML.encode("utf-8"))
