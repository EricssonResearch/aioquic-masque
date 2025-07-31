from ..h3.connection import H3Connection, Headers
from ..h3.events import DataReceived, DatagramReceived, H3Event, HeadersReceived
from ..h3.exceptions import H3Error
from aioquic.buffer import Buffer, BufferReadError
from .capsule import CapsuleBuffer, DatagramCapsule
from .capsule import encode_datagram_capsule
from enum import Enum
from typing import Any, Callable, List, Optional, Tuple

UDP_PAYLOAD = 0x0
UDP_PAYLOAD_BYTE = b'\x00'

class ConnectState(Enum):
    INITIALIZED = 0
    CONNECT_SENT = 1
    CONNECTED = 2



def _well_known_udp(host: str, port: int) -> bytes:
    return f'/.well-known/masque/udp/{host}/{port}'.encode()

class MasqueTunnel:
    def __init__(self, http3_connection: H3Connection, stream_id: int) -> None:
        self._capsule_buffer: CapsuleBuffer = CapsuleBuffer()
        self._connect_state: ConnectState = ConnectState.INITIALIZED
        self._http: H3Connection = http3_connection
        self._stream_id: int = stream_id
        
    def send_datagram(self, data: bytes, stream: bool = False):
        pass

class UdpTunnel(MasqueTunnel):
    def __init__(
            self, 
            http3_connection: H3Connection,
            stream_id: int,
            datagram_handler: Callable[[bytes], None]
        ) -> None:
        super().__init__(http3_connection, stream_id)    
        
        self._connect_callback: Optional[Callable[[MasqueTunnel], Any]] = None
        self._datagram_handler: Callable[[bytes], None] = datagram_handler
    
    def connect(
            self,
            target_host: str, 
            target_port: int,
            authority: str,
            connect_callback: Callable[[MasqueTunnel], Any],
            path: Callable[[str, int], bytes] = _well_known_udp,
        ):
        if self._connect_state != ConnectState.INITIALIZED:
            raise H3Error("Connect request already sent")
        
        self._connect_callback = connect_callback

        headers: Headers = [
            (b':method', b'CONNECT'),
            (b':scheme', b'https'),
            (b':authority', authority.encode()),
            (b':path', path(target_host, target_port)),
            (b':protocol', b'connect-udp'),
            (b'capsule-protocol', b'?1'),
        ]
        self._http.send_headers(stream_id=self._stream_id, headers=headers, end_stream=False)
        self._connect_state = ConnectState.CONNECT_SENT

    def handle_http_event(self, event: H3Event) -> None:
        if isinstance(event, HeadersReceived):

            assert event.stream_id == self._stream_id

            if self._connect_state != ConnectState.CONNECT_SENT:
                raise H3Error("Should not receive headers in this state.")

            for header, value in event.headers:
                if header == b':status' and value.isdigit() and int(value) in range(200, 300):
                    status = True
                elif header == b'capsule-protocol' and value == b'?1':
                    capsule = True
            if not status:
                raise H3Error(f"Connection Failed with Status {value}")
            if not capsule:
                raise H3Error(f"Peer does not support capsule protocol")
            
            self._connect_state = ConnectState.CONNECTED
            self._connect_callback(self) # type: ignore
        
        elif isinstance(event, DataReceived):

            if self._connect_state != ConnectState.CONNECTED:
                raise H3Error("Unknown data received")
            
            for capsule in self._capsule_buffer.read_capsule_data(event.data):
                if isinstance(capsule, DatagramCapsule):
                    self._receive_datagram(capsule.data)

        elif isinstance(event, DatagramReceived):
            assert event.stream_id == self._stream_id
            self._receive_datagram(event.data)

    def send_datagram(self, data: bytes, stream: bool = False):
        datagram = UDP_PAYLOAD_BYTE + data
        if stream:
            self._http.send_data(self._stream_id, encode_datagram_capsule(datagram), end_stream=False)
        else:
            self._http.send_datagram(self._stream_id, datagram)

    def _receive_datagram(self, data: bytes) -> None:
        ctx_size = 1 << ((data[0] & 0xc0) >> 6)
        
        # Drop datagrams that are too small to handle. 
        if len(data) <= ctx_size:
            return
        context_id = int.from_bytes(data[:ctx_size]) & 0x3f
        
        # Drop datagrams with unknown context IDs.
        if context_id != UDP_PAYLOAD:
            return
        self._datagram_handler(data[ctx_size:])






