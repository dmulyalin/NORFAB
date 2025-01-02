import pprint
import json
import time
from uuid import uuid4


class TestWorkerJobsApi:
    def test_job_list(self, nfclient):
        ret = nfclient.run_job("nornir", "job_list")

        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            for res in results["result"]:
                assert "client" in res
                assert "uuid" in res
                assert "task" in res
                assert "status" in res
                assert "received_timestamp" in res
                assert "done_timestamp" in res

    def test_job_list_pending_only(self, nfclient):
        ret = nfclient.run_job(
            "nornir", "job_list", kwargs={"pending": True, "completed": False}
        )

        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            for res in results["result"]:
                assert res["status"] == "PENDING"

    def test_job_list_filter_by_task_name(self, nfclient):
        ret = nfclient.run_job("nornir", "job_list", kwargs={"task": "cli"})

        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            for res in results["result"]:
                assert (
                    res["task"] == "cli"
                ), f"{worker} - Job with none 'cli' task returned: {res}"

    def test_job_list_last_1(self, nfclient):
        ret = nfclient.run_job("nornir", "job_list", kwargs={"last": 1})

        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            assert (
                len(results["result"]) == 2
            ), f"{worker} - Expected 2 results, got {len(results['result'])}"

    def test_job_details(self, nfclient):
        # run cli task with events
        cli_result = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-1"],
            kwargs={"commands": "show clock", "FC": "spine", "progress": True},
        )
        print(">>> cli_result:")
        pprint.pprint(cli_result)

        # grab job uuid for last CLI task
        job_summary = nfclient.run_job(
            "nornir",
            "job_list",
            workers=["nornir-worker-1"],
            kwargs={"last": 1, "completed": True, "pending": False, "task": "cli"},
        )
        print(">>> job_summary:")
        pprint.pprint(job_summary)
        for worker, results in job_summary.items():
            job_id = results["result"][0]["uuid"]

        # retrieve job details - job data, job result
        ret = nfclient.run_job(
            "nornir",
            "job_details",
            workers=["nornir-worker-1"],
            kwargs={"uuid": job_id},
        )
        print(">>> job_details:")
        pprint.pprint(ret, width=150)
        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            assert "client" in results["result"]
            assert "uuid" in results["result"]
            assert "status" in results["result"]
            assert "received_timestamp" in results["result"]
            assert "done_timestamp" in results["result"]
            assert "job_result" in results["result"]
            assert results["result"]["job_result"]
            assert "job_data" in results["result"]
            assert "job_events" in results["result"]
            assert len(results["result"]["job_events"]) > 0

    def test_job_details_no_events_result_data(self, nfclient):
        # run cli task with events
        cli_result = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-1"],
            kwargs={"commands": "show clock", "FC": "spine", "progress": True},
        )
        print(">>> cli_result:")
        pprint.pprint(cli_result)

        # grab job uuid for last CLI task
        job_summary = nfclient.run_job(
            "nornir",
            "job_list",
            workers=["nornir-worker-1"],
            kwargs={"last": 1, "completed": True, "pending": False, "task": "cli"},
        )
        print(">>> job_summary:")
        pprint.pprint(job_summary)
        for worker, results in job_summary.items():
            job_id = results["result"][0]["uuid"]

        # retrieve job details - job data, job result
        ret = nfclient.run_job(
            "nornir",
            "job_details",
            workers=["nornir-worker-1"],
            kwargs={"uuid": job_id, "data": False, "events": False, "result": False},
        )
        print(">>> job_details:")
        pprint.pprint(ret, width=150)
        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            assert results["result"]["job_result"] == None
            assert results["result"]["job_data"] == None
            assert results["result"]["job_events"] == []
