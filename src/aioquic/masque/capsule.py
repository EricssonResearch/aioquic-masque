from aioquic._buffer import BufferWriteError
from aioquic.buffer import Buffer, BufferReadError, UINT_VAR_MAX_SIZE
from dataclasses import dataclass
from enum import IntEnum
from typing import List, Optional, Tuple


MAX_CAPSULE_SIZE = 0xFFFF

class Capsule:
    """
    Base class for capsules
    """

@dataclass
class DatagramCapsule(Capsule):
    data: bytes


class CapsuleType(IntEnum):
    DATAGRAM = 0x00

def _encode_capsule(capsule_type: CapsuleType, payload: bytes) -> bytes:
    buf = Buffer(capacity=UINT_VAR_MAX_SIZE * 2 + len(payload))
    buf.push_uint_var(capsule_type.value)
    buf.push_uint_var(len(payload))
    buf.push_bytes(payload)

    return buf.data

def encode_datagram_capsule(data: bytes) -> bytes:
    return _encode_capsule(CapsuleType.DATAGRAM, data)

class CapsuleBuffer():
    def __init__(self) -> None:
        self._buf: Buffer = Buffer(capacity=MAX_CAPSULE_SIZE)
        self._capsule_buffer: bytes = b''
        self._start: int = 0

    def read_capsule_data(self, data: bytes) -> List[Capsule]:
        try:
            self._buf.push_bytes(data)
        except BufferWriteError:
            self._buf.seek(self._start)
            return []

        end = self._buf.tell()
        self._buf.seek(self._start)
        capsules = []       
        while self._buf.tell() < end:
            try:
                type = self._buf.pull_uint_var()
                length = self._buf.pull_uint_var()
                if self._buf.tell() + length > end:
                    self._buf.seek(end)
                    return capsules
                capsule_data = self._buf.pull_bytes(length)
                if type == CapsuleType.DATAGRAM:
                    capsules.append(DatagramCapsule(data=capsule_data))
                else:
                    capsules.append(Capsule())
                self._start = self._buf.tell()
            except BufferReadError:
                return capsules
        self._start = 0
        self._buf.seek(self._start)
        return capsules


