import json
import pika

def send_test_message(event_type, entity_id, name, forename):
    connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
    channel = connection.channel()
    channel.queue_declare(queue='interpol_notices', durable=True)

    payload = {
        "entity_id": entity_id,
        "forename": forename,
        "name": name,
        "date_of_birth": "1990/01/01",
        "nationalities": ["TR"],
        "event_type": event_type
    }

    channel.basic_publish(
        exchange='',
        routing_key='interpol_notices',
        body=json.dumps(payload),
        properties=pika.BasicProperties(delivery_mode=2)
    )
    connection.close()
    print(f"[TEST] {event_type} simülasyonu fırlatıldı! ID: {entity_id}")

send_test_message(
    event_type="NEW_CRIMINAL", 
    entity_id="2026/99999_TEST", 
    name="YENİ SU", 
    forename="TEST ALARMI"
)

send_test_message(
    event_type="UPDATED", 
    entity_id="2025/93298", 
    name="BEAUTRAIT (GÜNCELLENDİ)", 
    forename="CLARANCE"
)