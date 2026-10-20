"""Host injection for memory tools; no dependency on a particular memory implementation."""

from shared_contracts.protocols import MemoryReader

_reader: MemoryReader | None = None


def set_memory_reader(reader: MemoryReader | None) -> None:
    global _reader
    _reader = reader


def get_memory_reader() -> MemoryReader | None:
    return _reader
