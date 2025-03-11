import pprint
import pytest
import random
import requests
import json


class TestWorkflowWorker:
    def test_get_inventory(self, nfclient):
        ret = nfclient.run_job("workflow", "get_inventory")
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert all(
                k in data["result"] for k in ["service"]
            ), f"{worker_name} inventory incomplete"

    def test_get_version(self, nfclient):
        ret = nfclient.run_job("workflow", "get_version")
        pprint.pprint(ret)

        assert isinstance(ret, dict), f"Expected dictionary but received {type(ret)}"
        for worker_name, version_report in ret.items():
            for package, version in version_report["result"].items():
                assert version != "", f"{worker_name}:{package} version is empty"


class TestWorkflowRunTask:
    def test_workflow_1(self, nfclient):
        ret = nfclient.run_job(
            "workflow",
            "run",
            kwargs={
                "workflow": "nf://workflow/test_workflow_1.yaml",
            },
        )
        pprint.pprint(ret)

        assert (
            ret["workflow-worker-1"]["result"]["test_workflow_1"]["step1"][
                "nornir-worker-1"
            ]["failed"]
            is False
        ), "test_workflow_1 step1 nornir-worker-1 failed"
        assert ret["workflow-worker-1"]["result"]["test_workflow_1"]["step1"][
            "nornir-worker-1"
        ]["result"]["ceos-spine-1"][
            "show version"
        ], f"test_workflow_1 step1 nornir-worker-1 ceos-spine-1 show version has no output"
        assert ret["workflow-worker-1"]["result"]["test_workflow_1"]["step1"][
            "nornir-worker-1"
        ]["result"]["ceos-spine-2"][
            "show version"
        ], f"test_workflow_1 step1 nornir-worker-1 ceos-spine-2 show version has no output"
        assert ret["workflow-worker-1"]["result"]["test_workflow_1"]["step1"][
            "nornir-worker-1"
        ]["result"]["ceos-spine-1"][
            "show ip int brief"
        ], f"test_workflow_1 step1 nornir-worker-1 ceos-spine-1 show ip int brief has no output"
        assert ret["workflow-worker-1"]["result"]["test_workflow_1"]["step1"][
            "nornir-worker-1"
        ]["result"]["ceos-spine-2"][
            "show ip int brief"
        ], f"test_workflow_1 step1 nornir-worker-1 ceos-spine-2 show ip int brief has no output"

        assert (
            ret["workflow-worker-1"]["result"]["test_workflow_1"]["step2"][
                "nornir-worker-2"
            ]["failed"]
            is False
        ), "test_workflow_1 step2 nornir-worker-2 failed"
        assert ret["workflow-worker-1"]["result"]["test_workflow_1"]["step2"][
            "nornir-worker-2"
        ]["result"]["ceos-leaf-1"][
            "show hostname"
        ], f"test_workflow_1 step2 nornir-worker-2 ceos-leaf-1 show hostname has no output"
        assert ret["workflow-worker-1"]["result"]["test_workflow_1"]["step2"][
            "nornir-worker-2"
        ]["result"]["ceos-leaf-2"][
            "show hostname"
        ], f"test_workflow_1 step2 nornir-worker-2 ceos-leaf-2 show hostname has no output"
        assert ret["workflow-worker-1"]["result"]["test_workflow_1"]["step2"][
            "nornir-worker-2"
        ]["result"]["ceos-leaf-3"][
            "show hostname"
        ], f"test_workflow_1 step2 nornir-worker-2 ceos-leaf-3 show hostname has no output"
        assert ret["workflow-worker-1"]["result"]["test_workflow_1"]["step2"][
            "nornir-worker-2"
        ]["result"]["ceos-leaf-1"][
            "show ntp status"
        ], f"test_workflow_1 step2 nornir-worker-2 ceos-leaf-1 show ntp status has no output"
        assert ret["workflow-worker-1"]["result"]["test_workflow_1"]["step2"][
            "nornir-worker-2"
        ]["result"]["ceos-leaf-2"][
            "show ntp status"
        ], f"test_workflow_1 step2 nornir-worker-2 ceos-leaf-2 show ntp status has no output"
        assert ret["workflow-worker-1"]["result"]["test_workflow_1"]["step2"][
            "nornir-worker-2"
        ]["result"]["ceos-leaf-3"][
            "show ntp status"
        ], f"test_workflow_1 step2 nornir-worker-2 ceos-leaf-3 show ntp status has no output"
