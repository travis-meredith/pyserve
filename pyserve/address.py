
from __future__ import annotations

__all__ = ["Address", "RawAddress"]

from dataclasses import astuple, dataclass, field
from typing import cast

RawAddress = tuple[str, int]

@dataclass(frozen=True)
class Address:

    """Encapsulated IP address. Can be converted to a RawAddress
    with Address.astuple() or dataclasses.astuple(Address).
    """

    addr: str=field(default="127.0.0.1")
    port: int=field(default=48_575)

    def astuple(self) -> RawAddress:
        return cast(RawAddress, astuple(self))

