import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bridge'))
from capture_geometry import client_crop

class CaptureGeometryTests(unittest.TestCase):
    def test_physical_negative_monitor_coordinates(self):
        self.assertEqual(client_crop((1282,747),(-1500,100,-218,847),(-1499,126,-219,846)),(1,26,1281,746))

    def test_rejects_resizing_mismatch_instead_of_wrong_crop(self):
        with self.assertRaises(ValueError):client_crop((1286,749),(0,0,1282,747),(1,26,1281,746))

    def test_rejects_client_outside_window(self):
        with self.assertRaises(ValueError):client_crop((100,100),(0,0,100,100),(-1,0,99,99))

    def test_borderless_full_frame(self):
        self.assertEqual(client_crop((1920,1080),(0,0,1920,1080),(0,0,1920,1080)),(0,0,1920,1080))
