import unittest
import sys
import os

test_db = os.path.join(os.path.dirname(__file__), "test_scraper.db")
os.environ["SCRAPER_DB_PATH"] = test_db

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from container_a.main import Fetcher

class TestFetcher(unittest.TestCase):
    def setUp(self):
        if os.path.exists(test_db):
            os.remove(test_db)
            
    def tearDown(self):
        try:
            if os.path.exists(test_db):
                os.remove(test_db)
        except Exception:
            pass

    def test_hash_olusturma(self):
        f = Fetcher("http://fake.api", None)
        
        d1 = {"isim": "ali", "yas": 30}
        d2 = {"yas": 30, "isim": "ali"}
        
        h1 = f._mk_hash(d1)
        h2 = f._mk_hash(d2)
        
        self.assertEqual(h1, h2)
        
        d3 = {"isim": "veli", "yas": 30}
        h3 = f._mk_hash(d3)
        self.assertNotEqual(h1, h3)

if __name__ == '__main__':
    unittest.main()
