
from __future__ import annotations

__all__: list[str] = ["ClientNotConnectedError", "Client"]

import socket
from contextlib import suppress
from enum import Enum
from typing import cast

from .address import Address
from .socketprotocol import SocketProtocol, StrictPacket


class ClientState(Enum):
    IDLE = 0
    CONNECTED = 1
    CLOSED = 2

class ClientNotConnectedError(Exception):
    pass

class Client:

    """Client represents a connection to a server. Connection may be to a local or 
    remote server. 

    Usage: // main thread context manager
        client = Client()
        with client.connect():
            client.send(dict)
            dict = client.recv()

    Usage: // main thread no context manager
        client = Client()
        client.connect()
        client.send(dict)
        dict = client.recv()
        client.close()

    Args:
    -- ip: address to connect to

    Kwargs:
    -- protocol: determines how to communicate with server (DefaultProtocol())
    -- timeout: amount of time before timeout triggered on socket (10.)
    """

    _address: Address
    _protocol: SocketProtocol
    _socket: socket.socket
    _state: ClientState
    timeout: float

    def __init__(self, address: Address, *,
                protocol: SocketProtocol,
                timeout: float=10.
    ):
        self._address = address
        self._socket = socket.socket()
        self._protocol = protocol
        self._state = ClientState.IDLE
        self.timeout = timeout
        
    def __enter__(self):
        pass

    def __exit__(self, *eargs):
        self.close()

    def close(self):
        """Set server state to closed and close the socket
        """
        self._state = ClientState.CLOSED
        self.sock.close()

    def connect(self) -> Client:
        """Connect to the server assigned in __init__ and 
        set state
        """
        self.sock.connect(self.address.astuple())
        self._state = ClientState.CONNECTED
        return self

    def request(self, packet: StrictPacket) -> StrictPacket:
        """Send StrictPacket packet over connected connection and
        then wait to return the server's response

        Raises:
            ClientNotConnectedError:
                when client is not connected
        """
        self.send(packet)
        return self.recv()

    def send(self, packet: StrictPacket):
        """Send StrictPacket packet over connected connection
        
        Raises:
            ClientNotConnectedError:
                when client is not connected
        """
        self._connected_check()
        self.protocol.send_message(self.sock, packet)

    def recv(self) -> StrictPacket:
        """Wait to recieve a StrictPacket over the connected
        connection
        
        Raises:
            ClientNotConnectedError:
                when client is not connected
        """
        self._connected_check()
        packet = None
        while packet is None:
            with suppress(ConnectionAbortedError, ConnectionResetError):
                packet = self.protocol.recv_message(self.sock)
            return cast(StrictPacket, packet)

    @property
    def address(self) -> Address:
        return self._address

    @property
    def protocol(self) -> SocketProtocol:
        return self._protocol

    @property
    def sock(self) -> socket.socket:
        return self._socket

    @property
    def state(self) -> ClientState:
        return self._state

    @property
    def closed(self) -> bool:
        return self.state == ClientState.CLOSED
    
    @property
    def connected(self) -> bool:
        return self.state == ClientState.CONNECTED

    def _connected_check(self) -> bool:
        if self.connected:
            return True
        raise ClientNotConnectedError(f"cannot perform operation because client {self} is in state {self.state}")
