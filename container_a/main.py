import os
import json
import time
import string
import hashlib
import sqlite3
import pika
import threading
import logging
from curl_cffi import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)

class MQClient:
    def __init__(self, mq_host, q_name): 
        self.mq_host = mq_host
        self.q_name = q_name

    def push(self, items: list):
        if not items:
            return
        try:
            conn = pika.BlockingConnection(pika.ConnectionParameters(host=self.mq_host))
            ch = conn.channel()
            ch.queue_declare(queue=self.q_name, durable=True)
            for item in items:
                ch.basic_publish(
                    exchange='',
                    routing_key=self.q_name,
                    body=json.dumps(item),
                    properties=pika.BasicProperties(delivery_mode=2)
                )
            conn.close()
        except Exception as e:
            log.error(f"MQ push failed: {e}")

class Fetcher:
    def __init__(self, api_url, mq):
        self.api_url = api_url
        self.mq = mq
        self.age_range = range(17, 101)
        self.genders = ['M', 'F', 'U']
        self.db = os.getenv("SCRAPER_DB_PATH", "scraper_state.db")
        self._setup_db()
        self.is_fresh = self._is_empty()

    def _setup_db(self):
        with sqlite3.connect(self.db) as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS seen_records (
                    entity_id TEXT PRIMARY KEY,
                    data_hash TEXT
                )
            """)

    def _is_empty(self):
        with sqlite3.connect(self.db) as c:
            row = c.execute("SELECT COUNT(*) FROM seen_records").fetchone()
            return row[0] == 0

    def _get_hash(self, eid):
        with sqlite3.connect(self.db) as c:
            row = c.execute("SELECT data_hash FROM seen_records WHERE entity_id = ?", (eid,)).fetchone()
            return row[0] if row else None

    def _set_hash(self, eid, h):
        with sqlite3.connect(self.db) as c:
            c.execute("""
                INSERT INTO seen_records (entity_id, data_hash)
                VALUES (?, ?) ON CONFLICT(entity_id) DO UPDATE SET data_hash=excluded.data_hash
            """, (eid, h))
    def start(self):
        log.info("Scraper started")
        while True:
            t0 = time.time()
            self.mq.push([{"system_event": "SCAN_STATUS", "message": "Scanning in progress..."}])
            
            for a in self.age_range:
                for g in self.genders:
                    self._pull(f"{self.api_url}?resultPerPage=160&ageMin={a}&ageMax={a}&sexId={g}")

            for letter in string.ascii_uppercase:
                self._crawl_names(letter, limit=3)

            self.is_fresh = False
            self.mq.push([{"system_event": "SCAN_STATUS", "message": "All data fetched."}])
            log.info(f"Cycle done in {time.time() - t0:.2f}s")
            time.sleep(5)

    def _crawl_names(self, pfx, limit=3, depth=1):
        url = f"{self.api_url}?resultPerPage=160&name={pfx}"
        added, total = self._pull(url)
        if total >= 160 and depth < limit:
            for nxt in string.ascii_uppercase:
                self._crawl_names(f"{pfx}{nxt}", limit, depth + 1)
        return added

    def _mk_hash(self, d):
        return hashlib.md5(json.dumps(d, sort_keys=True).encode('utf-8')).hexdigest()

    def _pull(self, url):
        try:
            res = requests.get(url, impersonate="chrome120", timeout=15)
            if res.status_code == 200:
                items = res.json().get('_embedded', {}).get('notices', [])
                batch = []

                for p in items:
                    eid = p.get("entity_id")
                    if not eid:
                        continue

                    rec = {
                        "entity_id": eid,
                        "forename": p.get("forename", ""),
                        "name": p.get("name", ""),
                        "date_of_birth": p.get("date_of_birth", ""),
                        "nationalities": p.get("nationalities", [])
                    }

                    h_new = self._mk_hash(rec)
                    h_old = self._get_hash(eid)

                    if not h_old:
                        self._set_hash(eid, h_new)
                        rec["event_type"] = "BASELINE_ADDED" if self.is_fresh else "NEW_CRIMINAL"
                        batch.append(rec)
                    elif h_old != h_new:
                        self._set_hash(eid, h_new)
                        rec["event_type"] = "UPDATED"
                        batch.append(rec)

                if batch:
                    self.mq.push(batch)
                    time.sleep(0.3)
                else:
                    time.sleep(0.05)
                return len(batch), len(items)

            elif res.status_code == 429:
                time.sleep(60)
            else:
                time.sleep(0.5)

        except Exception as e:
            time.sleep(2)
        return 0, 0
def rpc_worker(mq_host):
    while True:
        try:
            conn = pika.BlockingConnection(pika.ConnectionParameters(host=mq_host))
            ch = conn.channel()
            ch.queue_declare(queue='interpol_rpc_queue')

            def on_req(ch, method, props, body):
                eid = body.decode('utf-8')
                fid = eid.replace('/', '-')
                url = f"https://ws-public.interpol.int/notices/v1/red/{fid}"
                log.info(f"RPC req for {eid}")
                
                try:
                    res = requests.get(url, impersonate="chrome120", timeout=15)
                    data = res.text
                except Exception as e:
                    data = json.dumps({"error": str(e)})
                    
                ch.basic_publish(
                    exchange='',
                    routing_key=props.reply_to,
                    properties=pika.BasicProperties(correlation_id=props.correlation_id),
                    body=data
                )
                ch.basic_ack(delivery_tag=method.delivery_tag)

            ch.basic_qos(prefetch_count=1)
            ch.basic_consume(queue='interpol_rpc_queue', on_message_callback=on_req)
            log.info("RPC worker listening")
            ch.start_consuming()
        except Exception as e:
            log.error(f"RPC worker error: {e}. Retry in 5s")
            time.sleep(5)

if __name__ == "__main__":
    api_url = os.getenv("INTERPOL_API_URL", "https://ws-public.interpol.int/notices/v1/red")
    mq_srv = os.getenv("RABBITMQ_HOST", "localhost")
    q_name = os.getenv("RABBITMQ_QUEUE", "interpol_notices")
    
    mq = MQClient(mq_srv, q_name)
    
    threading.Thread(target=rpc_worker, args=(mq_srv,), daemon=True).start()
    Fetcher(api_url, mq).start()