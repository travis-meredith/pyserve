
import json

from .plugin import SocketProtocol, malformed_packet_wrap

DefaultArgs = {
    "header_length":12,
    "encoding":"utf-8",
    "zero_string":"0"
}

class Plugin(SocketProtocol):
    send_message = malformed_packet_wrap(json.dumps)
    recv_message = malformed_packet_wrap(json.loads)
