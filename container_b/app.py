import os
import json
import sqlite3
import threading
import time
import uuid
import logging
from datetime import datetime
from flask import Flask, render_template, jsonify, request
import pika

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)
class Storage:
    def __init__(self, db_file):
        self.db_file = db_file
        self._setup()

    def _setup(self):
        with sqlite3.connect(self.db_file) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS notices (
                    entity_id TEXT PRIMARY KEY,
                    forename TEXT,
                    name TEXT,
                    date_of_birth TEXT,
                    nationalities TEXT,
                    event_type TEXT,
                    updated_at TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS system_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            conn.execute("INSERT OR IGNORE INTO system_metadata (key, value) VALUES ('scan_status', 'Initializing...')")

    def set_status(self, msg):
        with sqlite3.connect(self.db_file, timeout=10) as conn:
            conn.execute("UPDATE system_metadata SET value = ? WHERE key = 'scan_status'", (msg,))

    def save_notice(self, record):
        with sqlite3.connect(self.db_file, timeout=10) as conn:
            nats = record.get("nationalities", [])
            nat_str = ", ".join(nats) if isinstance(nats, list) else str(nats)

            conn.execute("""
                INSERT INTO notices (entity_id, forename, name, date_of_birth, nationalities, event_type, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(entity_id) DO UPDATE SET
                    forename=excluded.forename,
                    name=excluded.name,
                    date_of_birth=excluded.date_of_birth,
                    nationalities=excluded.nationalities,
                    event_type=excluded.event_type,
                    updated_at=excluded.updated_at
            """, (
                record.get("entity_id"),
                record.get("forename", ""),
                record.get("name", ""),
                record.get("date_of_birth", ""),
                nat_str,
                record.get("event_type", "NORMAL"),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))

    def get_stats(self, q="", page=1, limit=50):
        with sqlite3.connect(self.db_file, timeout=10) as conn:
            count_sql = "SELECT COUNT(*) FROM notices"
            sql = "SELECT entity_id, forename, name, date_of_birth, nationalities, event_type, updated_at FROM notices"
            args = []
            
            if q:
                where_clause = " WHERE entity_id LIKE ? OR forename LIKE ? OR name LIKE ? OR nationalities LIKE ?"
                count_sql += where_clause
                sql += where_clause
                wildcard = f"%{q}%"
                args = [wildcard, wildcard, wildcard, wildcard]

            c = conn.execute(count_sql, args)
            total = c.fetchone()[0]

            sql += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
            offset = (page - 1) * limit
            query_args = args + [limit, offset]

            rows = conn.execute(sql, query_args).fetchall()
            items = [
                {"entity_id": r[0], "forename": r[1], "name": r[2], "date_of_birth": r[3], "nationalities": r[4], "event_type": r[5], "updated_at": r[6]}
                for r in rows
            ]
            
            c = conn.execute("SELECT value FROM system_metadata WHERE key = 'scan_status'")
            row = c.fetchone()
            status_text = row[0] if row else "Unknown"
            
            return {
                "notices": items, 
                "total": total, 
                "scan_status": status_text,
                "page": page,
                "per_page": limit
            }
class Consumer:
    def __init__(self, mq_host, q_name, store):
        self.mq_host = mq_host
        self.q_name = q_name
        self.store = store

    def _handle_msg(self, body):
        if "system_event" in body:
            self.store.set_status(body["message"])
            return
        self.store.save_notice(body)

    def run(self):
        while True:
            try:
                conn = pika.BlockingConnection(pika.ConnectionParameters(host=self.mq_host))
                ch = conn.channel()
                ch.queue_declare(queue=self.q_name, durable=True)

                def cb(ch, method, props, body):
                    try:
                        self._handle_msg(json.loads(body))
                        ch.basic_ack(delivery_tag=method.delivery_tag)
                    except Exception as e:
                        log.error(f"DB error on msg: {e}")

                ch.basic_consume(queue=self.q_name, on_message_callback=cb)
                log.info("MQ consumer ready")
                ch.start_consuming()
            except Exception as e:
                log.error(f"MQ connect fail: {e}. Retry in 5s")
                time.sleep(5)
class RPC:
    def __init__(self, mq_host):
        self.mq_host = mq_host

    def fetch(self, eid):
        conn = pika.BlockingConnection(pika.ConnectionParameters(host=self.mq_host))
        ch = conn.channel()
        res = ch.queue_declare(queue='', exclusive=True)
        cb_q = res.method.queue
        
        reply = None
        c_id = str(uuid.uuid4())

        def on_res(ch, method, props, body):
            nonlocal reply
            if c_id == props.correlation_id:
                reply = body

        ch.basic_consume(queue=cb_q, on_message_callback=on_res, auto_ack=True)
        ch.basic_publish(
            exchange='',
            routing_key='interpol_rpc_queue',
            properties=pika.BasicProperties(reply_to=cb_q, correlation_id=c_id),
            body=str(eid)
        )

        t0 = time.time()
        while reply is None:
            if time.time() - t0 > 15:
                break
            conn.process_data_events(time_limit=1)
            
        conn.close()
        return reply
class App:
    def __init__(self, store, rpc_client):
        self.app = Flask(__name__)
        self.store = store
        self.rpc_client = rpc_client
        self._routes()

    def _routes(self):
        @self.app.route('/')
        def home():
            return render_template('index.html')

        @self.app.route('/api/data')
        def data_api():
            q = request.args.get('search', '', type=str)
            p = request.args.get('page', 1, type=int)
            return jsonify(self.store.get_stats(q=q, page=p))

        @self.app.route('/notice/<path:eid>')
        def detail_page(eid):
            return render_template('detail.html', entity_id=eid)

        @self.app.route('/api/notice/<path:eid>')
        def notice_api(eid):
            try:
                raw = self.rpc_client.fetch(eid)
                if raw:
                    return jsonify(json.loads(raw.decode('utf-8')))
                return jsonify({"error": "Empty RPC response"}), 500
            except Exception as e:
                return jsonify({"error": str(e)}), 500

    def serve(self, host="0.0.0.0", port=5000):
        self.app.run(host=host, port=port, threaded=True)

if __name__ == "__main__":
    db_file = os.getenv("INTERPOL_DB_PATH", "interpol.db")
    mq_server = os.getenv("RABBITMQ_HOST", "localhost")
    q_name = os.getenv("RABBITMQ_QUEUE", "interpol_notices")
    listen_port = int(os.getenv("PORT", 5000))

    store = Storage(db_file)
    rpc = RPC(mq_server)
    worker = Consumer(mq_server, q_name, store)
    app_srv = App(store, rpc)

    threading.Thread(target=worker.run, daemon=True).start()
    app_srv.serve(host="0.0.0.0", port=listen_port)