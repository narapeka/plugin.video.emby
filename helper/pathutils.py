def is_native_path(path, container=""):
    path_lower = (path or "").lower()

    if container == "iso" or ".iso" in path_lower:
        return True

    if path_lower.startswith(("dav://", "davs://", "smb://", "nfs://", "ftp://", "file://")):
        return True

    if not path:
        return False

    if "://" in path:
        return False

    if path.startswith("/"):
        return True

    return len(path) >= 3 and path[0].isalpha() and path[1] == ":" and path[2] in ("\\", "/")
