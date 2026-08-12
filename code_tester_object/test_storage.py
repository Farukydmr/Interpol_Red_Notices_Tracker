import unittest
import sys
import os

test_db = os.path.join(os.path.dirname(__file__), "test_storage.db")

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from container_b.app import Storage

class TestStorage(unittest.TestCase):
    def setUp(self):
        if os.path.exists(test_db):
            os.remove(test_db)
        self.store = Storage(test_db)

    def tearDown(self):
        try:
            if os.path.exists(test_db):
                os.remove(test_db)
        except Exception:
            pass

    def test_kayit_ekleme(self):
        fake_veri = {
            "entity_id": "2026/123",
            "forename": "TEST",
            "name": "KISI",
            "date_of_birth": "1990-01-01",
            "nationalities": ["TR", "EN"],
            "event_type": "NEW_CRIMINAL"
        }
        
        self.store.save_notice(fake_veri)
        
        sonuclar = self.store.get_stats()
        notices = sonuclar["notices"]
        
        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0]["entity_id"], "2026/123")
        self.assertEqual(notices[0]["name"], "KISI")
        self.assertEqual(notices[0]["nationalities"], "TR, EN")

if __name__ == '__main__':
    unittest.main()
