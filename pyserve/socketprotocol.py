
from __future__ import annotations

__all__ = ["load_protocol", "Packet", "StrictPacket", "SocketProtocol", "PacketMalformedError"]

import importlib
import json
import struct
from collections import namedtuple
from contextlib import suppress
from functools import lru_cache, partial, reduce
from socket import socket
from typing import Callable, Generator, NamedTuple, Sequence, Union, cast
from warnings import warn

from .protocols.plugin import (Packet, PacketMalformedError, PluginModule,
                               SocketProtocol, StrictPacket)

_SocketProtocol: NamedTuple = namedtuple("_SocketProtocol", ["send_message", "recv_message"])

MAX_PACKET_SIZE: int = 8_000_000_000

def _chop(seq: bytes, dist: int) -> Generator[bytes, None, None]:
    i = 0
    for end in range(dist, len(seq), dist):
        yield seq[i:end:]
        i = end
    yield seq[end:len(seq):]

def chop(seq: bytes, dist: int) -> list[bytes]:
    return list(_chop(seq, dist))

def make_binary_protocol(*, 
        encode_function: Callable, 
        decode_function: Callable, 
        byte_encoding_string: str, # struct pattern for the header
        info_bytes: int # amount of bytes to read off (must match the struct pattern)
        ) -> _SocketProtocol:

    """
    Create a SocketProtocol NamedTuple that defines socket-wise serialisation (in binary)
    for pyserve. 
    """

    def send_message(sock: socket, packet: StrictPacket):
        serialised = encode_function(packet)
        if len(serialised) > MAX_PACKET_SIZE:
            chopped = chop(serialised, MAX_PACKET_SIZE)
            for i in range(len(chopped) - 1):
                bytes_ = struct.pack(byte_encoding_string, len(chopped[i]), len(chopped) - i) + chopped[i]
                sock.send(bytes_)
            chunk = chopped[-1]
            bytes_ = struct.pack(byte_encoding_string, len(chunk), 1) + chunk
            sock.send(bytes_)
        else:
            bytes_ = struct.pack(byte_encoding_string, len(serialised), 0) + serialised
            sock.send(bytes_)

    def recv_message(sock: socket) -> Packet:
        lengthRaw = sock.recv(info_bytes)
        try:
            length, style = struct.unpack(byte_encoding_string, lengthRaw)
            if style == 0:
                pass
            elif style >= 1:
                raws = [sock.recv(length)]
                for _ in range(style - 1):
                    lengthRaw = sock.recv(info_bytes)
                    length, style = struct.unpack(byte_encoding_string, lengthRaw)
                    raws.append(sock.recv(length))
                return decode_function(reduce(lambda x, y: x + y, raws))
                #raws = [sock.recv(length)]
                #while style != 1:
                #    lengthRaw = sock.recv(infoBytes)
                #    length, style = struct.unpack(byteEncodingString, lengthRaw)
                #    raws.append(sock.recv(length))
                #return decode_function(reduce(lambda x, y: x + y, raws))
                #return decode_function(b"".join(raws))
        except struct.error:
            return None
        raw = sock.recv(length)
        try:
            return decode_function(raw)
        except PacketMalformedError:
            return None

    return _SocketProtocol(send_message, recv_message)

def make_string_protocol(*,
        encode_function: Callable,
        decode_function: Callable,
        header_length: int,
        encoding: str,
        zero_string: str
        ) -> _SocketProtocol:

    """
    Create a SocketProtocol NamedTuple that defines socket-wise serialisation (in utf-8)
    for pyserve. 
    """

    def send_message(sock: socket, packet: StrictPacket):
        serialised = encode_function(packet)
        msg = bytes(str(len(serialised)).rjust(header_length, zero_string), encoding)
        sock.send(msg)
        sock.sendall(bytes(serialised, encoding=encoding))

    def recv_message(sock: socket) -> Packet:
        length = str(sock.recv(header_length), encoding)
        if length == "":
            return None
        ilength = int(length)
        view = memoryview(bytearray(ilength))
        offset = 0
        while ilength - offset > 0:
            recvSize = sock.recv_into(view[offset::], ilength - offset)
            offset += recvSize
        return decode_function(view.tobytes())

    return _SocketProtocol(send_message, recv_message)

@lru_cache(maxsize=256)
def _load_protocol(protocol_name: str, sorted_args: tuple) -> SocketProtocol:

    kwargs = {key: value for key, value in sorted_args}

    if protocol_name in LOADED_PROTOCOLS:
        return cast(SocketProtocol, LOADED_PROTOCOLS[protocol_name](**kwargs))
    raise KeyError(f"Protocol {protocol_name} is not defined")

def load_protocol(protocol_name: str | Sequence[str] | None=None, **kwargs) -> SocketProtocol:

    sorted_args = tuple(sorted(kwargs.items()))

    if protocol_name is None:
        protocol_name = DEFAULT_PROTOCOL

    # single string given
    if isinstance(protocol_name, str):
        return _load_protocol(protocol_name.lower(), sorted_args)

    # list of protocols
    elif isinstance(protocol_name, list):
        for protocol in protocol_name:
            protocol = cast(str, protocol)
            with suppress(KeyError):
                return _load_protocol(protocol.lower(), sorted_args)

    raise KeyError(f"Protocol definition {protocol_name} could not be resolved to a valid protocol")

def load_any_protocol() -> SocketProtocol:
    for protocolname in sorted(LOADED_PROTOCOLS.keys()):
        try:
            return load_protocol(protocolname)
        except KeyError:
            continue
    raise KeyError("No protocols are loaded")

def _load_plugin(plugin: dict):

    try:
        plugin_route = plugin["packagename"]
        plugin_type = plugin["type"]
    except KeyError:
        warn(f"Plugin {plugin} is ill-defined (missing 'packagename' or 'type')")
        return

    try:
        module = cast(PluginModule, importlib.import_module(f".{plugin_route}", "pyserve.protocols"))
    except ImportError:
        warn(f"Plugin {plugin} (at .{plugin_route} in package pyserve.protocols) could not be found")
        return 
    
    try:
        protocol = cast(SocketProtocol, module.Plugin)
    except AttributeError:
        warn(f"Plugin {plugin} did not have required Plugin object")
        return

    try:
        kwargs = module.DefaultArgs
    except AttributeError:
        warn(f"Plugin {plugin} did not have required attribute DefaultArgs")
        return

    encode_function = protocol.send_message
    decode_function = protocol.recv_message

    if plugin_type == "str":
        LOADED_PROTOCOLS[pluginname] = partial(
            make_string_protocol,
                encode_function=encode_function,
                decode_function=decode_function,
                **kwargs
        )
    elif plugin_type == "bin":
        LOADED_PROTOCOLS[pluginname] = partial(
            make_binary_protocol,
                encode_function=encode_function,
                decode_function=decode_function,
                **kwargs
        )

LOADED_PROTOCOLS: dict[str, partial[_SocketProtocol]] = {}

try:
    with open("pyserve\\protocols\\plugins.json", "r") as f:
        plugins = json.load(f)
except FileNotFoundError:
    raise FileNotFoundError(f"Cannot find plugins.json in pyserve/protocols/")

for pluginname in plugins:
    _load_plugin(plugins[pluginname])

DEFAULT_PROTOCOL: tuple = (
    "msgpack",
    "json"
)
