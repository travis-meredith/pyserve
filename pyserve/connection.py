
__all__ = ["Connection"]

import socket
from queue import Queue

from .address import RawAddress
from .socketprotocol import SocketProtocol, StrictPacket


class Connection:
    """Connection object that exists between a socket and a server.
    These are owned by a Server instance 

    Usage:
        conn = Connection()
        with conn:
            conn.send()
            conn.recv()
    
    Usage:
        conn = Connection()
        try:
            conn.send()
            conn.recv()
        finally:
            conn.close()

    Usage:
        conn = Connection()
        with conn:
            conn.blocking_operate()

    Args:
    -- address: address to host server on

    Kwargs:
    -- protocol: determines how to serialise and deserialise packets
    -- timeout: amount of time before timeout triggered on a Connection

    """
    def __init__(self, 
            protocol: SocketProtocol, 
            connect: tuple[socket.socket, RawAddress], 
            queue: Queue):
        self.protocol = protocol
        self.conn, self.addr = connect
        self.queue = queue
        self.closed = False

    def __enter__(self):
        pass

    def __exit__(self, *eargs):
        self.close()

    def send(self, packet: StrictPacket) -> bool:
        """Send StrictPacket packet over this connections open
        socket unless the connection is closed and finally
        return whether the packet was sent or not
        """
        if self.closed:
            return False
        self.protocol.send_message(self.conn, packet)
        return True

    def close(self):
        """Close this connection and close the socket object
        encapsulated by it
        """
        self.closed = True
        self.conn.close()

    def recv(self):
        """Recieve on this socket (blocking) and put result to the server's
        queue and silently return if closed. Will add a None to the queue
        to indicate that the connection has died, if it has
        """
        if self.closed:
            # recv may be called once after the connection is closed if
            # it was closed by the parent server closing (state is not
            # thread safe so it's possible that "not self.closed" in 
            # blocking_operate is True and then becomes false by now)
            return
        try:
            data = self.protocol.recv_message(self.conn)
        except (ConnectionAbortedError, ConnectionResetError, OSError):
            # if the connection dies during the transmission of this packet
            # the connection is closed and a None is put on the Queue (to 
            # indicate that this connection's thread should end soon)
            self.queue.put((self.addr, None), block=True)
            self.close()
            return
        if data is None:
            # if that packet was malformed, a None is returned
            # so we want to do the same here as with a connection
            # error
            self.queue.put((self.addr, None), block=True)
            self.close()
            return
        # valid data
        self.queue.put((self.addr, data), block=True)

    def blocking_operate(self):
        while not self.closed:
            self.recv()
