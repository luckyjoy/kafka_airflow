# Apache Airflow and Kafka ETL Pipeline ⚙️

This project demonstrates a robust, production-ready **Extract, Transform, Load (ETL)** data pipeline orchestrated by **Apache Airflow** that utilizes **Apache Kafka** as a streaming intermediary for decoupled data ingestion and processing.

The pipeline simulates a daily process for handling new **User Sign-up Events**.

***

## Project Structure

The repository contains the following key files:

| File | Description |
| :--- | :--- |
| `user_etl_dag.py` | The main **Airflow Directed Acyclic Graph (DAG)** definition. It orchestrates the producer, consumer, and loading steps. |
| `kafka_utils.py` | **Core Python logic** for interacting with Kafka (producer, consumer) and includes robust error handling and connection logic. |
| `README.md` | This documentation file. |

***

## Pipeline Overview

The `robust_kafka_etl_pipeline` DAG executes the following steps daily:

1.  **`generate_and_produce_data` (Python Operator):**
    * Fetches the Kafka connection details from Airflow.
    * Simulates generating a batch of **new user sign-up events**.
    * **Produces** these events to the Kafka topic (`user_signups`).
    * Includes **retries and delivery reporting** for producer reliability.

2.  **`consume_and_stage_data` (Python Operator):**
    * **Consumes** the batch of messages produced in the previous step, using a unique Kafka **`group.id`** tied to the Airflow run ID.
    * **Handles malformed messages** by committing their offset and skipping them.
    * **Stages** the processed data (transformed into a clean CSV format) to a local temporary file (`/tmp/kafka_staging_*.csv`).
    * Pushes the **staging file path** to Airflow **XCom** for downstream tasks.
    * Manually **commits offsets** only upon successful completion of the staging process.

3.  **`load_staged_data` (Python Operator):**
    * **Pulls** the staging file path from XCom.
    * Simulates the **Load** step (e.g., reading the CSV and inserting it into a Data Warehouse like PostgreSQL, Snowflake, or S3).
    * Includes checks for file existence and size.

4.  **`cleanup_staging_file` (Bash Operator):**
    * **Removes** the temporary staging CSV file from the Airflow worker's filesystem.
    * Uses the **`all_done`** trigger rule, ensuring this task runs regardless of whether the `load_staged_data` task succeeds or fails (critical for disk space management).

***

## Setup and Configuration

### Prerequisites

1.  **Airflow Environment:** A running Apache Airflow instance (version 2.x recommended).
2.  **Kafka Cluster:** Access to a Kafka cluster (local Docker setup recommended for development).
3.  **Python Dependencies:**
    ```bash
    pip install apache-airflow 'apache-airflow-providers-apache-kafka' confluent-kafka
    ```

### Airflow Connections

A **Kafka Connection** must be defined in the Airflow UI:

| Field | Value | Notes |
| :--- | :--- | :--- |
| **Conn Id** | `kafka_default` | Must match the `KAFKA_CONN_ID` in `user_etl_dag.py`. |
| **Conn Type** | `Apache Kafka` | Select the Kafka connection type. |
| **Extra** | `{"bootstrap.servers": "kafka:9092"}` | Replace `kafka:9092` with your cluster's address. |

### Deployment

1.  Place both `user_etl_dag.py` and `kafka_utils.py` into your Airflow **`dags`** folder.
2.  Ensure the Kafka topic (`user_signups`) exists on your cluster.
3.  Unpause the `robust_kafka_etl_pipeline` DAG in the Airflow UI.

***

## Error Handling and Robustness

This pipeline incorporates several features for production readiness:

| Feature | Location | Benefit |
| :--- | :--- | :--- |
| **Connection Retries** | `kafka_utils.py` (Producer) | Internal retries for transient network issues before failing the Airflow task. |
| **Manual Offset Commit** | `kafka_utils.py` (Consumer) | Offsets are committed *only* after data is successfully staged, preventing data loss or reprocessing on task failure. |
| **Malformed Message Skip**| `kafka_utils.py` (Consumer) | Catches `JSONDecodeError` for bad messages, commits that specific offset, and continues processing the rest of the batch, preventing pipeline blockage. |
| **`AirflowFailException`** | `user_etl_dag.py` | Used for configuration errors (e.g., missing Kafka connection). This immediately fails the task **without** triggering Airflow retries, saving resources. |
| **`all_done` Trigger Rule** | `user_etl_dag.py` (Cleanup) | Guarantees the cleanup task runs even if the load step fails, maintaining disk health. |
| **Execution Timeout** | `user_etl_dag.py` (Consumer) | Ensures the consuming task doesn't hang indefinitely waiting for messages or network resources. |