"""Built-in size, format and quality limits for on-demand artwork redirects."""

QUALITY = 90
PROFILES = {
    "poster": (480, 720, "jpg"),
    "person": (480, 720, "jpg"),
    "square": (720, 720, "jpg"),
    "library": (1920, 1080, "jpg"),
    "landscape": (960, 540, "jpg"),
    "backdrop": (1920, 1080, "jpg"),
    "logo": (1000, 400, "png"),
    "disc": (720, 720, "png"),
    "studio": (640, 360, "png"),
    "chapter": (640, 360, "jpg"),
}
IMAGE_TYPES = {"p": "Primary", "l": "Logo", "d": "Disc", "t": "Thumb", "B": "Backdrop", "c": "Chapter"}
SOURCE_CODES = {
    "Primary": "p", "SeriesPrimary": "p", "AlbumPrimary": "p",
    "AlbumArtists": "p", "ArtistItems": "p", "Logo": "l", "ParentLogo": "l",
    "Disc": "d", "Thumb": "t", "Backdrop": "B", "ParentBackdrop": "B", "Chapter": "c",
}


def profile_for(ItemType, ImageType):
    if ImageType in ("Backdrop", "ParentBackdrop"):
        return "backdrop"
    if ImageType in ("Logo", "ParentLogo"):
        return "logo"
    if ImageType == "Disc":
        return "disc"
    if ImageType == "Chapter":
        return "chapter"
    if ImageType == "SeriesPrimary":
        return "poster"
    if ImageType in ("AlbumPrimary", "AlbumArtists", "ArtistItems"):
        return "square"
    if ItemType == "Studio":
        return "studio"
    if ItemType == "Person":
        return "person"
    if ItemType == "Library":
        return "library"
    if ItemType in ("MusicArtist", "MusicAlbum", "Audio"):
        return "square"
    if ItemType == "Episode":
        return "landscape"
    return "poster"


def image_params(Profile, ImageTag):
    Width, Height, Format = PROFILES[Profile]
    Params = {"MaxWidth": Width, "MaxHeight": Height, "Quality": QUALITY,
              "Format": Format, "EnableImageEnhancers": False}
    if ImageTag and ImageTag != "noimage":
        Params["tag"] = ImageTag
    return Params
