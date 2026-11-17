"""A minimal MQTT 3.1.1 broker for tests.

Accepts connections on localhost, records CONNECT details (including the
last will) and every PUBLISH, answers SUBSCRIBE and PINGREQ, and can drop
all clients to simulate a broker restart. QoS 0 only, which is all the
add-on uses.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field

CONNECT, CONNACK, PUBLISH, SUBSCRIBE, SUBACK = 1, 2, 3, 8, 9
PINGREQ, PINGRESP, DISCONNECT = 12, 13, 14


@dataclass
class Connection:
    client_id: str
    username: str | None
    password: str | None
    will: tuple[str, bytes, bool] | None
    keepalive: int


@dataclass
class Published:
    topic: str
    payload: bytes
    retain: bool


@dataclass
class FakeBroker:
    reject_with: int = 0  # CONNACK return code; 0 accepts
    connections: list[Connection] = field(default_factory=list)
    published: list[Published] = field(default_factory=list)
    subscriptions: list[str] = field(default_factory=list)
    clean_disconnects: int = 0
    _writers: set[asyncio.StreamWriter] = field(default_factory=set)
    _server: asyncio.Server | None = None
    port: int = 0

    async def start(self, port: int = 0) -> None:
        self._server = await asyncio.start_server(self._client, "127.0.0.1", port)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        await self.drop_clients()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def drop_clients(self) -> None:
        """Close every client connection without a DISCONNECT."""
        for writer in list(self._writers):
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
        self._writers.clear()

    async def send(self, topic: str, payload: bytes) -> None:
        """Deliver a QoS 0 PUBLISH to every connected client."""
        body = len(topic).to_bytes(2, "big") + topic.encode() + payload
        packet = bytes([PUBLISH << 4]) + _encode_length(len(body)) + body
        for writer in list(self._writers):
            writer.write(packet)
            await writer.drain()

    def topics(self) -> list[str]:
        return [p.topic for p in self.published]

    def payloads(self, topic: str) -> list[str]:
        return [p.payload.decode() for p in self.published if p.topic == topic]

    async def wait_for(self, predicate, timeout: float = 3.0) -> None:
        async with asyncio.timeout(timeout):
            while not predicate():
                await asyncio.sleep(0.01)

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._writers.add(writer)
        try:
            while True:
                packet_type, flags, body = await _read_packet(reader)
                if packet_type == CONNECT:
                    self.connections.append(_parse_connect(body))
                    writer.write(bytes([CONNACK << 4, 2, 0, self.reject_with]))
                elif packet_type == PUBLISH:
                    topic_len = int.from_bytes(body[:2], "big")
                    topic = body[2 : 2 + topic_len].decode()
                    offset = 2 + topic_len + (2 if flags & 0x06 else 0)
                    self.published.append(Published(topic, body[offset:], bool(flags & 1)))
                elif packet_type == SUBSCRIBE:
                    packet_id = body[:2]
                    topic_len = int.from_bytes(body[2:4], "big")
                    self.subscriptions.append(body[4 : 4 + topic_len].decode())
                    writer.write(bytes([SUBACK << 4, 3]) + packet_id + b"\x00")
                elif packet_type == PINGREQ:
                    writer.write(bytes([PINGRESP << 4, 0]))
                elif packet_type == DISCONNECT:
                    self.clean_disconnects += 1
                    break
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            self._writers.discard(writer)
            writer.close()


async def _read_packet(reader: asyncio.StreamReader) -> tuple[int, int, bytes]:
    header = (await reader.readexactly(1))[0]
    length = 0
    for shift in range(0, 28, 7):
        byte = (await reader.readexactly(1))[0]
        length |= (byte & 0x7F) << shift
        if not byte & 0x80:
            break
    return header >> 4, header & 0x0F, await reader.readexactly(length)


def _encode_length(length: int) -> bytes:
    encoded = bytearray()
    while True:
        byte, length = length % 128, length // 128
        encoded.append(byte | (0x80 if length else 0))
        if not length:
            return bytes(encoded)


def _parse_connect(body: bytes) -> Connection:
    pos = 0

    def string() -> bytes:
        nonlocal pos
        size = int.from_bytes(body[pos : pos + 2], "big")
        value = body[pos + 2 : pos + 2 + size]
        pos += 2 + size
        return value

    string()  # protocol name
    flags = body[pos + 1]
    keepalive = int.from_bytes(body[pos + 2 : pos + 4], "big")
    pos += 4
    client_id = string().decode()
    will = None
    if flags & 0x04:
        will_topic = string().decode()
        will = (will_topic, string(), bool(flags & 0x20))
    username = string().decode() if flags & 0x80 else None
    password = string().decode() if flags & 0x40 else None
    return Connection(client_id, username, password, will, keepalive)
