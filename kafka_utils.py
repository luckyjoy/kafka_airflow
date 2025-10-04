import json
import logging
import time
from datetime import datetime
from confluent_kafka import Producer, Consumer, KafkaException, KafkaError
from typing import List, Dict, Any

log = logging.getLogger(__name__)

# --- Configuration (Simulated) ---
KAFKA_TOPIC = "user_signups"

# --- Helper Function for Delivery Reporting ---
def delivery_report(err, msg, produced_counter: Dict[str, int]):
    """Called once for each message produced to indicate delivery result."""
    if err is not None:
        log.error(f"Message delivery failed for key {msg.key()}: {err}")
        produced_counter['failed'] += 1
    else:
        log.info(f"Delivered message to {msg.topic()} [{msg.partition()}] @ offset {msg.offset()}")
        produced_counter['success'] += 1

# --- Producer Logic with Connection Retries ---

def produce_user_data(bootstrap_servers: str, num_records: int, max_retries: int = 3):
    """Produces messages to Kafka with error reporting and retries."""
    
    producer_conf = {
        'bootstrap.servers': bootstrap_servers,
        'retries': 5, # Kafka library retry setting
        'socket.timeout.ms': 3000,
    }
    
    produced_counter = {'success': 0, 'failed': 0}
    
    for attempt in range(max_retries):
        try:
            producer = Producer(producer_conf)
            log.info(f"Attempt {attempt + 1}: Starting production of {num_records} records.")
            
            # --- Simulate Data Fetch/Generation ---
            for i in range(1, num_records + 1):
                user_id = f"user_{i}_{datetime.now().strftime('%H%M%S')}"
                user_data = {
                    "user_id": user_id,
                    "event_time": datetime.now().isoformat(),
                    "payload": {"status": "new_signup", "tier": "free"}
                }
                
                # The callback uses a lambda to pass the mutable counter
                producer.produce(
                    topic=KAFKA_TOPIC,
                    key=user_id.encode('utf-8'),
                    value=json.dumps(user_data).encode('utf-8'),
                    callback=lambda err, msg: delivery_report(err, msg, produced_counter)
                )
                producer.poll(0) # Serve delivery reports
                
            producer.flush(timeout=10) # Wait for all messages to be delivered
            
            if produced_counter['failed'] == 0:
                log.info(f"Production successful. Total messages: {produced_counter['success']}")
                return produced_counter['success']
            else:
                log.warning(f"Production finished with {produced_counter['failed']} failures.")
                # If there are failures, Airflow will retry the task based on its config.
                return produced_counter['success']

        except KafkaException as e:
            log.error(f"Kafka connection error on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(5) # Wait before next retry
                continue
            else:
                log.critical("Max retries reached. Producer task failed.")
                raise # Re-raise on final failure to fail the Airflow task
        except Exception as e:
            log.critical(f"Unexpected error during production: {e}")
            raise

# --- Consumer Logic with Robust Commit Handling ---

def consume_and_process_batch(bootstrap_servers: str, dag_run_id: str, max_messages: int = 100):
    """Consumes a batch, stages data, and handles consumer errors."""
    
    group_id = f"airflow-consumer-{dag_run_id}"
    consumer_conf = {
        'bootstrap.servers': bootstrap_servers,
        'group.id': group_id,
        'auto.offset.reset': 'earliest',
        'enable.auto.commit': False,  # Manual commit by Airflow/consumer logic
        'session.timeout.ms': 10000,  # Lowered timeout to detect failures faster
    }
    
    messages_to_process = []
    
    try:
        consumer = Consumer(consumer_conf)
        consumer.subscribe([KAFKA_TOPIC])
        log.info(f"Consumer subscribed to {KAFKA_TOPIC} with group ID {group_id}")

        while len(messages_to_process) < max_messages:
            msg = consumer.poll(timeout=2.0) # Poll with a short timeout

            if msg is None:
                log.info("No more messages in the batch or poll timeout reached.")
                break
            
            if msg.error():
                if msg.error().code() == KafkaError.PARTITION_EOF:
                    log.info(f"Reached end of partition {msg.partition()} - waiting for next message.")
                    continue
                elif msg.error().code() == KafkaError.UNKNOWN_TOPIC_OR_PART:
                    log.error(f"Topic not found: {KAFKA_TOPIC}")
                    raise KafkaException(msg.error())
                else:
                    log.error(f"Kafka consumer error: {msg.error()}")
                    raise KafkaException(msg.error())
            
            # Successful message retrieval
            try:
                decoded_value = json.loads(msg.value().decode('utf-8'))
                messages_to_process.append(decoded_value)
                # Store the message object to commit offsets later
                latest_message_to_commit = msg 
            except json.JSONDecodeError as e:
                log.error(f"Skipping malformed message from offset {msg.offset()}: {msg.value()}")
                # Critical: Commit the offset of the bad message to avoid reprocessing it forever
                consumer.commit(message=msg)
                
        # --- Processing and Staging ---
        staging_file_path = f"/tmp/kafka_staging_{dag_run_id.replace(' ', '_')}.csv"
        with open(staging_file_path, 'w') as f:
            f.write("user_id,event_time,tier,status\n")
            for record in messages_to_process:
                row = (
                    f"{record['user_id']},"
                    f"{record['event_time']},"
                    f"{record['payload']['tier']},"
                    f"{record['payload']['status']}\n"
                )
                f.write(row)

        log.info(f"Staged {len(messages_to_process)} records to: {staging_file_path}")
        
        # Manually commit the offset ONLY IF processing the batch was successful
        if messages_to_process and 'latest_message_to_commit' in locals():
            # Commit the offset of the last successfully processed message + 1
            consumer.commit(message=latest_message_to_commit, asynchronous=False)
            log.info("Successfully committed Kafka offsets.")
            
        consumer.close()
        return staging_file_path

    except Exception as e:
        log.critical(f"Consumer pipeline failure: {e}")
        # If the task fails, Airflow retries, and the consumer will restart 
        # using the last committed offset (or 'earliest' for a new group_id).
        # We rely on Airflow's retry mechanism here.
        if 'consumer' in locals():
            consumer.close()
        raise # Re-raise to fail the Airflow task