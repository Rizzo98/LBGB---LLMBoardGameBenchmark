"""Game plugins. Each plugin is self-contained and imports only lgbg.core.

Importing a plugin registers it (ARCHITECTURE.md section 7.4: explicit import for in-repo
games, entry points for external ones), so importing this package is enough to make every
game that ships with the engine available.

In-repo plugins are imported here as they are implemented; Catan arrives with the board and
state cards.
"""

__all__: list[str] = []
