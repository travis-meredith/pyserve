
import msgpack # type: ignore

from .plugin import SocketProtocol, malformed_packet_wrap

DefaultArgs = {
    "byteEncodingString":">LL",
    "infoBytes":8
}

class Plugin(SocketProtocol):
    send_message = malformed_packet_wrap(msgpack.dumps)
    recv_message = malformed_packet_wrap(msgpack.loads)
