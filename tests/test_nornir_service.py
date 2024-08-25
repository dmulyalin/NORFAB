import pprint
import pytest
import random

# ----------------------------------------------------------------------------
# NORNIR WORKER TESTS
# ----------------------------------------------------------------------------


class TestNornirWorker:
    def test_get_nornir_inventory(self, nfclient):
        ret = nfclient.run_job(b"nornir", "get_nornir_inventory")
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert all(
                k in data["result"] for k in ["hosts", "groups", "defaults"]
            ), f"{worker_name} inventory incomplete"

    def test_get_nornir_hosts(self, nfclient):
        ret = nfclient.run_job(b"nornir", "get_nornir_hosts")
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert isinstance(
                data["result"], list
            ), "{worker_name} did not return a list of hosts"
            assert len(data) > 0 or data == []

    def test_get_nornir_version(self, nfclient):
        ret = nfclient.run_job(b"nornir", "get_nornir_version")
        pprint.pprint(ret)

        assert isinstance(ret, dict), f"Expected dictionary but received {type(ret)}"
        for worker_name, version_report in ret.items():
            for package, version in version_report["result"].items():
                assert version != "", f"{worker_name}:{package} version is empty"


# ----------------------------------------------------------------------------
# NORNIR.CLI FUNCTION TESTS
# ----------------------------------------------------------------------------


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
            for host, res in results["result"].items():
                assert (
                    "show clock" in res and "Traceback" not in res["show clock"]
                ), f"{worker}:{host} show clock output is wrong"
                assert (
                    "show version" in res and "Traceback" not in res["show version"]
                ), f"{worker}:{host} show clock output is wrong"

    def test_commands_cli_dry_run(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "cli",
            kwargs={"commands": ["show version", "show clock"], "cli_dry_run": True},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert "cli_dry_run" in res and res["cli_dry_run"] == [
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

    def test_commands_from_file_cli_dry_run(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "cli",
            kwargs={
                "commands": "nf://nf_tests_inventory/cli/commands.txt",
                "cli_dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert "cli_dry_run" in res and res["cli_dry_run"] == [
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

        assert ret["nornir-worker-1"]["failed"] == True
        assert ret["nornir-worker-1"]["errors"]

    def test_commands_from_file_template(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "cli",
            kwargs={
                "commands": "nf://nf_tests_inventory/cli/show_interfaces.j2",
                "cli_dry_run": True,
            },
        )
        pprint.pprint(ret)

        found_ceos_spine_1 = False
        found_ceos_spine_2 = False

        for worker, results in ret.items():
            for host, res in results["result"].items():
                if host == "ceos-spine-1":
                    found_ceos_spine_1 = True
                    assert "loopback0" in res["cli_dry_run"][0]
                    assert "ethernet1" in res["cli_dry_run"][0]
                elif host == "ceos-spine-2":
                    assert "loopback0" not in res["cli_dry_run"][0]
                    assert "ethernet1" in res["cli_dry_run"][0]
                    found_ceos_spine_2 = True

        assert found_ceos_spine_1, "No results for ceos-spine-1"
        assert found_ceos_spine_2, "No results for ceos-spine-2"

    def test_run_ttp(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "cli",
            workers="nornir-worker-1",
            kwargs={
                "run_ttp": "nf://nf_tests_inventory/ttp/parse_eos_intf.txt",
                "FB": ["ceos-spine-*"],
                "enable": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert "run_ttp" in res, f"{worker}:{host} no run_ttp output"
                for interface in res["run_ttp"]:
                    assert (
                        "interface" in interface
                    ), f"{worker}:{host} run_ttp output is wrong"

    def test_commands_template_with_norfab_client_call(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "cli",
            workers="nornir-worker-1",
            kwargs={
                "commands": "nf://nf_tests_inventory/cli/test_commands_template_with_norfab_call.j2",
                "cli_dry_run": True,
                "FL": ["ceos-spine-1"],
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert all(
                    k in res["cli_dry_run"][0]
                    for k in [
                        "nornir-worker-2",
                        "ceos-leaf-1",
                        "nr_test",
                        "eos-leaf-3",
                        "eos-leaf-2",
                    ]
                ), f"{worker}:{host} output is wrong"

    def test_commands_template_with_nornir_worker_call(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "cli",
            workers="nornir-worker-1",
            kwargs={
                "commands": "nf://nf_tests_inventory/cli/test_commands_template_with_nornir_worker_call.j2",
                "cli_dry_run": True,
                "FL": ["ceos-spine-1", "ceos-spine-2"],
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert all(
                    k in res["cli_dry_run"][0]
                    for k in [
                        "updated by norfab",
                        "interface Ethernet",
                        "interface Loopback",
                        "description",
                    ]
                ), f"{worker}:{host} output is wrong"

    def test_commands_with_tests(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "cli",
            workers="nornir-worker-1",
            kwargs={
                "commands": ["show version", "show clock"],
                "tests": [
                    ["show version", "contains", "cEOS"],
                    ["show clock", "contains", "NTP"],
                ],
                "FL": ["ceos-spine-1", "ceos-spine-2"],
                "remove_tasks": False,
            },
        )
        pprint.pprint(ret)
        
        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert all(
                    k in res 
                    for k in [
                        "show clock", 
                        "show clock contains NTP..",
                        "show version",
                        "show version contains cEOS..",
                    ]
                )
                
    @pytest.mark.skip(reason="TBD")
    def test_commands_with_tf_processor(self, nfclient):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_commands_with_diff_processor(self, nfclient):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_commands_with_diff_processor_diff_last(self, nfclient):
        pass


# ----------------------------------------------------------------------------
# NORNIR.TASK FUNCTION TESTS
# ----------------------------------------------------------------------------


class TestNornirTask:
    def test_task_nornir_salt_nr_test(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "task",
            workers=["nornir-worker-1"],
            kwargs={"plugin": "nornir_salt.plugins.tasks.nr_test", "foo": "bar"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert res == {"nr_test": {"foo": "bar"}}

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
        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert res == {
                    "nr_test": {
                        "changed": False,
                        "connection_retry": 0,
                        "diff": "",
                        "exception": None,
                        "failed": False,
                        "result": {"foo": "bar"},
                        "task_retry": 0,
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

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert res == {"dummy": True}

    def test_task_from_nonexisting_file(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "task",
            workers=["nornir-worker-1"],
            kwargs={"plugin": "nf://nf_tests_inventory/nornir_tasks/_non_existing_.py"},
        )
        pprint.pprint(ret, width=150)

        for worker, results in ret.items():
            assert results["failed"] == True
            assert (
                "nornir-worker-1 - 'nf://nf_tests_inventory/nornir_tasks/_non_existing_.py' task plugin download failed"
                in results["errors"][0]
            )
            assert (
                "nornir-worker-1 - 'nf://nf_tests_inventory/nornir_tasks/_non_existing_.py' task plugin download failed"
                in results["messages"][0]
            )

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

        for worker, results in ret.items():
            assert results["failed"] == True
            assert (
                "No module named 'nornir_salt.plugins.tasks.non_existing_module'"
                in results["errors"][0]
            )
            assert (
                "No module named 'nornir_salt.plugins.tasks.non_existing_module'"
                in results["messages"][0]
            )

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
            for hostname, host_results in worker_results["result"].items():
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

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert res == {
                    "dummy": "dummy task done",
                    "dummy_subtask": "dummy substask done",
                }


# ----------------------------------------------------------------------------
# NORNIR.CFG FUNCTION TESTS
# ----------------------------------------------------------------------------


class TestNornirCfg:
    def test_config_list(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "cfg",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs={"config": ["interface loopback 0", "description RID"]},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert (
                    "netmiko_send_config" in res
                ), f"{worker}:{host} no netmiko_send_config output"
                assert (
                    "Traceback" not in res["netmiko_send_config"]
                ), f"{worker}:{host} cfg output is wrong"

    def test_config_cfg_dry_run(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "cfg",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs={
                "config": ["interface loopback 0", "description RID"],
                "cfg_dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert "cfg_dry_run" in res, f"{worker}:{host} no cfg dry run output"
                assert res["cfg_dry_run"] == [
                    "interface loopback 0",
                    "description RID",
                ], f"{worker}:{host} cfg dry run output is wrong"

    def test_config_with_hosts_filters(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "cfg",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs={
                "config": ["interface loopback 0", "description RID"],
                "FL": ["ceos-leaf-1", "ceos-spine-1"],
                "cfg_dry_run": True,
            },
        )
        pprint.pprint(ret)

        assert (
            len(ret["nornir-worker-1"]["result"]) == 1
        ), f"nornir-worker-1 produced more then 1 host result"
        assert (
            len(ret["nornir-worker-2"]["result"]) == 1
        ), f"nornir-worker-2 produced more then 1 host result"

        assert (
            "ceos-spine-1" in ret["nornir-worker-1"]["result"]
        ), f"nornir-worker-1 no output for ceos-spine-1"
        assert (
            "ceos-leaf-1" in ret["nornir-worker-2"]["result"]
        ), f"nornir-worker-2 no output for ceos-leaf-1"

    def test_config_with_worker_target(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "cfg",
            workers=["nornir-worker-1"],
            kwargs={
                "config": ["interface loopback 0", "description RID"],
                "cfg_dry_run": True,
            },
        )
        pprint.pprint(ret)

        assert len(ret) == 1, f"CFG produced more then 1 worker result"
        assert "nornir-worker-1" in ret, f"No output for nornir-worker-1"

    def test_config_add_details(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "cfg",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs={
                "config": ["interface loopback 0", "description RID"],
                "add_details": True,
                "cfg_dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert "cfg_dry_run" in res, f"{worker}:{host} no cfg_dry_run output"
                assert isinstance(
                    res["cfg_dry_run"], dict
                ), f"{worker}:{host} no detailed output produced"
                assert all(
                    k in res["cfg_dry_run"]
                    for k in [
                        "changed",
                        "connection_retry",
                        "diff",
                        "exception",
                        "failed",
                        "result",
                        "task_retry",
                    ]
                ), f"{worker}:{host} detailed output incomplete"

    def test_config_to_dict_false(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "cfg",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs={
                "config": ["interface loopback 0", "description RID"],
                "to_dict": False,
                "cfg_dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert isinstance(
                results["result"], list
            ), f"{worker} did not return list result"
            for host_res in results["result"]:
                assert (
                    len(host_res) == 3
                ), f"{worker} was expecting 3 items in host result dic, but got more"
                assert all(
                    k in host_res for k in ["name", "result", "host"]
                ), f"{worker} host output incomplete"

    def test_config_to_dict_false_add_details(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "cfg",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs={
                "config": ["interface loopback 0", "description RID"],
                "to_dict": False,
                "cfg_dry_run": True,
                "add_details": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert isinstance(
                results["result"], list
            ), f"{worker} did not return list result"
            for host_res in results["result"]:
                assert (
                    len(host_res) > 3
                ), f"{worker} was expecting more then 3 items in host result dic, but got less"
                assert all(
                    k in host_res
                    for k in [
                        "changed",
                        "connection_retry",
                        "diff",
                        "exception",
                        "failed",
                        "result",
                        "task_retry",
                        "name",
                        "host",
                    ]
                ), f"{worker} host output incomplete"

    def test_config_wrong_plugin(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "cfg",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs={
                "config": ["interface loopback 0", "description RID"],
                "cfg_dry_run": True,
                "plugin": "wrong_plugin",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert (
                "UnsupportedPluginError" in results["errors"][0]
            ), f"{worker} did not raise error"

    def test_config_from_file_cfg_dry_run(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "cfg",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs={
                "config": "nf://nf_tests_inventory/cfg/config_1.txt",
                "cfg_dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert "cfg_dry_run" in res, f"{worker}:{host} no cfg dry run output"
                assert res["cfg_dry_run"] == [
                    "interface Loopback0\ndescription RID"
                ], f"{worker}:{host} cfg dry run output is wrong"

    def test_config_from_nonexisting_file(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "cfg",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs={
                "config": "nf://nf_tests_inventory/cfg/config_non_existing.txt",
                "cfg_dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert "FileNotFoundError" in results["errors"][0]

    def test_config_from_file_template(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "cfg",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs={
                "config": "nf://nf_tests_inventory/cfg/config_2.txt",
                "cfg_dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host_name, res in results["result"].items():
                assert (
                    "cfg_dry_run" in res
                ), f"{worker}:{host_name} no cfg dry run output"
                assert (
                    "interface Loopback0\ndescription RID for " in res["cfg_dry_run"][0]
                ), f"{worker}:{host_name} cfg dry run output is wrong"
                assert (
                    host_name in res["cfg_dry_run"][0]
                ), f"{worker}:{host_name} cfg dry run output is not rendered"

    def test_config_plugin_napalm(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "cfg",
            workers=["nornir-worker-1"],
            kwargs={
                "config": [
                    "interface loopback 123",
                    f"description RID {random.randint(0, 1000)}",
                ],
                "plugin": "napalm",
                "add_details": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert (
                    "napalm_configure" in res
                ), f"{worker}:{host} no napalm_configure output"
                assert (
                    res["napalm_configure"]["result"] is None
                ), f"{worker}:{host} cfg output is wrong"
                assert (
                    res["napalm_configure"]["diff"] is not None
                ), f"{worker}:{host} cfg output no diff"

    def test_config_plugin_scrapli(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "cfg",
            workers=["nornir-worker-1"],
            kwargs={
                "config": ["interface loopback 0", "description RID"],
                "plugin": "scrapli",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert (
                    "scrapli_send_config" in res
                ), f"{worker}:{host} no scrapli_send_config output"
                assert (
                    "Traceback" not in res["scrapli_send_config"]
                ), f"{worker}:{host} cfg output is wrong"

    def test_config_plugin_netmiko(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "cfg",
            workers=["nornir-worker-1"],
            kwargs={
                "config": ["interface loopback 0", "description RID"],
                "plugin": "netmiko",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert (
                    "netmiko_send_config" in res
                ), f"{worker}:{host} no netmiko_send_config output"
                assert (
                    "Traceback" not in res["netmiko_send_config"]
                ), f"{worker}:{host} cfg output is wrong"


# ----------------------------------------------------------------------------
# NORNIR.TEST FUNCTION TESTS
# ----------------------------------------------------------------------------


class TestNornirTests:
    def test_nornir_test_suite(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={"suite": "nf://nf_tests_inventory/nornir_test_suites/suite_1.txt"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results, f"{worker} returned no test results"
            for host, res in results["result"].items():
                for test_name, test_res in res.items():
                    assert (
                        "Traceback" not in test_res
                    ), f"{worker}:{host}:{test_name} test output contains error"
                    assert test_res in [
                        "PASS",
                        "FAIL",
                    ], f"{worker}:{host}:{test_name} unexpected test result"

    def test_nornir_test_suite_template(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={"suite": "nf://nf_tests_inventory/nornir_test_suites/suite_2.txt"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results, f"{worker} returned no test results"
            for host, res in results["result"].items():
                for test_name, test_res in res.items():
                    assert (
                        "Traceback" not in test_res
                    ), f"{worker}:{host}:{test_name} test output contains error"
                    assert test_res in [
                        "PASS",
                        "FAIL",
                    ], f"{worker}:{host}:{test_name} unexpected test result"

    def test_nornir_test_suite_subset(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nf_tests_inventory/nornir_test_suites/suite_1.txt",
                "subset": "check*version",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results, f"{worker} returned no test results"
            for host, res in results["result"].items():
                assert (
                    len(res) == 1
                ), f"{worker}:{host} was expecting results for single test only"
                assert (
                    "check ceos version" in res
                ), f"{worker}:{host} was expecting 'check ceos version' results"

    def test_nornir_test_dry_run(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nf_tests_inventory/nornir_test_suites/suite_1.txt",
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results, f"{worker} returned no test results"
            for host, res in results["result"].items():
                assert (
                    "tests_dry_run" in res
                ), f"{worker}:{host} no tests_dry_run results"
                assert isinstance(
                    res["tests_dry_run"], list
                ), f"{worker}:{host} was expecting list of tests"
                for i in res["tests_dry_run"]:
                    assert all(
                        k in i for k in ["name", "pattern", "task", "test"]
                    ), f"{worker}:{host} test missing some keys"

    def test_nornir_test_to_dict_true(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nf_tests_inventory/nornir_test_suites/suite_1.txt",
                "to_dict": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results, f"{worker} returned no test results"
            for host, res in results["result"].items():
                for test_name, test_res in res.items():
                    assert (
                        "Traceback" not in test_res
                    ), f"{worker}:{host}:{test_name} test output contains error"
                    assert test_res in [
                        "PASS",
                        "FAIL",
                    ], f"{worker}:{host}:{test_name} unexpected test result"

    def test_nornir_test_to_dict_false(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nf_tests_inventory/nornir_test_suites/suite_1.txt",
                "to_dict": False,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            assert isinstance(results["result"], list)
            for i in results["result"]:
                assert all(
                    k in i for k in ["host", "name", "result"]
                ), f"{worker} test output does not contains all keys"

    def test_nornir_test_remove_tasks_false(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nf_tests_inventory/nornir_test_suites/suite_1.txt",
                "remove_tasks": False,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                assert len(res) > 2, f"{worker}:{host} not having tasks output"
                for task_name, task_res in res.items():
                    assert (
                        "Traceback" not in task_res
                    ), f"{worker}:{host}:{test_name} test output contains error"

    def test_nornir_test_failed_only_true(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nf_tests_inventory/nornir_test_suites/suite_1.txt",
                "failed_only": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results, f"{worker} returned no test results"
            for host, res in results["result"].items():
                for test_name, test_res in res.items():
                    assert (
                        "Traceback" not in test_res
                    ), f"{worker}:{host}:{test_name} test output contains error"
                    assert test_res in [
                        "FAIL"
                    ], f"{worker}:{host}:{test_name} unexpected test result"

    def test_nornir_test_suite_non_existing_file(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nf_tests_inventory/nornir_test_suites/suite_non_existing.txt"
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert (
                "suite download failed" in results["errors"][0]
            ), f"{worker} was expecting download to fail"

    def test_nornir_test_suite_bad_yaml_file(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nf_tests_inventory/nornir_test_suites/suite_bad_yaml.txt"
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert (
                "YAML load failed" in results["errors"][0]
            ), f"{worker} was expecting YAML load to fail"

    def test_nornir_test_suite_bad_jinja2(self, nfclient):
        ret = nfclient.run_job(
            b"nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nf_tests_inventory/nornir_test_suites/suite_bad_jinja2.txt"
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert (
                "Jinja2 rendering failed" in results["errors"][0]
            ), f"{worker} was expecting Jinja2 rendering to fail"


# ----------------------------------------------------------------------------
# NORNIR.NETWORK FUNCTION TESTS
# ----------------------------------------------------------------------------


class TestNornirNetwork:
    def test_nornir_network_ping(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "network",
            workers=["nornir-worker-1"],
            kwargs={"fun": "ping", "FC": "ceos"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                assert "ping" in res, f"{worker}:{host} did not return ping result"
                assert (
                    "Reply from" in res["ping"]
                ), f"{worker}:{host} ping result is not good"

    def test_nornir_network_ping_with_count(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "network",
            workers=["nornir-worker-1"],
            kwargs={"fun": "ping", "FC": "ceos", "count": 2},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                assert "ping" in res, f"{worker}:{host} did not return ping result"
                assert (
                    "Reply from" in res["ping"]
                ), f"{worker}:{host} ping result is not good"
                assert (
                    res["ping"].count("Reply from") == 2
                ), f"{worker}:{host} ping result did not get 2 replies"

    @pytest.mark.skip(reason="TBD")
    def test_nornir_network_resolve_dns(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "network",
            workers=["nornir-worker-1"],
            kwargs={"fun": "resolve_dns", "FC": "ceos"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                assert "ping" in res, f"{worker}:{host} did not return ping result"
                assert (
                    "Reply from" in res["ping"]
                ), f"{worker}:{host} ping result is not good"
