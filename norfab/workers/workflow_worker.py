import json
import logging
import sys
import importlib.metadata
import yaml
import os
from norfab.core.worker import NFPWorker, Result
from typing import Union, Dict, List

SERVICE = "workflow"

log = logging.getLogger(__name__)


class WorkflowWorker(NFPWorker):
    """ """

    def __init__(
        self,
        inventory,
        broker: str,
        worker_name: str,
        exit_event=None,
        init_done_event=None,
        log_level: str = "WARNING",
        log_queue: object = None,
    ):
        super().__init__(
            inventory, broker, SERVICE, worker_name, exit_event, log_level, log_queue
        )
        self.init_done_event = init_done_event

        # get inventory from broker
        self.workflow_worker_inventory = self.load_inventory()

        self.init_done_event.set()
        log.info(f"{self.name} - Started")

    def worker_exit(self):
        pass

    def get_version(self):
        """
        Generate a report of the versions of specific Python packages and system information.

        This method collects the version information of several Python packages and system details,
        including the Python version, platform, and a specified language model.

        Returns:
            Result: An object containing a dictionary with the package names as keys and their
                    respective version numbers as values. If a package is not found, its version
                    will be an empty string.
        """
        libs = {
            "norfab": "",
            "python": sys.version.split(" ")[0],
            "platform": sys.platform,
        }
        # get version of packages installed
        for pkg in libs.keys():
            try:
                libs[pkg] = importlib.metadata.version(pkg)
            except importlib.metadata.PackageNotFoundError:
                pass

        return Result(result=libs)

    def get_inventory(self):
        """
        NorFab task to retrieve the workflow's worker inventory.

        Returns:
            Result: An instance of the Result class containing the workflow's worker inventory.
        """
        return Result(result=self.workflow_worker_inventory)

    def remove_empty_results(self, results: Dict) -> Dict:
        """
        Remove empty results from the workflow results.

        Args:
            results (Dict): The workflow results.

        Returns:
            Dict: The workflow results with empty results removed.
        """
        ret = {}
        for step, task_results in results.items():
            ret[step] = {}
            for worker_name, worker_result in task_results.items():
                # add non empty results for tasks that did not fail
                if worker_result["failed"] is False:
                    if worker_result["result"]:
                        ret[step][worker_name] = worker_result
                # add failed tasks irregardless of result content
                else:
                    ret[step][worker_name] = worker_result
        return ret

    def run(
        self, workflow: Union[str, Dict], remove_empty_results: bool = True
    ) -> Dict:
        ret = Result(task=f"{self.name}:run", result={})

        if self.is_url(workflow):
            workflow_name = (
                os.path.split(workflow)[-1].replace(".yaml", "").replace(".yml", "")
            )
            workflow = self.jinja2_render_templates([workflow])
            workflow = yaml.safe_load(workflow)
            workflow_name = workflow.get("name", workflow_name)
        else:
            workflow_name = workflow.get("name", "workflow")

        self.event(f"Starting workflow '{workflow_name}'")

        ret.result[workflow_name] = {}

        for step, data in workflow["steps"].items():

            self.event(f"Doing workflow step '{step}'")

            ret.result[workflow_name][step] = self.client.run_job(
                service=data["service"],
                task=data["task"],
                workers=data.get("workers", "all"),
                kwargs=data.get("kwargs", {}),
                args=data.get("args", []),
                timeout=data.get("timeout", 600),
            )

        if remove_empty_results:
            ret.result[workflow_name] = self.remove_empty_results(
                ret.result[workflow_name]
            )

        return ret
