from dataclasses import dataclass
from typing import List, Optional, Tuple

class MasqueEvent:
    """
    Base class for Masque events.
    """

@dataclass
class ProxiedDatagramReceived(MasqueEvent):
    stream_id: int
    datagram: bytes

@dataclass
class Connected(MasqueEvent):
    stream_id: int

@dataclass
class ConnectFailed(MasqueEvent):
    stream_id: int
    reason: Optional[str] = None