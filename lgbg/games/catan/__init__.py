"""The Catan plugin: the reference implementation of the game plugin interface.

Importing this package registers the game under the name `catan` (ARCHITECTURE.md section
7.4: explicit import for in-repo games, entry points for games that ship separately).
"""

from lgbg.games.catan import game

__all__: list[str] = ["game"]
