"""Playback ordering and the last episode's choice, independent of source ownership."""
import re
import threading
from urllib.parse import quote, unquote, urlsplit

_Tag = re.compile(r'\[([^\[\]]+)\]')
_Lock = threading.Lock()
_LastChoice = None


def source_info(Source):
    return Source if isinstance(Source, dict) else Source[0]


def http_iso_directory(Path):
    LowerPath = Path.lower()
    if not LowerPath.startswith(('http://', 'https://')) or '.iso' not in LowerPath:
        return ''

    # Kodi checks the filename before HTTP URL and protocol options.
    Address = re.split(r'[?;#|]', Path, maxsplit=1)[0]
    try:
        URL = urlsplit(Address)
    except ValueError:
        return ''
    if URL.netloc and URL.path.lower().endswith('.iso'):
        return Address[:Address.rfind('/') + 1]
    return ''


def disc_source_path(Path):
    # Decode one host per wrapper, leaving the HTTP URL's own escaping intact.
    for Prefix in ('bluray://', 'udf://'):
        if Path.startswith(Prefix):
            Path = unquote(Path[len(Prefix):].split('/', 1)[0])
    return Path


def comparable_http_path(Path):
    # The fork can escape raw spaces/non-ASCII and lowercase the scheme before AVStart.
    # Keep any existing escapes, path case and signed parameters intact.
    Scheme, Separator, Address = Path.split('|', 1)[0].partition('://')
    return Scheme.lower() + Separator + re.sub(r'[ \x80-\U0010ffff]', lambda Part: quote(Part[0]).lower(), Address)


def unique_http_source_index(Sources, Path):
    Path = comparable_http_path(Path)
    Matches = [Index for Index, Source in enumerate(Sources)
               if comparable_http_path(source_info(Source).get('Path') or '') == Path]
    return Matches[0] if len(Matches) == 1 else None


def version_tag(Source):
    Match = _Tag.search(source_info(Source).get('Name') or '')
    return Match.group(1).casefold() if Match else ''


def sort_sources(Sources):
    def key(Source):
        Info = source_info(Source)
        Name = (Info.get('Name') or '').strip().casefold()
        return (version_tag(Source) != 'default', Name, str(Info.get('Id', Info.get('MediaSourceId', ''))))
    return sorted(Sources, key=key)


def highest_resolution_index(Sources):
    HighestIndex = 0
    HighestWidth = 0
    for Index, Source in enumerate(Sources):
        Streams = Source.get('KodiStreams', {}).get('Video', ()) if isinstance(Source, dict) else Source[1]
        if not Streams:
            continue

        Stream = Streams[0]
        try:
            Width = int(Stream.get('Width', Stream.get('width')) or 0)
        except (TypeError, ValueError, OverflowError):
            continue

        if Width > HighestWidth:
            HighestIndex = Index
            HighestWidth = Width

    return HighestIndex


def clear_choice():
    global _LastChoice
    with _Lock:
        _LastChoice = None


def recall_choice(Sources, Context, clear_mismatch=True):
    global _LastChoice
    with _Lock:
        if not Sources or not Context or not _LastChoice or _LastChoice[0] != Context:
            if clear_mismatch:
                _LastChoice = None
            return None
        _, Tag, Index = _LastChoice

    if Tag:
        for Position, Source in enumerate(Sources):
            if version_tag(Source) == Tag:
                return Position
    return Index if Index < len(Sources) else 0


def remember_choice(Sources, Index, Context):
    global _LastChoice
    with _Lock:
        _LastChoice = (Context, version_tag(Sources[Index]), Index) if Context else None


def playing_source(Sources, Path, SourceId=None):
    if SourceId:
        for Source in Sources:
            if source_info(Source).get('Id') == SourceId:
                return Source
    # Kodi protocol options affect transport, not the underlying source identity.
    if http_iso_directory(Path):
        Index = unique_http_source_index(Sources, Path)
        if Index is not None:
            return Sources[Index]
    Path = Path.split('|', 1)[0]
    return next((Source for Source in Sources if (source_info(Source).get('Path') or '').split('|', 1)[0] == Path), Sources[0])
