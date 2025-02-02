import pprint
import json
import time
from uuid import uuid4


class TestClientApi:
    def test_show_workers(self, nfclient):
        reply = nfclient.get(b"mmi.service.broker", "show_workers")

        ret = json.loads(reply["results"])
        pprint.pprint(ret)

        for worker in ret:
            assert all(k in worker for k in ["holdtime", "name", "service", "status"])

    def test_show_broker(self, nfclient):
        reply = nfclient.get(b"mmi.service.broker", "show_broker")

        ret = json.loads(reply["results"])
        pprint.pprint(ret)

        for k in [
            "endpoint",
            "keepalives",
            "multiplier",
            "services count",
            "status",
            "workers count",
        ]:
            assert k in ret, "Not all broker params returned"
            assert ret[k], "Some broker params seems wrong"
