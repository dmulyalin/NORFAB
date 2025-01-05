import pprint
import pytest
import random
import socket

# check if has access to juniper device
vmx_1_ip = "192.168.1.130"
vmx_1_port = 2205
try:
    s = socket.socket()
    s.settimeout(5)
    s.connect((vmx_1_ip, vmx_1_port))
    has_vmx_1 = True
except:
    has_vmx_1 = False

skip_if_not_has_vmx_1 = pytest.mark.skipif(
    has_vmx_1 == False,
    reason=f"Has no connection to juniper router {vmx_1_ip}:{vmx_1_port}",
)


class TestJunipervMX:
    cli_plugins = ["netmiko", "scrapli", "napalm"]

    @skip_if_not_has_vmx_1
    @pytest.mark.parametrize("plugin", cli_plugins)
    def test_nornir_cli(self, nfclient, plugin):
        commands = ["show version", "show configuration | display set"]
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-6"],
            kwargs={
                "commands": commands,
                "plugin": plugin,
            },
        )

        pprint.pprint(ret, width=150)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            for host, res in results["result"].items():
                for command in commands:
                    assert res[command], f"{host} - show command is wrong"
