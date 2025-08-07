from asyncio import DatagramProtocol, DatagramTransport
from typing import Callable, Optional, Tuple
from aioquic.quic.connection import NetworkAddress


class MasqueTransport(DatagramTransport):
    """ Transport class for protocols using a MASQUE connection
    """
    def __init__(self,  
        addr: NetworkAddress,
        send: Callable[[bytes], None], 
    ):
        self._protocol: Optional[DatagramProtocol] = None
        self._addr = addr
        self._send = send
        
    def get_protocol(self):
        return self._protocol
    
    def set_protocol(self, protocol: DatagramProtocol): 
        self._protocol = protocol
    
    def sendto(self, data: bytes, _: Tuple[str, int]) -> None:
        self._send(data)
        
    def data_received(self, data: bytes) -> None:
        if self._protocol:
            self._protocol.datagram_received(data, self._addr) 
