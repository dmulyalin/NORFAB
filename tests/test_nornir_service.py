import pprint
import pytest


class TestNornirWorker:
    def test_get_nornir_invenotry(self, nfclient):
        ret = nfclient.run_job(b"nornir", "get_nornir_inventory")
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert all(
                k in data for k in ["hosts", "groups", "defaults"]
            ), f"{worker_name} inventory incomplete"

    def test_get_nornir_hosts(self, nfclient):
        ret = nfclient.run_job(b"nornir", "get_nornir_hosts")
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert isinstance(
                data, list
            ), "{worker_name} did not return a list of hosts"
            assert len(data) > 0 or data == []

    def test_get_nornir_version(self, nfclient):
        ret = nfclient.run_job(b"nornir", "get_nornir_version")
        pprint.pprint(ret)

        assert isinstance(ret, dict), f"Expected dictionary but received {type(ret)}"
        for worker_name, version_report in ret.items():
            for package, version in version_report.items():
                assert version != "", f"{worker_name}:{package} version is empty"


class TestNornirCli:
    def test_commands_list(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "cli",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs={"commands": ["show version", "show clock"]},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results.items():
                assert (
                    "show clock" in res and "Traceback" not in res["show clock"]
                ), f"{worker}:{host} show clock output is wrong"
                assert (
                    "show version" in res and "Traceback" not in res["show version"]
                ), f"{worker}:{host} show clock output is wrong"

    def test_commands_dry_run(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "cli",
            kwargs={"commands": ["show version", "show clock"], "dry_run": True},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results.items():
                assert "nr_test" in res and res["nr_test"] == [
                    "show version",
                    "show clock",
                ], f"{worker}:{host} dry run output is wrong"

    @pytest.mark.skip(reason="TBD")
    def test_commands_with_hosts_filters(self, nfclient):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_commands_with_worker_target(self, nfclient):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_commands_add_details(self, nfclient):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_commands_to_dict_false(self, nfclient):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_commands_to_dict_false_add_details(self, nfclient):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_commands_wrong_plugin(self, nfclient):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_commands_plugin_scrapli(self, nfclient):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_commands_plugin_napalm(self, nfclient):
        pass

    def test_commands_from_file_dry_run(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "cli",
            kwargs={
                "commands": "nf://nf_tests_inventory/cli/commands.txt",
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results.items():
                assert "nr_test" in res and res["nr_test"] == [
                    "show version\nshow clock\nshow int description"
                ], f"{worker}:{host} output is wrong"

    def test_commands_from_nonexisting_file(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "cli",
            workers="nornir-worker-1",
            kwargs={
                "commands": "nf://nf_tests_inventory/cli/commands_non_existing.txt"
            },
        )
        pprint.pprint(ret)

        assert ret == {"nornir-worker-1": {}}

    def test_commands_from_file_template(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "cli",
            kwargs={
                "commands": "nf://nf_tests_inventory/cli/show_interfaces.j2",
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results.items():
                if host == "ceos-spine-1":
                    assert "loopback0" in res["nr_test"][0]
                    assert "ethernet1" in res["nr_test"][0]
                elif host == "ceos-spine-2":
                    assert "loopback0" not in res["nr_test"][0]
                    assert "ethernet1" in res["nr_test"][0]


class TestNornirTask:
    def test_task_nornir_salt_nr_test(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "task",
            workers=["nornir-worker-1"],
            kwargs={"plugin": "nornir_salt.plugins.tasks.nr_test", "foo": "bar"},
        )
        pprint.pprint(ret)

        assert ret == {
            "nornir-worker-1": {
                "ceos-spine-1": {"nr_test": {"foo": "bar"}},
                "ceos-spine-2": {"nr_test": {"foo": "bar"}},
            }
        }

    def test_task_nornir_salt_nr_test_add_details(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "task",
            workers=["nornir-worker-1"],
            kwargs={
                "plugin": "nornir_salt.plugins.tasks.nr_test",
                "foo": "bar",
                "add_details": True,
            },
        )
        pprint.pprint(ret)

        assert ret == {
            "nornir-worker-1": {
                "ceos-spine-1": {
                    "nr_test": {
                        "changed": False,
                        "connection_retry": 0,
                        "diff": "",
                        "exception": None,
                        "failed": False,
                        "result": {"foo": "bar"},
                        "task_retry": 0,
                    }
                },
                "ceos-spine-2": {
                    "nr_test": {
                        "changed": False,
                        "connection_retry": 0,
                        "diff": "",
                        "exception": None,
                        "failed": False,
                        "result": {"foo": "bar"},
                        "task_retry": 0,
                    }
                },
            }
        }

    def test_task_from_file(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "task",
            workers=["nornir-worker-1"],
            kwargs={"plugin": "nf://nf_tests_inventory/nornir_tasks/dummy.py"},
        )
        pprint.pprint(ret)

        assert ret == {
            "nornir-worker-1": {
                "ceos-spine-1": {"dummy": True},
                "ceos-spine-2": {"dummy": True},
            }
        }

    def test_task_from_nonexisting_file(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "task",
            workers=["nornir-worker-1"],
            kwargs={"plugin": "nf://nf_tests_inventory/nornir_tasks/_non_existing_.py"},
        )
        pprint.pprint(ret, width=150)

        assert ret == {
            "nornir-worker-1": "nornir-worker-1 - 'nf://nf_tests_inventory/nornir_tasks/_non_existing_.py' task plugin download failed"
        }

    def test_task_from_nonexisting_module(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "task",
            workers=["nornir-worker-1"],
            kwargs={
                "plugin": "nornir_salt.plugins.tasks.non_existing_module",
                "foo": "bar",
            },
        )
        pprint.pprint(ret, width=200)

        assert ret == {
            "nornir-worker-1": "nornir-worker-1 - 'nornir_salt.plugins.tasks.non_existing_module' task import failed with error 'No module named 'nornir_salt.plugins.tasks.non_existing_module''"
        }

    def test_task_with_error(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "task",
            workers=["nornir-worker-1"],
            kwargs={
                "plugin": "nf://nf_tests_inventory/nornir_tasks/dummy_with_error.py"
            },
        )
        pprint.pprint(ret, width=150)

        for worker_name, worker_results in ret.items():
            for hostname, host_results in worker_results.items():
                assert (
                    "Traceback" in host_results["dummy"]
                    and "RuntimeError: dummy error" in host_results["dummy"]
                )

    def test_task_with_subtasks(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "task",
            workers=["nornir-worker-1"],
            kwargs={
                "plugin": "nf://nf_tests_inventory/nornir_tasks/dummy_with_subtasks.py"
            },
        )
        pprint.pprint(ret)

        assert ret == {
            "nornir-worker-1": {
                "ceos-spine-1": {
                    "dummy": "dummy task done",
                    "dummy_subtask": "dummy substask done",
                },
                "ceos-spine-2": {
                    "dummy": "dummy task done",
                    "dummy_subtask": "dummy substask done",
                },
            }
        }
