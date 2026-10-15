"""Prompt artefacts and their hashes (PRD-v1 FR-19.3).

A prompt is a file a game ships, and a run that used it records *which* file it was: the header
carries a hash per prompt, so a record can be read years later and still say what the players were
told. Nothing here knows what a prompt says - hashing is the whole of it - and nothing here decides
which files a game has: that is the game's own declaration.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Final

ALGORITHM: Final[str] = "sha256"
"""The hash the header records, pinned by the header format rather than by this module."""


def digest(text: str) -> str:
    """The hash of one prompt, in the form a record carries it: lowercase hexadecimal."""
    return hashlib.new(ALGORITHM, text.encode("utf-8")).hexdigest()


def hashes_of(files: Mapping[str, Path]) -> dict[str, str]:
    """The hash of each named prompt file, in name order, which is what a config carries."""
    return {name: digest(path.read_text(encoding="utf-8")) for name, path in sorted(files.items())}
