
import os
from airflow.models import DagBag


def _load_dag():
    return DagBag(dag_folder=os.path.abspath('dags'), include_examples=False)


def test_dag_has_expected_properties():
    dagbag = _load_dag()
    assert len(dagbag.import_errors) == 0, f"DAG import errors: {dagbag.import_errors}"
    dag = dagbag.get_dag('robust_kafka_etl_pipeline')
    assert dag is not None
    assert dag.max_active_runs == 1
    assert dag.schedule == '0 1 * * *'


def test_dag_tasks_have_templated_bootstrap():
    dag = _load_dag().get_dag('robust_kafka_etl_pipeline')
    prod = dag.get_task('generate_and_produce_data')
    cons = dag.get_task('consume_and_stage_data')
    # Bootstrap passed via Jinja template string
    assert isinstance(prod.op_kwargs.get('bootstrap_servers'), str)
    assert "conn.kafka_default" in prod.op_kwargs['bootstrap_servers']
    assert isinstance(cons.op_kwargs.get('bootstrap_servers'), str)
    assert "conn.kafka_default" in cons.op_kwargs['bootstrap_servers']
