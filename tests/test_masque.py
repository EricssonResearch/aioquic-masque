from unittest import TestCase
from aioquic.masque.capsule import CapsuleBuffer, CapsuleType, DatagramCapsule
from aioquic.masque.capsule import _encode_capsule as encode_capsule
from aioquic.buffer import Buffer, UINT_VAR_MAX_SIZE



class CapsuleTest(TestCase):

    def test_encode_datagram_capsule(self):
        type = CapsuleType.DATAGRAM
        data = b'x' * 10
        encoded = encode_capsule(type, data)
        
        self.assertEqual(encoded[0], 0)
        self.assertEqual(encoded[1] & 0xc0, 0x00)
        self.assertEqual(len(encoded), len(data) + 2)
        
        buf = Buffer(data=encoded)

        encoded_type = buf.pull_uint_var()
        self.assertEqual(encoded_type, type)
        encoded_length = buf.pull_uint_var()
        self.assertEqual(encoded_length, len(data))
        encoded_data = buf.pull_bytes(encoded_length)
        self.assertEqual(encoded_data, data)

    def test_empty(self):
        capsule_buffer = CapsuleBuffer()
        capsules = capsule_buffer.read_capsule_data(b'')
        self.assertEqual(capsules, [])
    
    def test_single(self):
        capsule_buffer = CapsuleBuffer()
        data = b'x' * 100
        input = encode_capsule(CapsuleType.DATAGRAM, data)
        capsules = capsule_buffer.read_capsule_data(input)
        self.assertEqual(len(capsules), 1)
        self.assertIsInstance(capsules[0], DatagramCapsule)
        self.assertEqual(capsules[0].data, data) # type: ignore
    
    def test_fragmented(self):
        capsule_buffer = CapsuleBuffer()
        first = b'x' * 100
        rest = b'y' * 100
        
        buf = Buffer(capacity=UINT_VAR_MAX_SIZE * 2 + len(first))
        buf.push_uint_var(CapsuleType.DATAGRAM)
        buf.push_uint_var(len(first) + len(rest))
        buf.push_bytes(first)
        first_input = buf.data
        capsules = capsule_buffer.read_capsule_data(first_input)
        self.assertEqual(capsules, [])
        capsules = capsule_buffer.read_capsule_data(rest)
        self.assertEqual(len(capsules), 1)
        self.assertIsInstance(capsules[0], DatagramCapsule)
        self.assertEqual(capsules[0].data, first + rest) # type: ignore

    def test_multiple(self):
        capsule_buffer = CapsuleBuffer()
        first = b'x' * 100
        second = b'y' * 100
        
        capsule1 = encode_capsule(CapsuleType.DATAGRAM, first)
        capsule2 = encode_capsule(CapsuleType.DATAGRAM, second)

        capsules = capsule_buffer.read_capsule_data(capsule1 + capsule2)
        self.assertEqual(len(capsules), 2)
        self.assertIsInstance(capsules[0], DatagramCapsule)
        self.assertIsInstance(capsules[1], DatagramCapsule)
        self.assertEqual(capsules[0].data, first) # type: ignore
        self.assertEqual(capsules[1].data, second) # type: ignore
    
    def test_multiple_and_fragmented(self):
        capsule_buffer = CapsuleBuffer()
        first = b'x' * 100
        second = b'y' * 50
        third =  b'z' * 50
        
        capsule1 = encode_capsule(CapsuleType.DATAGRAM, first)
        #capsule2 = encode_capsule(CapsuleType.DATAGRAM, second)

        buf = Buffer(capacity=UINT_VAR_MAX_SIZE + len(second))
        buf.push_uint_var(CapsuleType.DATAGRAM)
        buf.push_uint_var(len(second) + len(third))
        buf.push_bytes(second)

        capsules = capsule_buffer.read_capsule_data(capsule1 + buf.data)
        self.assertEqual(len(capsules), 1)
        self.assertIsInstance(capsules[0], DatagramCapsule)
        self.assertEqual(capsules[0].data, first) # type: ignore

        capsules = capsule_buffer.read_capsule_data(third)
        self.assertEqual(len(capsules), 1)
        self.assertIsInstance(capsules[0], DatagramCapsule)
        self.assertEqual(capsules[0].data, second + third) # type: ignore