import logging
import pprint
import yaml

from norfab.core.nfapi import NorFab
from robot.api.deco import keyword
from robot.api import ContinuableFailure, FatalError, Error
from robot.api import logger
from nornir_salt.plugins.functions import TabulateFormatter

log = logging.getLogger(__name__)

# Global vars
DATA = {}


def clean_global_data():
    global DATA
    DATA.clear()


class NorFabRobot:
    ROBOT_LIBRARY_SCOPE = "GLOBAL"
    ROBOT_AUTO_KEYWORDS = False
    ROBOT_LIBRARY_DOC_FORMAT = "reST"  # reStructuredText
    ROBOT_LISTENER_API_VERSION = 3

    def __init__(
        self,
        inventory="./inventory.yaml",
        log_level="WARNING",
    ):
        self.ROBOT_LIBRARY_LISTENER = self

        # initiate NorFab
        self.nf = NorFab(inventory=inventory, log_level=log_level)
        self.nf.start()
        self.client = self.nf.make_client()

    def start_suite(self, data, result):
        pass

    def end_suite(self, data, result):
        print(f"NorFab ROBOT - Exiting")
        self.nf.destroy()

    @keyword("Workers")
    def workers(self, *args, **kwargs):
        """Collect workers to target"""
        if args:
            DATA["workers"] = args
        else:
            DATA["workers"] = kwargs.pop("workers", "all")

    @keyword("Hosts")
    def hosts(self, *args, **kwargs):
        """Collect hosts to target"""
        if args:
            DATA["hosts"] = {"FB": ", ".join(args), **kwargs}
        else:
            DATA["hosts"] = kwargs

    @keyword("nr.test")
    def nr_test(self, *args, **kwargs):
        """Run nr.test  task"""
        tests_pass = 0
        tests_fail = 0
        tests_results = []
        commands_output = {}
        if args:
            kwargs["suite"] = args[0]
        kwargs = {
            **DATA.pop("hosts", {"FB": "*"}),
            **kwargs,
            "remove_tasks": False,
            "add_details": True,
            "return_tests_suite": True,
            "to_dict": False,
        }
        logger.info(f"Running nr.test with kwargs '{kwargs}', global DATA '{DATA}'")
        has_errors = False
        # run this function
        ret = self.client.run_job(
            service="nornir",
            task="test",
            workers=DATA.get("workers", "all"),
            kwargs=kwargs,
        )
        # iterate over results and log tests and task statuses
        for worker, worker_results in ret.items():
            for result in worker_results["result"]["test_results"]:
                host = result["host"]
                # evaluate and log test result
                if "success" in result:
                    if (
                        result["failed"]
                        or result["exception"]
                        or not result["success"]
                        or "traceback" in str(result["result"]).lower()
                    ):
                        tests_fail += 1
                        has_errors = True
                        logger.error(
                            (
                                f'{worker} worker, {host} test "{result["name"]}" - '
                                f'<span style="background-color: #CE3E01">"{result["exception"]}"</span>'
                            ),
                            html=True,
                        )
                    else:
                        tests_pass += 1
                        logger.info(
                            (
                                f'{worker} worker, {host} test "{result["name"]}" - '
                                f'<span style="background-color: #97BD61">success</span>'
                            ),
                            html=True,
                        )
                    # save test results to log them later
                    tests_results.append({"worker": worker, **result})
                # evaluate and log task result
                else:
                    # log exception for task
                    if result["failed"] or result["exception"]:
                        has_errors = True
                        logger.error(
                            (
                                f'{worker} worker, {host} task "{result["name"]}" - '
                                f'<span style="background-color: #CE3E01">"{result["exception"].strip()}"</span>'
                            ),
                            html=True,
                        )
                    # save device commands output to log it later
                    commands_output.setdefault(host, {})
                    commands_output[host][result["name"]] = result["result"]
        # clear global state to prep for next test
        clean_global_data()

        tests_results_html_table = TabulateFormatter(
            tests_results,
            tabulate={"tablefmt": "html"},
            headers=[
                "worker",
                "host",
                "name",
                "result",
                "failed",
                "task",
                "test",
                "criteria",
                "exception",
            ],
        )

        tests_results_csv_table = [
            f'''"{i['worker']}","{i['host']}","{i['name']}","{i['result']}","{i['failed']}","{i['task']}","{i['test']}","{i['criteria']}","{i['exception']}"'''
            for i in tests_results
        ]
        tests_results_csv_table.insert(
            0,
            '"worker","host","name","result","failed","task","test","criteria","exception"',
        )
        tests_results_csv_table = "\n".join(tests_results_csv_table)

        # form nested HTML of commands output
        devices_output_html = []
        for host in sorted(commands_output.keys()):
            commands = commands_output[host]
            commands_output_html = []
            for command, result in commands.items():
                commands_output_html.append(
                    f'<p><details style="margin-left:20px;"><summary>{command}</summary><p style="margin-left:20px;"><font face="courier new">{result}</font></p></details></p>'
                )
            devices_output_html.append(
                f'<p><details><summary>{host} ({len(commands_output_html)} commands)</summary><p>{"".join(commands_output_html)}</p></details></p>'
            )

        # form nested HTML for devices tes suite
        devices_test_suite = []
        for worker, worker_results in ret.items():
            for host in sorted(worker_results["result"]["suite"].keys()):
                suite_content = worker_results["result"]["suite"][host]
                devices_test_suite.append(
                    f'<p><details><summary>{host} ({len(suite_content)} tests)</summary><p style="margin-left:20px;">{yaml.dump(suite_content, default_flow_style=False)}</p></details></p>'
                )

        logger.info(
            f"<details><summary>Workers results</summary>{pprint.pformat(ret)}</details>",
            html=True,
        )
        logger.info(
            f"<details><summary>Test suite results details</summary><p>{tests_results_html_table}</p></details>",
            html=True,
        )
        logger.info(
            f"<details><summary>Test suite results CSV table</summary><p>{tests_results_csv_table}</p></details>",
            html=True,
        )
        logger.info(
            f"<details><summary>Devices tests suites content</summary>{''.join(devices_test_suite)}</details>",
            html=True,
        )
        logger.info(
            f"<details><summary>Collected devices output</summary>{''.join(devices_output_html)}</details>",
            html=True,
        )
        logger.info(
            (
                f"Tests completed - {tests_pass + tests_fail}, "
                f'<span style="background-color: #97BD61">success - {tests_pass}</span>, '
                f'<span style="background-color: #CE3E01">failed - {tests_fail}</span>'
            ),
            html=True,
        )

        # raise if has errors
        if has_errors:
            raise ContinuableFailure("Tests failed")
        # return test results with no errors in structured format
        return ret

    @keyword("nr.cli")
    def nr_cli(self, *args, **kwargs):
        """Run Nornir service cli task"""
        log.info(
            f"Running nr.cli with args '{args}', kwargs '{kwargs}', global DATA '{DATA}'"
        )
        has_errors = False
        if args:
            kwargs["commands"] = args
        kwargs = {
            **DATA.pop("hosts", {"FB": "*"}),
            **kwargs,
            "add_details": True,
            "to_dict": False,
        }
        # run this function
        ret = self.client.run_job(
            service="nornir",
            task="cli",
            workers=DATA.get("workers", "all"),
            kwargs=kwargs,
        )
        # extract results for the host
        for worker, worker_results in ret.items():
            for result in worker_results["result"]:
                host = result["host"]
                # evaluate and log results
                if (
                    result["failed"]
                    or result["exception"]
                    or "traceback" in str(result["result"]).lower()
                ):
                    has_errors = True
                    logger.error(
                        (
                            f'<details><summary>{worker} worker, {host} device, comand "{result["name"]}" failed - '
                            f'<span style="background-color: #CE3E01">"{result["exception"]}"</span></summary>'
                            f'<p style="margin-left:20px;"><font face="courier new">{result["result"]}'
                            f"</font></p></details>"
                        ),
                        html=True,
                    )
                else:
                    logger.info(
                        (
                            f'<details><summary>{worker} worker, {host} device, command "{result["name"]}" - '
                            f'<span style="background-color: #97BD61">success</span></summary>'
                            f'<p style="margin-left:20px;"><font face="courier new">{result["result"]}'
                            f"</font></p></details>"
                        ),
                        html=True,
                    )
        logger.info(
            f"<details><summary>Workers results</summary>{pprint.pformat(ret)}</details>",
            html=True,
        )
        # clean global state to prep for next test
        clean_global_data()
        # raise exception if cli command failed
        if has_errors:
            raise ContinuableFailure(ret)
        # return ret with no errors in structured format
        return ret

    @keyword("nr.cfg")
    def nr_cfg(self, *args, **kwargs):
        """Run Nornir service cfg task"""
        log.info(
            f"Running nr.cfg with args '{args}', kwargs '{kwargs}', global DATA '{DATA}'"
        )
        if args:
            kwargs["config"] = args
        kwargs = {
            **DATA.pop("hosts", {"FB": "*"}),
            **kwargs,
            "add_details": True,
            "to_dict": False,
        }
        has_errors = False
        # run this function
        ret = self.client.run_job(
            service="nornir",
            task="cfg",
            workers=DATA.get("workers", "all"),
            kwargs=kwargs,
        )
        # extract results for the host
        for worker, worker_results in ret.items():
            for result in worker_results["result"]:
                host = result["host"]
                # evaluate and log results
                if (
                    result["failed"]
                    or result["exception"]
                    or "traceback" in str(result["result"]).lower()
                ):
                    has_errors = True
                    logger.error(
                        (
                            f'<details><summary>{worker} worker, {host} device, "{result["name"]}" failed - '
                            f'<span style="background-color: #CE3E01">"{result["exception"]}"</span></summary>'
                            f'<p style="margin-left:20px;"><font face="courier new">{result["result"]}'
                            f"</font></p></details>"
                        ),
                        html=True,
                    )
                else:
                    logger.info(
                        (
                            f'<details><summary>{worker} worker, {host} device, "{result["name"]}" - '
                            f'<span style="background-color: #97BD61">success</span></summary>'
                            f'<p style="margin-left:20px;"><font face="courier new">{result["result"]}'
                            f"</font></p></details>"
                        ),
                        html=True,
                    )
        logger.info(
            f"<details><summary>Workers results</summary>{pprint.pformat(ret)}</details>",
            html=True,
        )
        # clean global state to prep for next test
        clean_global_data()
        # raise exception if cli command failed
        if has_errors:
            raise ContinuableFailure(ret)
        # return ret with no errors in structured format
        return ret
