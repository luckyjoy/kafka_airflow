
import os
import tempfile
from airflow.exceptions import AirflowFailException

# Import DAG module so we can access load_task
import importlib.util
import sys
spec = importlib.util.spec_from_file_location("user_etl_dag", os.path.abspath('dags/user_etl_dag.py'))
user_etl_dag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(user_etl_dag)


def test_load_task_raises_if_missing_file(tmp_path):
    class _TI:
        def xcom_pull(self, task_ids, key):
            return str(tmp_path / 'does_not_exist.csv')
    ti = _TI()
    try:
        user_etl_dag.load_task(ti=ti)
        assert False, "Expected AirflowFailException"
    except AirflowFailException:
        assert True


def test_load_task_reads_file(tmp_path):
    csv = tmp_path / 'stage.csv'
    csv.write_text('user_id,event_time,tier,status
')
    class _TI:
        def xcom_pull(self, task_ids, key):
            return str(csv)
    ti = _TI()
    # Should not raise
    user_etl_dag.load_task(ti=ti)
