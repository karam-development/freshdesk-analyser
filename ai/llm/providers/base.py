from abc import ABC, abstractmethod


class BaseLLMProvider(ABC):
    @abstractmethod
    def complete(self, request):
        raise NotImplementedError

    @abstractmethod
    def test_connection(self) -> bool:
        raise NotImplementedError

    def supports_vision(self) -> bool:
        return False

    def supports_json_mode(self) -> bool:
        return False

    def supports_tools(self) -> bool:
        return False
