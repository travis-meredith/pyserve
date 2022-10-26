
from __future__ import annotations

__all__ = ["Server", "ServerState", "ServerError", "TickCallBack"]

import socket
import threading
import time
from contextlib import suppress
from enum import Enum
from queue import Queue
from typing import Callable, Generator

from .address import Address
from .call import call
from .connection import Connection
from .socketprotocol import Packet, SocketProtocol, StrictPacket


class ServerError(Exception):
    pass

class ServerState(Enum):
    RUNNING = 0
    CLOSED = 1
    IDLE = 2
    CONNECTION_ON = 3

class Server:

    """Server that forms and controls connection and communication between itself
    and the client(s). Spawns Connections on different threads that add to a single
    Queue object to communicate with the Server's main thread (which may or may not 
    be the main thread of the program)

    Usage:
        with Server().operate():
            ... // main thread
    // Comms are done on the daemon thread spawned by operate

    Usage:
        Server().operate()
    // Comms are done on the main thread
    // which blocks until the server closes
    // (there is no built-in mechanism for this)

    Args:
    -- address: address to host server on

    Kwargs:
    -- protocol: determines how to serialise and deserialise packets\n
    -- timeout: amount of time before timeout triggered on a Connection\n
    -- tickcallback: function(server: Server, addr: Address, packet: StrictPacket)\n
    -- delay: time.sleep delay between polls

    Raises:
        ServerError:
            when supplied address cannot be bound

    """

    __address: Address
    _protocol: SocketProtocol
    _socket: socket.socket
    _state: ServerState
    _tickcallback: tuple[TickCallBack]
    _client_dict_lock: threading.Lock
    _clients: dict[Address, Connection]
    _queue: Queue[tuple[Address, Packet]]
    _threads: list[threading.Thread]
    _unjoined: list[threading.Thread]
    _unjoined_lock: threading.Lock
    delay: float

    def __init__(self, address: Address, *, 
                protocol: SocketProtocol,
                tickcallback: TickCallBack,
                timeout: float=10.,
                delay: float=0.000
    ):
        self.__address = address
        self._protocol = protocol
        self._socket = socket.socket()
        self._state = ServerState.IDLE
        self._tickcallback = (tickcallback,)
        self._client_dict_lock = threading.Lock()
        self._clients = {}
        self._queue = Queue()
        self._threads = []
        self._unjoined = []
        self._unjoined_lock = threading.Lock()
        self._timeout = timeout
        self.delay = delay
        self._connect()
        
    def __repr__(self) -> str:
        return f"Server ({self.__class__.__qualname__})"

    def __enter__(self):
        pass

    def __exit__(self, *eargs):
        self.close()

    def blocking_operate(self):
        """Block execution to operate server until closed
        
        Raises:
            ServerError:
                when server is already running or has already closed
        """
        self._operate_check()
        if self.state == ServerState.IDLE:
            self._nonblocking_accept_clients()
        self._blocking_operate()

    def operate(self) -> Server:
        """Operate server on new thread until closed and return
        self for use in context manager format (the prefered method)

        Raises:
            ServerError:
                when server is already running or has already closed
        """
        self._operate_check()
        self._start_thread(self.blocking_operate)
        while not self.running:
            time.sleep(self.delay)
        return self

    def send(self, address: Address, packet: StrictPacket):
        """Send StrictPacket packet over an active connection with
        Address address if open
        
        Raises:
            ServerError:
                ...
            KeyError:
                when there is no client at Address address
        """
        with self._client_dict_lock:
            self._clients[address].send(packet)

    def close(self):
        """Set server state to closed, tell all connections to close,
        and finally rejoin all instantiated threads for cleanup
        """
        self._state = ServerState.CLOSED
        self.sock.close()
        clients = list(self._clients.values())
        for conn in clients:
            conn.close()
        for thread in self._get_threads():
            thread.join()

    @property
    def address(self) -> Address:
        return self.__address

    @property
    def timeout(self) -> float:
        return self._timeout

    @timeout.setter
    def timeout(self, timeout: float):
        self._timeout = timeout
        self.sock.settimeout(timeout)

    @property
    def protocol(self) -> SocketProtocol:
        return self._protocol

    @property
    def sock(self) -> socket.socket:
        return self._socket

    @property
    def state(self) -> ServerState:
        return self._state

    @property
    def tickcallback(self) -> TickCallBack:
        return self._tickcallback[0]

    @property
    def closed(self) -> bool:
        return self.state == ServerState.CLOSED

    @property
    def running(self) -> bool:
        return self.state == ServerState.RUNNING

    def _connect(self):
        try:
            self.sock.bind(self.address.astuple())
            self.sock.listen()
            self.sock.settimeout(self.timeout)
        except (OSError, TypeError) as e:
            self.sock.close()
            raise ServerError(f"Server {self} ({self.__class__.__qualname__}) failed to bind to {self.address}\n"
                              f"Raised exception `{e}`")

    def _operate_check(self) -> bool:
        if self.closed or self.running:
            raise ServerError(f"Server {self} in state {self.state} cannot be operated on")
        return True

    def _tick(self):
        if not self._queue.empty():
            # although Queue.empty() does not guarantee that Queue.get()
            # returns a value threadsafely, no other thread is using Queue.get()
            # and so this is actually threadsafe anyway
            addr, packet = self._queue.get(block=True)
            self.tickcallback(self, addr, packet)
        else:
            # on an empty tick, join closed connection threads if there
            # exists any to join
            if len(self._unjoined) > 0:
                with self._unjoined_lock:
                    for thread in self._unjoined:
                        thread.join()
                    self._unjoined = []
            else:
                # if nothing at all has been done this tick on this thread,
                # wait for the set delay time to help the scheduler
                # (best performance comes from having no delay, however)
                time.sleep(self.delay)

    def _nonblocking_connect(self, connection: Connection):
        self._start_thread(lambda: self._blocking_connect(connection))

    def _nonblocking_accept_clients(self):
        self._start_thread(self._accept_clients)

    def _blocking_connect(self, connection: Connection):
        with connection:
            connection.blocking_operate()
        self._unjoined.append(threading.current_thread())

    def _blocking_operate(self):
        self._state = ServerState.RUNNING
        while not self.closed:
            self._tick()

    def _accept_clients(self):
        while not self.closed:
            with suppress(socket.timeout, OSError):
                connection = Connection(self.protocol, self.sock.accept(), self._queue)
                with self._client_dict_lock:
                    self._clients[connection.addr] = connection
                self._nonblocking_connect(connection)

    def _get_threads(self) -> Generator[threading.Thread, None, None]:
        yield from self._threads

    def _start_thread(self, function: Callable):
        self._threads.append(call(function))

TickCallBack = Callable[[Server, Address, StrictPacket], None]
