
import os
import sys
import json
import time

# Ensure import path includes ./dags
sys.path.insert(0, os.path.abspath('dags'))
import kafka_utils as ku  # noqa

# Provide a fake KafkaException if not present (for local runs without the lib)
if not hasattr(ku, 'KafkaException'):
    class _KEx(Exception):
        pass
    ku.KafkaException = _KEx  # type: ignore


class FlakyProducer:
    """Producer that fails to construct once, then succeeds."""
    attempts = 0
    def __init__(self, conf):
        type(self).attempts += 1
        if type(self).attempts == 1:
            raise ku.KafkaException('bootstrap failure')
        self.produced = []
        self._callbacks = []
    def produce(self, topic, key, value, callback=None):
        self.produced.append((topic, key, value))
        if callback:
            self._callbacks.append(callback)
    def poll(self, t):
        return 0
    def flush(self, timeout=10):
        # succeed all callbacks
        for i, (topic, key, value) in enumerate(self.produced):
            class _Msg:
                def __init__(self, key, offset):
                    self._key=key; self._offset=offset
                def key(self): return self._key
                def topic(self): return ku.KAFKA_TOPIC
                def partition(self): return 0
                def offset(self): return self._offset
            m = _Msg(key, i)
            for cb in self._callbacks:
                cb(None, m)


def test_producer_retries_on_kafka_exception(monkeypatch):
    # Force our flaky producer
    monkeypatch.setattr(ku, 'Producer', FlakyProducer)
    produced = ku.produce_user_data(bootstrap_servers='kafka:9092', num_records=5, max_retries=3)
    assert produced == 5
