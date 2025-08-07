from aioquic.buffer import encode_uint_var
from aioquic.masque.events import ConnectFailed, Connected, MasqueEvent, ProxiedDatagramReceived
from ..h3.connection import H3Connection, Headers
from ..h3.events import DataReceived, DatagramReceived, H3Event, HeadersReceived
from .capsule import CapsuleBuffer, DatagramCapsule
from .capsule import encode_datagram_capsule
from .exceptions import MasqueError
from enum import Enum
from typing import Any, Callable, List, Optional, Tuple
from urllib.parse import urlparse

UDP_PAYLOAD = 0x0
UDP_PAYLOAD_BYTE = b'\x00'

def connect_udp_default_uri(authority: str, host: str, port: int) -> str:
    return f"https://{authority.rstrip('/')}/.well-known/masque/udp/{host}/{port}/"

class ConnectState(Enum):
    INITIALIZED = 0
    CONNECT_SENT = 1
    CONNECTED = 2
    FAILED = 3

class MasqueTunnel:
    def __init__(self, http3_connection: H3Connection, stream_id: int) -> None:
        self._capsule_buffer: CapsuleBuffer = CapsuleBuffer()
        self._connect_state: ConnectState = ConnectState.INITIALIZED
        self._http: H3Connection = http3_connection
        self.stream_id: int = stream_id
    
    def handle_http_event(self, event: H3Event) -> List[MasqueEvent]:
        """
        Handling of HTTP events
        """
        raise NotImplementedError("This method must be implemented by subclasses.")

    def send_datagram(self, data: bytes, stream: bool = False):
        raise NotImplementedError("This method must be implemented by subclasses.")

class UdpTunnel(MasqueTunnel):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
    
    def connect(self, uri: str) -> None:
        if self._connect_state != ConnectState.INITIALIZED:
            raise MasqueError("Connect request already sent")
        if not uri.startswith("https://"):
            raise MasqueError("Invalid URI")
        
        parsed = urlparse(uri)
        headers: Headers = [
            (b':method', b'CONNECT'),
            (b':scheme', b'https'),
            (b':authority', parsed.netloc.encode()),
            (b':path', parsed.path.encode()),
            (b':protocol', b'connect-udp'),
            (b'capsule-protocol', b'?1'),
        ]
        self._http.send_headers(stream_id=self.stream_id, headers=headers, end_stream=False)
        self._connect_state = ConnectState.CONNECT_SENT

    def handle_http_event(self, event: H3Event) -> List[MasqueEvent]:
        masque_events: List[MasqueEvent] = []
        if isinstance(event, HeadersReceived):

            assert event.stream_id == self.stream_id

            if self._connect_state != ConnectState.CONNECT_SENT:
                raise MasqueError("Should not receive headers in this state.")

            for header, value in event.headers:
                if header == b':status' and value.isdigit(): 
                    if int(value) in range(200, 300):
                        status = True
                    else:            
                      return [ConnectFailed(self.stream_id, reason=f"Connect request failed with status {value}")]
                elif header == b'capsule-protocol' and value == b'?1':
                    capsule = True
            if not status:
                self._connect_state = ConnectState.FAILED
                return [ConnectFailed(self.stream_id, reason="Incomplete response")]
            if not capsule:
                self._connect_state = ConnectState.FAILED
                return [ConnectFailed(self.stream_id, reason="Capsule protocol not supported")]
            
            self._connect_state = ConnectState.CONNECTED
            masque_events.append(Connected(self.stream_id))
        
        elif isinstance(event, DataReceived):

            if self._connect_state != ConnectState.CONNECTED:
                raise MasqueError("Unknown data received")
            
            for capsule in self._capsule_buffer.read_capsule_data(event.data):
                if isinstance(capsule, DatagramCapsule):
                    datagram = self._receive_datagram(capsule.data)
                    if datagram:
                        masque_events.append(ProxiedDatagramReceived(self.stream_id, event.data))
        
        elif isinstance(event, DatagramReceived):
            assert event.stream_id == self.stream_id
            datagram = self._receive_datagram(event.data)
            if datagram:
                masque_events.append(ProxiedDatagramReceived(self.stream_id, datagram))
        
        return masque_events

    def send_datagram(self, data: bytes, stream: bool = False):
        context_id = encode_uint_var(UDP_PAYLOAD)
        datagram = context_id + data
        if stream:
            self._http.send_data(self.stream_id, encode_datagram_capsule(datagram), end_stream=False)
        else:
            self._http.send_datagram(self.stream_id, datagram)

    def _receive_datagram(self, data: bytes) -> bytes:
        ctx_size = 1 << ((data[0] & 0xc0) >> 6)
        # Drop datagrams that are too small to handle. 
        if len(data) <= ctx_size:
            return b''
        context_id = int.from_bytes(data[:ctx_size]) & 0x3f
        
        # Drop datagrams with unknown context IDs.
        if context_id != UDP_PAYLOAD:
            return b''
        return data[ctx_size:]






