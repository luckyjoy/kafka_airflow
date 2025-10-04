
import os
import sys
import json

sys.path.insert(0, os.path.abspath('dags'))
import kafka_utils as ku  # noqa

# Fakes used to validate consumer edge cases
class FakeKafkaError:
    PARTITION_EOF = object()
    UNKNOWN_TOPIC_OR_PART = object()
    def __init__(self, code_val=None):
        self._code = code_val
    def code(self):
        return self._code
    def __str__(self):
        return f"FakeKafkaError({self._code})"

class FakeMsg:
    def __init__(self, value=None, error_obj=None, offset=0):
        self._val = value
        self._err = error_obj
        self._offset = offset
    def value(self): return self._val
    def error(self): return self._err
    def topic(self): return ku.KAFKA_TOPIC
    def partition(self): return 0
    def offset(self): return self._offset

class FakeConsumer:
    def __init__(self, conf):
        self._msgs = []
        self._commit_log = []
        self.closed = False
    def subscribe(self, topics):
        pass
    def enqueue(self, msg):
        self._msgs.append(msg)
    def poll(self, timeout=1.0):
        return self._msgs.pop(0) if self._msgs else None
    def commit(self, message=None, asynchronous=False):
        self._commit_log.append(message)
    def close(self):
        self.closed = True


def test_consumer_no_messages_no_commit(monkeypatch, tmp_path):
    monkeypatch.setattr(ku, 'Consumer', FakeConsumer)
    monkeypatch.setattr(ku, 'KafkaError', FakeKafkaError)

    fc = FakeConsumer({})
    monkeypatch.setattr(ku, 'Consumer', lambda conf: fc)

    staging = ku.consume_and_process_batch('kafka:9092', 'run_nomsg', max_messages=3)
    assert os.path.exists(staging)
    with open(staging) as f:
        lines = f.readlines()
    # header only
    assert len(lines) == 1
    assert len(fc._commit_log) == 0
    os.remove(staging)


def test_consumer_unknown_topic_raises(monkeypatch):
    # Provide a KafkaException if missing
    if not hasattr(ku, 'KafkaException'):
        class _KEx(Exception):
            pass
        ku.KafkaException = _KEx  # type: ignore

    monkeypatch.setattr(ku, 'Consumer', FakeConsumer)
    monkeypatch.setattr(ku, 'KafkaError', FakeKafkaError)

    fc = FakeConsumer({})
    # First polled message returns an error indicating unknown topic
    fc.enqueue(FakeMsg(error_obj=FakeKafkaError(FakeKafkaError.UNKNOWN_TOPIC_OR_PART)))
    monkeypatch.setattr(ku, 'Consumer', lambda conf: fc)

    import pytest
    with pytest.raises(ku.KafkaException):
        ku.consume_and_process_batch('kafka:9092', 'run_unknown_topic', max_messages=1)
