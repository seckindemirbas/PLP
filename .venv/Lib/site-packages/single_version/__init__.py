from pathlib import Path

from .ver import get_version


__version__ = get_version('single_version', Path(__file__).parent.parent)
