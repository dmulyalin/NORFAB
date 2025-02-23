import pprint
import pytest
import random


class TestDummyPluginLocal:
    def test_dummy_worker_running(self, nfclient):
        ret = nfclient.get("mmi.service.broker", "show_workers")
        assert any(
            "dummy" in w["name"] and w["status"] == "alive" for w in ret["results"]
        ), "dummy worker not running"

    def test_dummy_plugin_inventory(self, nfclient):
        ret = nfclient.run_job("DummyService", "get_inventory")
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert all(
                k in res["result"] for k in ["service", "data"]
            ), f"{worker} - not all dummy inventory data returned"

    def test_dummy_plugin_get_version(self, nfclient):
        ret = nfclient.run_job("DummyService", "get_version")
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert all(
                k in res["result"] for k in ["norfab", "platform", "python"]
            ), f"{worker} - not all dummy inventory data returned"
