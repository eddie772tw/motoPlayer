import logging
import unittest
from obd_converter import parse_fast_response, decode_pid_response

class TestOBDOptimization(unittest.TestCase):
    def test_rpm_decoding(self):
        # 0C = RPM
        # 1AF8 => (26*256 + 248)/4 = 1726
        # Input like: 410C1AF8
        resp = b"410C1AF8"
        val = decode_pid_response("010C", resp)
        print(f"\nPID 0C (RPM) Input: {resp} => {val}")
        self.assertEqual(val, 1726)

    def test_speed_decoding(self):
        # 0D = Speed
        # 32 => 50 km/h
        resp = b"410D32"
        val = decode_pid_response("010D", resp)
        print(f"PID 0D (Speed) Input: {resp} => {val}")
        self.assertEqual(val, 50)

    def test_fast_response_parsing(self):
        # Combined response
        # 41 
        # 04 99 (Load=153*100/255=60.0%)
        # 05 68 (Temp=104-40=64 C)
        # 0C 1A F8 (RPM=1726)
        # 0D 32 (Speed=50)
        # 11 33 (Throttle=51*100/255=20.0%)
        # > at end
        
        raw_resp = b"41049905680C1AF80D321133>"
        print(f"Fast Response Input: {raw_resp}")
        
        result = parse_fast_response(raw_resp)
        print("Parsed Result:", result)
        
        self.assertEqual(result.get("04"), 60.0)
        self.assertEqual(result.get("05"), 64.0)
        self.assertEqual(result.get("0C"), 1726)
        self.assertEqual(result.get("0D"), 50)
        self.assertEqual(result.get("11"), 20.0)

    def test_garbage_handling(self):
        # 不完整的數據
        raw_resp = b"410C1A" # Missing last byte for RPM
        result = parse_fast_response(raw_resp)
        print(f"Garbage Input: {raw_resp} => {result}")
        self.assertIsNone(result.get("0C"))

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    unittest.main()
