
from socket import socket
from typing import Callable, Mapping, Protocol, Union

SerialisableElement = Union[None, bool, int, float, str, list, dict]

StrictPacket = dict[str, SerialisableElement]
Packet = Union[StrictPacket, None]

class SocketProtocol(Protocol):

    """Protocol that defines how custom SocketProtocols should be defined"""

    @staticmethod
    def send_message(sock: socket, packet: StrictPacket):
        ...
    
    @staticmethod
    def recv_message(sock: socket) -> Packet:
        ...

class PacketMalformedError(Exception):
    pass

def malformed_packet_wrap(function: Callable) -> Callable:
    def value_error_catch(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (ValueError, TypeError) as e:
            raise PacketMalformedError("Packet was malformed")
    return value_error_catch

class PluginModule:

    Plugin: SocketProtocol
    DefaultArgs: Mapping
