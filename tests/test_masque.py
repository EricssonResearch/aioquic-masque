from unittest import TestCase
from unittest.mock import Mock
from aioquic.masque.capsule import CapsuleBuffer, CapsuleType, DatagramCapsule
from aioquic.masque.capsule import _encode_capsule as encode_capsule
from aioquic.masque.tunnel import UdpTunnel, ConnectState
from aioquic.masque.events import Connected, ConnectFailed
from aioquic.masque.exceptions import MasqueError
from aioquic.h3.events import HeadersReceived
from aioquic.buffer import Buffer, UINT_VAR_MAX_SIZE, encode_uint_var



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


class TunnelTest(TestCase):
    
    def setUp(self):
        self.http_mock = Mock()
        self.stream_id = 4
        self.tunnel = UdpTunnel(self.http_mock, self.stream_id)
    
    def test_connect_success(self):
        uri = "https://proxy.example.com/.well-known/masque/udp/target.com/443/"
        self.tunnel.connect(uri)
        
        self.assertEqual(self.tunnel._connect_state, ConnectState.CONNECT_SENT)
        self.http_mock.send_headers.assert_called_once()
    
    def test_connect_invalid_uri(self):
        with self.assertRaises(MasqueError):
            self.tunnel.connect("http://proxy.example.com/path")
    
    def test_handle_headers_success(self):
        self.tunnel._connect_state = ConnectState.CONNECT_SENT
        event = HeadersReceived(
            stream_id=self.stream_id,
            headers=[(b':status', b'200'), (b'capsule-protocol', b'?1')],
            stream_ended=False,
            push_id=None
        )
        
        events = self.tunnel.handle_http_event(event)
        
        self.assertEqual(len(events), 1)
        self.assertIsInstance(events[0], Connected)
        self.assertEqual(events[0].stream_id, self.stream_id)  # type: ignore
    
    def test_handle_headers_failed_status(self):
        self.tunnel._connect_state = ConnectState.CONNECT_SENT
        event = HeadersReceived(
            stream_id=self.stream_id,
            headers=[(b':status', b'404'), (b'capsule-protocol', b'?1')],
            stream_ended=False,
            push_id=None
        )
        
        events = self.tunnel.handle_http_event(event)
        
        self.assertEqual(len(events), 1)
        self.assertIsInstance(events[0], ConnectFailed)
    
    def test_handle_headers_capsule_zero(self):
        self.tunnel._connect_state = ConnectState.CONNECT_SENT
        event = HeadersReceived(
            stream_id=self.stream_id,
            headers=[(b':status', b'200'), (b'capsule-protocol', b'?0')],
            stream_ended=False,
            push_id=None
        )
        
        events = self.tunnel.handle_http_event(event)
        
        self.assertEqual(len(events), 1)
        self.assertIsInstance(events[0], ConnectFailed)
    

    def test_handle_headers_capsule_missing(self):
        self.tunnel._connect_state = ConnectState.CONNECT_SENT
        event = HeadersReceived(
            stream_id=self.stream_id,
            headers=[(b':status', b'200')],
            stream_ended=False,
            push_id=None
        )
        
        events = self.tunnel.handle_http_event(event)
        
        self.assertEqual(len(events), 1)
        self.assertIsInstance(events[0], ConnectFailed)

    def test_send_datagram_via_stream(self):
        payload = b"test data"
        self.tunnel.send_datagram(payload, stream=True)
        
        self.http_mock.send_data.assert_called_once()
    
    def test_send_datagram_via_datagram(self):
        payload = b"test data"
        self.tunnel.send_datagram(payload, stream=False)
        
        self.http_mock.send_datagram.assert_called_once()
    
    def test_receive_datagram_valid(self):
        payload = b"test data"
        context_id = encode_uint_var(0)
        datagram_data = context_id + payload
        
        result = self.tunnel._receive_datagram(datagram_data)
        self.assertEqual(result, payload)
    
    def test_receive_datagram_invalid_context(self):
        payload = b"test data"
        context_id = encode_uint_var(1)
        datagram_data = context_id + payload
        
        result = self.tunnel._receive_datagram(datagram_data)
        self.assertEqual(result, b'')