"""Playback ordering and the last episode's choice, independent of source ownership."""
import re
import threading

_Tag = re.compile(r'\[([^\[\]]+)\]')
_Lock = threading.Lock()
_LastChoice = None


def source_info(Source):
    return Source if isinstance(Source, dict) else Source[0]


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
    Path = Path.split('|', 1)[0]
    return next((Source for Source in Sources if (source_info(Source).get('Path') or '').split('|', 1)[0] == Path), Sources[0])
