from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class LLMMessage:
    role: str
    content: str


@dataclass
class LLMRequest:
    model: str
    messages: List[LLMMessage]
    max_tokens: int = 1024
    temperature: float = 0.0
    system: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str
    stop_reason: Optional[str] = None
    usage: LLMUsage = field(default_factory=LLMUsage)
    raw: Optional[Any] = None
