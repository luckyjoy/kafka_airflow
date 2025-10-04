from __future__ import annotations
import pendulum
import logging
import os

from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.exceptions import AirflowFailException # Crucial for controlled task failure

# Import the utility functions
from kafka_utils import produce_user_data, consume_and_process_batch

log = logging.getLogger(__name__)

# --- Configuration (Centralized) ---
KAFKA_CONN_ID = "kafka_default" 
NUM_RECORDS_TO_GENERATE = 50
MAX_TASK_RETRIES = 2 # Airflow level retries

# --- Python Callables for Tasks (Refined) ---

def get_kafka_bootstrap_servers(conn_id: str):
    """Retrieves the bootstrap servers from the Airflow connection."""
    from airflow.hooks.base import BaseHook
    try:
        conn = BaseHook.get_connection(conn_id)
        # Assumes the bootstrap servers are in the Extra field
        extra_config = conn.extra_dejson
        bootstrap_servers = extra_config.get("bootstrap.servers")
        if not bootstrap_servers:
             raise ValueError(f"bootstrap.servers not found in 'Extra' for connection {conn_id}.")
        return bootstrap_servers
    except Exception as e:
        log.error(f"Failed to retrieve Kafka connection {conn_id}: {e}")
        # Use AirflowFailException for a clean, non-retryable failure on configuration error
        raise AirflowFailException(f"Configuration Error: Kafka connection failed. {e}")


def producer_task(ti, **kwargs):
    """Calls the utility function to produce data to Kafka."""
    bootstrap_servers = get_kafka_bootstrap_servers(KAFKA_CONN_ID)
    
    produced_count = produce_user_data(
        bootstrap_servers=bootstrap_servers,
        num_records=NUM_RECORDS_TO_GENERATE,
        max_retries=3 # Internal retry for connection stability
    )
    
    # Fail if zero messages were produced after all retries (e.g., source data issue)
    if produced_count == 0 and NUM_RECORDS_TO_GENERATE > 0:
        raise AirflowFailException("Producer expected to generate records but produced zero.")
        
    return produced_count


def load_task(ti, **kwargs):
    """Retrieves the staging file path from XCom and simulates loading."""
    staging_file_path = ti.xcom_pull(task_ids='consume_and_stage_data', key='staging_file_path')
    
    if not staging_file_path or not os.path.exists(staging_file_path):
        # A file missing error is a critical failure that shouldn't typically retry
        raise AirflowFailException(f"Critical Error: Staging file not found at {staging_file_path}")
        
    log.info(f"Starting load process for file: {staging_file_path}")
    
    try:
        # Check file size for empty file error handling
        if os.path.getsize(staging_file_path) < 100: # Arbitrary small size check
             log.warning("Staging file is very small. Check for upstream issues.")

        # Simulate database hook/load logic
        with open(staging_file_path, 'r') as f:
            lines = f.readlines()
            log.info(f"Loaded {len(lines) - 1} records from staging file.")
            
    except Exception as e:
        log.error(f"Error during data loading: {e}")
        # Allow Airflow to handle retry for transient DB issues
        raise # Re-raise to trigger Airflow retry logic


# --- Airflow DAG Definition ---
with DAG(
    dag_id="robust_kafka_etl_pipeline",
    start_date=pendulum.datetime(2023, 1, 1, tz="UTC"),
    schedule="0 1 * * *",
    catchup=False,
    tags=["etl", "kafka", "robust"],
    default_args={
        'retries': MAX_TASK_RETRIES,
        'retry_delay': pendulum.duration(minutes=5),
        'max_active_runs': 1, # Prevent concurrent runs processing the same data
    }
) as dag:
    
    # 1. Producer Task
    produce_data = PythonOperator(
        task_id="generate_and_produce_data",
        python_callable=producer_task,
        # Set a shorter retry count if the internal Python function already handles retries
        retries=1, 
    )

    # 2. Consumer Task
    consume_and_stage = PythonOperator(
        task_id="consume_and_stage_data",
        python_callable=consume_and_process_batch,
        op_kwargs={'run_id': "{{ run_id }}", 'max_messages': NUM_RECORDS_TO_GENERATE},
        # Ensure the consumer task has enough time, as it waits for Kafka polls
        execution_timeout=pendulum.duration(minutes=10)
    )

    # 3. Loader Task
    load_to_dw = PythonOperator(
        task_id="load_staged_data",
        python_callable=load_task,
    )
    
    # 4. Cleanup Task (Triggered even on load failure to free disk space)
    cleanup = BashOperator(
        task_id="cleanup_staging_file",
        bash_command="rm -f {{ task_instance.xcom_pull(task_ids='consume_and_stage_data', key='staging_file_path') }}",
        trigger_rule="all_done", # Runs even if `load_to_dw` succeeds or fails
    )

    # Define the pipeline flow
    produce_data >> consume_and_stage >> load_to_dw >> cleanup