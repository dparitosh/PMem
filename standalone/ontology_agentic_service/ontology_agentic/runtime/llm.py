from dataclasses import dataclass


@dataclass(slots=True)
class LLMResponse:
    content: str
    model: str = "noop"


class NoopLLMClient:
    """Placeholder interface for later LLM wiring.

    The default package is deterministic and does not require an LLM.
    """

    def complete(self, prompt: str) -> LLMResponse:
        return LLMResponse(content=prompt)
