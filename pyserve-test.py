
from __future__ import annotations

__all__: list[str] = []

import random
import threading
import time
import unittest
from typing import cast

from pyserve import (Address, Client, ClientNotConnectedError, Packet,
                     PacketMalformedError, RequestManagerServer, Server,
                     ServerError, StrictPacket, load_protocol, socketprotocol)

HOST_IP = "127.0.0.1"
TARGET_IP = "127.0.0.1"
TEST_PROTOCOL = "msgpack"

PORT = 31776

def gport():
    global PORT
    return PORT

SUPER_PACKET: StrictPacket = {
    "str": "string",
    "int": 2,
    "float": 52.1,
    "list[int]": [1, 5, 2, 4, 6],
    "list[str, int, float]": ["test", 5, 532.25],
    "dict[str, int]": {"1": 1, "2": 2},
    "127": 52
}

DELAY: float = 0.

def response(server: Server, addr: Address, packet: StrictPacket):
    server.send(addr, packet)

class TestServer(Server):

    def __init__(self, address: Address):
        super().__init__(address, 
                        protocol=load_protocol(TEST_PROTOCOL),
                        tickcallback=response
                        )

class TestClient(Client):

    _x: int

    def __init__(self, address: Address):
        super().__init__(address,
                        protocol=load_protocol(TEST_PROTOCOL),
                        )


def test_request(packet: Packet) -> Packet:
    return packet

class CommsTest(unittest.TestCase):

    def test_request(self):

        HOST = Address(HOST_IP, gport())
        CLIENT = Address(TARGET_IP, gport())
        packet = SUPER_PACKET
        server = TestServer(HOST)
        client = TestClient(CLIENT)

        with server.operate():
            with client.connect():
                recv = client.request(packet)
                self.assertEqual(packet, recv)

    def test_requests(self):

        HOST = Address(HOST_IP, gport())
        CLIENT = Address(TARGET_IP, gport())
        packet = SUPER_PACKET
        server = TestServer(HOST)
        client = TestClient(CLIENT)

        with server.operate():
            time.sleep(DELAY)
            with client.connect():
                time.sleep(DELAY)
                for i in range(24):
                    data = client.request(packet)
                    self.assertEqual(data, packet)
                    packet["127"] += i

    def test_requests_diff(self):

        HOST = Address(HOST_IP, gport())
        CLIENT = Address(TARGET_IP, gport())
        packet = SUPER_PACKET
        server = TestServer(HOST)
        client = TestClient(CLIENT)

        with server.operate():
            time.sleep(DELAY)
            with client.connect():
                time.sleep(DELAY)
                for i in range(24):
                    data = client.request(packet)
                    self.assertEqual(data, packet)
                    packet[f"127{i}"] = i ** 2

    def test_large_request(self):

        HOST = Address(HOST_IP, gport())
        CLIENT = Address(TARGET_IP, gport())
        packet = {f"{i}": i + 0.5 for i in range(240)}
        server = TestServer(HOST)
        client = TestClient(CLIENT)
        
        with server.operate():
            time.sleep(DELAY)
            with client.connect():
                time.sleep(DELAY)
                data = client.request(packet)
                self.assertEqual(data, packet)

    def n_client_random_test(self, n: int, r: int):

        HOST = Address(HOST_IP, gport())
        CLIENT = Address(TARGET_IP, gport())
        server = TestServer(HOST)
        clients = [TestClient(CLIENT) for _ in range(n)]

        with server.operate():
            time.sleep(DELAY)

            random.shuffle(clients)

            for client in clients:
                client.connect()

            random.shuffle(clients)

            for i, client in enumerate(clients):
                client._x = i
                client.send(SUPER_PACKET | {"id": i})

            random.shuffle(clients)

            for i, client in enumerate(clients):
                packet = client.recv()
                self.assertEqual(packet["id"], client._x)
                client.close()


    def n_client_test(self, n: int, r: int):

        HOST = Address(HOST_IP, gport())
        CLIENT = Address(TARGET_IP, gport())
        server = TestServer(HOST)
        clients = [TestClient(CLIENT) for _ in range(n)]

        def do_requests(client: TestClient):
            with client.connect():
                time.sleep(DELAY)
                for _ in range(r):
                    self.assertEqual(client.request(SUPER_PACKET), SUPER_PACKET)

        with server.operate():
            time.sleep(DELAY)
            for client in clients:
                do_requests(client)

    def test_client_disconnect(self):

        HOST = Address(HOST_IP, gport())
        CLIENT = Address(TARGET_IP, gport())
        server = TestServer(HOST)
        clientdc = TestClient(CLIENT)
        clientworking = TestClient(CLIENT)

        with server.operate():
            time.sleep(DELAY)
            with clientdc.connect():
                clientdc.send(SUPER_PACKET)
            with clientworking.connect():
                packet = clientworking.request(SUPER_PACKET)
                self.assertEqual(packet, SUPER_PACKET)

    def test_server_stable_after_bad_packet(self):

        HOST = Address(HOST_IP, gport())
        CLIENT = Address(TARGET_IP, gport())
        server = TestServer(HOST)
        clientbad = TestClient(CLIENT)
        clientworking = TestClient(CLIENT)

        with server.operate():

            with clientbad.connect():
                clientbad.sock.send(bytes([100, 4, 12, 42, 254, 1]))

            time.sleep(DELAY)

            with clientworking.connect():
                packet = clientworking.request(SUPER_PACKET)
                self.assertEqual(packet, SUPER_PACKET)

    def test_client_raises_exception_when_bad_packet_sent(self):

        HOST = Address(HOST_IP, gport())
        CLIENT = Address(TARGET_IP, gport())
        server = TestServer(HOST)
        client = TestClient(CLIENT)

        with server.operate():

            if TEST_PROTOCOL != "pickle":
                with client.connect():
                    with self.assertRaises(PacketMalformedError):
                        client.send(TestClient)

                    with self.assertRaises(PacketMalformedError):
                        client.send(SUPER_PACKET | {"fail": TestClient})

    def test_client_message_when_not_connected(self):
        
        HOST = Address(HOST_IP, gport())
        CLIENT = Address(TARGET_IP, gport())
        server = TestServer(HOST)
        client = TestClient(CLIENT)

        with server.operate():
            with self.assertRaises(ClientNotConnectedError):
                client.send({1: 5})

            with self.assertRaises(ClientNotConnectedError):
                client.recv()

            with client.connect():
                packet = client.request(SUPER_PACKET)
                self.assertEqual(packet, SUPER_PACKET)

    def test_server_send_to_closed_client(self):

        HOST = Address(HOST_IP, gport())
        CLIENT = Address(TARGET_IP, gport())
        server = TestServer(HOST)
        client = TestClient(CLIENT)

        with server.operate():

            with client.connect():
                packet = client.request(SUPER_PACKET)
                for conn in server._clients:
                    clientConn = conn
                self.assertEqual(packet, SUPER_PACKET)

            server.send(clientConn, SUPER_PACKET)


    def test_server_state_management(self):
        
        HOST = Address(HOST_IP, gport())
        CLIENT = Address(TARGET_IP, gport())
        server = TestServer(HOST)
        client = TestClient(CLIENT)

        with server.operate():

            with self.assertRaises(ServerError):
                server.operate()

            with client.connect():
                packet = client.request(SUPER_PACKET)
                self.assertEqual(packet, SUPER_PACKET)

    def test_server_error_when_address_invalid(self):

        with self.assertRaises(ServerError):
            server = TestServer(Address("", ""))
            server.close()
        
        with self.assertRaises(ServerError):
            server = TestServer(Address())
            server2 = TestServer(Address())

        server.close()

    def test_001x_client(self):
        self.n_client_test(1, 16)

    def test_002x_client(self):
        self.n_client_test(2, 8)

    def test_004x_client(self):
        self.n_client_test(4, 4)

    def test_016x_client(self):
        self.n_client_test(16, 1)

    def test_064x_client(self):
        self.n_client_test(64, 4)

    def test_512x_client(self):
        self.n_client_test(512, 4)

    def test_random_001x_client(self):
        self.n_client_random_test(1, 16)

    def test_random_002x_client(self):
        self.n_client_random_test(2, 8)

    def test_random_004x_client(self):
        self.n_client_random_test(4, 4)

    def test_random_016x_client(self):
        self.n_client_random_test(16, 1)

    def test_random_064x_client(self):
        self.n_client_random_test(64, 4)

    def test_random_512x_client(self):
        self.n_client_random_test(512, 4)

class RequestTest(unittest.TestCase):
    
    def test_request_default(self):

        HOST = Address(HOST_IP, gport())
        CLIENT = Address(TARGET_IP, gport())
        manager = RequestManagerServer(HOST, protocol=load_protocol(TEST_PROTOCOL))
        manager.subscribe("Test", test_request)
        with manager.operate():
            time.sleep(DELAY)
            client = Client(CLIENT, protocol=load_protocol(TEST_PROTOCOL))
            with client.connect():
                time.sleep(DELAY)
                client.send({"RequestType": "Test", "data": 1})
                recv = client.recv()
                del recv["addr"]
                self.assertEqual(recv, {"RequestType": "Test", "data": 1})

    @staticmethod
    def log_and_add_request(packet) -> dict:
        kw1, kw2 = packet["kw1"], packet["kw2"]
        return {"response": kw1 + kw2}

    def n_request_test(self, n: int, r: int):

        HOST = Address(HOST_IP, gport())
        CLIENT = Address(TARGET_IP, gport())
        server = RequestManagerServer(HOST, protocol=load_protocol(TEST_PROTOCOL))
        server.subscribe("TestRequest", RequestTest.log_and_add_request)
        clients = [Client(CLIENT, protocol=load_protocol(TEST_PROTOCOL)) for _ in range(n)]

        def do_requests(client: Client):
            with client.connect():
                for i in range(r):
                    client.send(cast(StrictPacket, {"RequestType": "TestRequest", "kw1": i, "kw2": 4} | SUPER_PACKET))
                    self.assertEqual(client.recv(), {"response": i + 4})

        with server.operate():
            for client in clients:
                do_requests(client)

    def test_01x_request_response(self):
        self.n_request_test(1, 16)

    def test_02x_request_response(self):
        self.n_request_test(2, 8)
        
    def test_04x_request_response(self):
        self.n_request_test(4, 4)

    def test_16x_request_response(self):
        self.n_request_test(16, 1)

    def test_64x_request_response(self):
        self.n_request_test(64, 4)

    def test_512x_request_response(self):
        self.n_request_test(512, 4)

class ThreadTest(unittest.TestCase):
    def test_thread_count(self):
        #try:
        #    call(lambda: print(nothing))
        #except Exception as e:
        #    print(e, e.args, e.__traceback__)
        self.assertEqual(threading.active_count(), 1, "if thread count isn't 1, then a thread leak has occured")     

def main():
    unittest.main()

if __name__ == "__main__":
    main()
