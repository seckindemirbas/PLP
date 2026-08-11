import re
import sys
from pathlib import Path


__all__ = ('get_version',)


_REGEX_VERSION = re.compile(r'\s*version\s*=\s*["\']([.0-9a-z-+]+)["\']\s*$')
FALLBACK_VERSION = '0.0.0'

pyver = sys.version_info[:2]
if pyver <= (3, 7):
    import importlib_metadata
else:
    import importlib.metadata as importlib_metadata


def get_version(package_name: str, looked_path: Path) -> str:
    """
    Retrieve version string for your project.

    :param package_name: Your package's name.
    :type package_name: str
    :param looked_path: Folder where your project's pyproject.toml resides.
    :type looked_path: pathlib.Path

    :return: string of version, default to "0.0" if the information cannot be parsed.
    :rtype: str
    """
    # Poetry doesn't include pyproject.toml file to distribution package,
    # so, if we see that file, its mean that the package is imported
    # from development folder.
    filepath = looked_path / 'pyproject.toml'
    if filepath.exists():
        for line in filepath.open():
            found = _REGEX_VERSION.match(line)
            if found:
                return found.group(1)
        return FALLBACK_VERSION
    try:
        return importlib_metadata.version(package_name)
    except importlib_metadata.PackageNotFoundError:
        pass
    return FALLBACK_VERSION
