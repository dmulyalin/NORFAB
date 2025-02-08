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
            "services count",
            "status",
            "workers count",
        ]:
            assert k in ret, "Not all broker params returned"
            assert ret[k], "Some broker params seems wrong"

    def test_show_broker_version(self, nfclient):
        reply = nfclient.get(b"mmi.service.broker", "show_broker_version")

        ret = json.loads(reply["results"])
        pprint.pprint(ret)

        for k in [
            "norfab",
            "python",
            "platform",
        ]:
            assert k in ret, "Not all broker params returned"
            assert ret[k], "Some broker params seems wrong"

    def test_show_broker_inventory(self, nfclient):
        reply = nfclient.get(b"mmi.service.broker", "show_broker_inventory")

        ret = json.loads(reply["results"])
        pprint.pprint(ret)

        for k in ["broker", "logging", "workers", "topology"]:
            assert k in ret, "Not all broker params returned"
            assert ret[k], "Some broker params seems wrong"
