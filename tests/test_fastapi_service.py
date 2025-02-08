import pprint
import pytest
import random
import requests
import json

# ----------------------------------------------------------------------------
# NORNIR WORKER TESTS
# ----------------------------------------------------------------------------


class TestFastAPIWorker:
    def test_get_fastapi_inventory(self, nfclient):
        ret = nfclient.run_job(b"fastapi", "get_fastapi_inventory")
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert all(
                k in data["result"] for k in ["fastapi", "uvicorn", "service"]
            ), f"{worker_name} inventory incomplete"

    def test_get_fastapi_version(self, nfclient):
        ret = nfclient.run_job(b"fastapi", "get_fastapi_version")
        pprint.pprint(ret)

        assert isinstance(ret, dict), f"Expected dictionary but received {type(ret)}"
        for worker_name, version_report in ret.items():
            for package, version in version_report["result"].items():
                assert version != "", f"{worker_name}:{package} version is empty"


class TestFastAPIServer:
    def test_job_post(self, nfclient):
        resp = requests.post(
            url="http://127.0.0.1:8000/job",
            data=json.dumps(
                {
                    "service": "nornir",
                    "task": "cli",
                    "kwargs": {
                        "commands": ["show clock", "show hostname"],
                        "FC": "spine",
                    },
                }
            ),
        )
        resp.raise_for_status()
        res = resp.json()
        pprint.pprint(res)

        assert res["errors"] == [], f"Having errors: '{res['errors']}'"
        assert res["status"] == "200", f"Unexpected status: '{res['status']}'"
        assert res["uuid"], f"Unexpectd uuid value '{res['uuid']}'"
        assert len(res["workers"]) > 0, f"No workers targeted"

    def test_job_post_noargs_nokwargs(self, nfclient):
        resp = requests.post(
            url="http://127.0.0.1:8000/job",
            data=json.dumps({"service": "nornir", "task": "get_nornir_version"}),
        )
        resp.raise_for_status()
        res = resp.json()
        pprint.pprint(res)

        assert res["errors"] == [], f"Having errors: '{res['errors']}'"
        assert res["status"] == "200", f"Unexpected status: '{res['status']}'"
        assert res["uuid"], f"Unexpectd uuid value '{res['uuid']}'"
        assert len(res["workers"]) > 0, f"No workers targeted"

    def test_job_get(self, nfclient):
        # post the job first
        post_resp = requests.post(
            url="http://127.0.0.1:8000/job",
            data=json.dumps({"service": "nornir", "task": "get_nornir_version"}),
        )
        post_resp.raise_for_status()
        post_res = post_resp.json()
        pprint.pprint(post_res)

        uuid = post_res["uuid"]

        # get the job
        get_resp = requests.get(
            url="http://127.0.0.1:8000/job",
            data=json.dumps({"service": "nornir", "uuid": uuid}),
        )
        get_resp.raise_for_status()
        get_res = get_resp.json()
        pprint.pprint(get_res)

        assert get_res["errors"] == []
        assert get_res["status"] == "202"
        assert get_res["workers"]["dispatched"] != []
        assert get_res["workers"]["done"] != []
        assert get_res["workers"]["pending"] == []

        for wname, wres in get_res["results"].items():
            assert wres["errors"] == [], f"{wname} having errors '{wres['errors']}'"
            assert wres["failed"] == False, f"{wname} failed to run job"
            assert wres["result"], f"{wname} no results provided"

    def test_job_run(self, nfclient):
        resp = requests.post(
            url="http://127.0.0.1:8000/job/run",
            data=json.dumps(
                {
                    "service": "nornir",
                    "task": "cli",
                    "kwargs": {
                        "commands": ["show clock", "show hostname"],
                        "FC": "spine",
                    },
                }
            ),
        )
        resp.raise_for_status()
        res = resp.json()
        pprint.pprint(res)

        for wname, wres in res.items():
            assert wres["errors"] == [], f"{wname} having errors '{wres['errors']}'"
            assert wres["failed"] == False, f"{wname} failed to run job"
            assert "result" in wres, f"{wname} no results provided"

    def test_job_run_specific_worker(self, nfclient):
        resp = requests.post(
            url="http://127.0.0.1:8000/job/run",
            data=json.dumps(
                {
                    "service": "nornir",
                    "task": "cli",
                    "workers": ["nornir-worker-1"],
                    "kwargs": {
                        "commands": ["show clock", "show hostname"],
                        "FC": "spine",
                    },
                }
            ),
        )
        resp.raise_for_status()
        res = resp.json()
        pprint.pprint(res)

        assert len(res) == 1
        for wname, wres in res.items():
            assert wres["errors"] == [], f"{wname} having errors '{wres['errors']}'"
            assert wres["failed"] == False, f"{wname} failed to run job"
            assert "result" in wres, f"{wname} no results provided"
