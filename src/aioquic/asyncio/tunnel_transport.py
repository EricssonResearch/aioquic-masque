from asyncio import DatagramProtocol, DatagramTransport
from typing import Optional, Tuple
from aioquic.masque.tunnel import MasqueTunnel
from aioquic.quic.connection import NetworkAddress


class MasqueTransport(DatagramTransport):
    """ Transport class for protocols using a MASQUE connection
    """
    def __init__(self,  
        addr: NetworkAddress,
        tunnel: MasqueTunnel, 
        *args, **kwargs
    ):
        super.__init__(*args, **kwargs)
        self._protocol: Optional[DatagramProtocol] = None
        self._addr = addr
        self._tunnel = tunnel
        
    def get_protocol(self):
        return self._protocol
    
    def set_protocol(self, protocol: DatagramProtocol): 
        self._protocol = protocol
    
    def sendto(self, data: bytes, addr: Tuple[str, int]) -> None:
        self._tunnel.send_datagram(data)
        
    def data_received(self, data: bytes) -> None:
        if self._protocol:
            self._protocol.datagram_received(data, self._addr) 
