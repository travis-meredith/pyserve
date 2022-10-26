
from __future__ import annotations
import warnings

from pyserve.client import Client, ClientNotConnectedError

__all__: list[str] = ["RequestManagerServer", "RequestFunction"]

from typing import Callable, cast

from .address import Address
from .server import Server, ServerError, TickCallBack
from .socketprotocol import Packet, SocketProtocol, StrictPacket

class RequestManagerBase:

    _request_header_string: str
    _protocol: SocketProtocol
    _timeout: float
    _address: Address
    requests: dict[str, RequestFunction]

    def __init__(self, *, request_header_string: str="RequestType"):
        self._request_header_string = request_header_string
        self.requests = {}

    def subscribe(self, request_name: str, function: RequestFunction):
        """Add the given requestName and function to the list of valid requests
        and will call function whenever a request of type requestName is given.
        Note that the function given *must* return a dict that can be serialised
        by the protocol given.

        Raises:
            KeyError:
                when requestName is already occupied by a request definition
                use unsubscribe to remove a request definition
        """
        if request_name in self.requests:
            raise KeyError(f"Cannot subscribe function {function} to name {request_name} because "
                           f"the name is already used")
        self.requests[request_name] = function

    def unsubscribe(self, request_name: str, function: RequestFunction):
        """Removes the requestName from the list of valid requests. If a function
        is given, a stricter version is used where the function assigned to requestName
        must be equal to the given function.
        
        Raises:
            KeyError:
                when requestName is not a request that already exists

            ValueError:
                when function does not match the function attatched to the requestName being
                removed
        """
        if request_name not in self.requests:
            raise KeyError(f"Cannot unsubscribe name {request_name} as it is not subscribed")
        if function is None or function == self.requests[request_name]:
            del self.requests[request_name]
        else:
            raise ValueError(f"Optional function {function} check does not match the function "
                             f"{self.requests[request_name]} for request name {request_name}")

    def post(self, request_name: str, packet: StrictPacket) -> Packet:
        """Posts request requestName with the data obtained from a packet sent
        as Kwargs to the subscribed function. 
        """
        if request_name not in self.requests:
            return None
        return self.requests[request_name](packet)


class RequestManagerServer(RequestManagerBase, Server):
    
    def __init__(self, address: Address, *,
                protocol: SocketProtocol,
                request_header_string: str="RequestType",
                timeout: float=10.
    ):
        Server.__init__(self,
            address, 
                protocol=protocol, 
                tickcallback=cast(TickCallBack, self.__class__._handle_request),  
                timeout=timeout
            )
        RequestManagerBase.__init__(self, request_header_string=request_header_string)

    def reply(self, client: Address, response: StrictPacket):
        try:
            self.send(client, response)
        except (ServerError, KeyError) as e:
            warnings.warn(f"Server {self} tried to send to client {client} resp {response} but failed due to {e}")

    @staticmethod
    def _handle_request(server: RequestManagerServer, addr: Address, packet: Packet):
        if packet is None:
            return
        header = cast(str, packet[server.request_header_string])
        packet["addr"] = cast(list, addr)
        resp = server.post(header, packet)
        server.reply(addr, cast(StrictPacket, resp))

    @property
    def request_header_string(self) -> str:
        return self._request_header_string
   

RequestFunction = Callable[[Packet], StrictPacket]
