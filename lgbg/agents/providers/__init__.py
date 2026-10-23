"""Provider adapters behind one narrow seam (PRD-v2 FR-5.1)."""

from lgbg.agents.providers.base import (
    SAMPLING_MAX,
    Completion,
    CompletionConfig,
    Message,
    Provider,
    ProviderError,
    ProviderTimeoutError,
    Role,
    Sampling,
    ToolCall,
    ToolSpec,
    Usage,
)
from lgbg.agents.providers.mock import (
    Behaviour,
    MockProvider,
    MockScriptError,
)

__all__: list[str] = [
    "SAMPLING_MAX",
    "Behaviour",
    "Completion",
    "CompletionConfig",
    "Message",
    "MockProvider",
    "MockScriptError",
    "Provider",
    "ProviderError",
    "ProviderTimeoutError",
    "Role",
    "Sampling",
    "ToolCall",
    "ToolSpec",
    "Usage",
]
