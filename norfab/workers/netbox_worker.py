import json
import logging
import sys
import importlib.metadata
import requests
import copy
import os
import concurrent.futures
import pynetbox

from fnmatch import fnmatchcase
from datetime import datetime, timedelta
from norfab.core.worker import NFPWorker, Result
from typing import Union
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from norfab.core.exceptions import UnsupportedServiceError
from diskcache import FanoutCache

SERVICE = "netbox"

log = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# HELPER FUNCTIONS
# ----------------------------------------------------------------------


def _form_query_v4(obj, filters, fields, alias=None):
    """
    Helper function to form graphql query for Netbox version 4.

    Args:
        obj (str): The object to return data for, e.g., 'device', 'interface', 'ip_address'.
        filters (dict): A dictionary of key-value pairs to filter by.
        fields (list): A list of data fields to return.
        alias (str, optional): An alias value for the requested object.

    Returns:
        str: A formatted GraphQL query string.
    """
    filters_list = []
    for k, v in filters.items():
        if isinstance(v, (list, set, tuple)):
            items = ", ".join(f'"{i}"' for i in v)
            filters_list.append(f"{k}: [{items}]")
        elif "{" in v and "}" in v:
            filters_list.append(f"{k}: {v}")
        else:
            filters_list.append(f'{k}: "{v}"')
    filters_string = ", ".join(filters_list)
    filters_string = filters_string.replace("'", '"')  # swap quotes
    fields = " ".join(fields)
    if alias:
        query = f"{alias}: {obj}(filters: {{{filters_string}}}) {{{fields}}}"
    else:
        query = f"{obj}(filters: {{{filters_string}}}) {{{fields}}}"

    return query


def _form_query_v3(obj, filters, fields, alias=None):
    """
    Helper function to form graphql query for Netbox version 3.

    Args:
        obj (str): The object to return data for, e.g., 'device', 'interface', 'ip_address'.
        filters (dict): A dictionary of key-value pairs to filter by.
        fields (list): A list of data fields to return.
        alias (str, optional): An alias value for the requested object.

    Returns:
        str: A formatted GraphQL query string.
    """
    filters_list = []
    for k, v in filters.items():
        if isinstance(v, (list, set, tuple)):
            items = ", ".join(f'"{i}"' for i in v)
            filters_list.append(f"{k}: [{items}]")
        else:
            filters_list.append(f'{k}: "{v}"')
    filters_string = ", ".join(filters_list)
    fields = " ".join(fields)
    if alias:
        query = f"{alias}: {obj}({filters_string}) {{{fields}}}"
    else:
        query = f"{obj}({filters_string}) {{{fields}}}"

    return query


class NetboxWorker(NFPWorker):
    """
    NetboxWorker class for interacting with Netbox API and managing inventory.

    Args:
        inventory (dict): The inventory data.
        broker (object): The broker instance.
        worker_name (str): The name of the worker.
        exit_event (threading.Event, optional): Event to signal exit.
        init_done_event (threading.Event, optional): Event to signal initialization completion.
        log_level (int, optional): Logging level.
        log_queue (object, optional): Queue for logging.

    Raises:
        AssertionError: If the inventory has no Netbox instances.

    Attributes:
        default_instance (str): Default Netbox instance name.
        inventory (dict): Inventory data.
        nb_version (tuple): Netbox version.
        compatible_ge_v3 (tuple): Minimum supported Netbox v3 version.
        compatible_ge_v4 (tuple): Minimum supported Netbox v4 version.
    """

    default_instance = None
    inventory = None
    nb_version = None
    compatible_ge_v3 = (
        3,
        6,
        0,
    )  # 3.6.0 - minimum supported Netbox v3
    compatible_ge_v4 = (
        4,
        0,
        5,
    )  # 4.0.5 - minimum supported Netbox v4

    def __init__(
        self,
        inventory,
        broker,
        worker_name,
        exit_event=None,
        init_done_event=None,
        log_level=None,
        log_queue: object = None,
    ):
        super().__init__(
            inventory, broker, SERVICE, worker_name, exit_event, log_level, log_queue
        )
        self.init_done_event = init_done_event
        self.cache = None

        # get inventory from broker
        self.netbox_inventory = self.load_inventory()
        if not self.netbox_inventory:
            log.critical(
                f"{self.name} - Broker {self.broker} returned no inventory for {self.name}, killing myself..."
            )
            self.destroy()

        assert self.netbox_inventory.get(
            "instances"
        ), f"{self.name} - inventory has no Netbox instances"

        # extract parameters from imvemtory
        self.netbox_connect_timeout = self.netbox_inventory.get(
            "netbox_connect_timeout", 10
        )
        self.netbox_read_timeout = self.netbox_inventory.get("netbox_read_timeout", 300)
        self.cache_use = self.netbox_inventory.get("cache_use", True)
        self.cache_ttl = self.netbox_inventory.get("cache_ttl", 31557600)  # 1 Year

        # find default instance
        for name, params in self.netbox_inventory["instances"].items():
            if params.get("default") is True:
                self.default_instance = name
                break
        else:
            self.default_instance = name

        # check Netbox compatibility
        self._verify_compatibility()

        # instantiate cache
        self.cache_dir = os.path.join(self.base_dir, "cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.cache = self._get_diskcache()

        self.init_done_event.set()
        log.info(f"{self.name} - Started")

    def worker_exit(self) -> None:
        """
        Worker exist sanity checks. Closes the cache if it exists.

        This method checks if the cache attribute is present and not None.
        If the cache exists, it closes the cache to release any resources
        associated with it.
        """
        if self.cache:
            self.cache.close()

    # ----------------------------------------------------------------------
    # Netbox Service Functions that exposed for calling
    # ----------------------------------------------------------------------

    def get_inventory(self) -> dict:
        """
        NorFab Task to return running inventory for NetBox worker.

        Returns:
            dict: A dictionary containing the NetBox inventory.
        """
        return Result(
            task=f"{self.name}:get_inventory", result=dict(self.netbox_inventory)
        )

    def get_version(self, **kwargs) -> dict:
        """
        Retrieves the version information of specified libraries and system details.

        Returns:
            dict: A dictionary containing the version information of the
                specified libraries and system details.
        """
        libs = {
            "norfab": "",
            "pynetbox": "",
            "requests": "",
            "python": sys.version.split(" ")[0],
            "platform": sys.platform,
        }
        # get version of packages installed
        for pkg in libs.keys():
            try:
                libs[pkg] = importlib.metadata.version(pkg)
            except importlib.metadata.PackageNotFoundError:
                pass

        return Result(task=f"{self.name}:get_version", result=libs)

    def get_netbox_status(self, instance=None) -> dict:
        """
        Retrieve the status of NetBox instances.

        This method queries the status of a specific NetBox instance if the
        `instance` parameter is provided. If no instance is specified, it
        queries the status of all instances in the NetBox inventory.

        Args:
            instance (str, optional): The name of the specific NetBox instance
                                      to query.

        Returns:
            dict: A dictionary containing the status of the requested NetBox
                  instance(s).
        """
        ret = Result(result={}, task=f"{self.name}:get_netbox_status")
        if instance:
            ret.result[instance] = self._query_netbox_status(instance)
        else:
            for name in self.netbox_inventory["instances"].keys():
                ret.result[name] = self._query_netbox_status(name)
        return ret

    def get_compatibility(self) -> dict:
        """
        Checks the compatibility of Netbox instances based on their version.

        This method retrieves the status and version of Netbox instances and determines
        if they are compatible with the required versions. It logs a warning if any
        instance is not reachable.

        Returns:
            dict: A dictionary where the keys are the instance names and the values are
                  booleans indicating compatibility (True/False) or None if the instance
                  is not reachable.
        """
        ret = Result(task=f"{self.name}:get_compatibility", result={})
        netbox_status = self.get_netbox_status()
        for instance, params in netbox_status.result.items():
            if params["status"] is not True:
                log.warning(f"{self.name} - {instance} Netbox instance not reachable")
                ret.result[instance] = None
            else:
                self.nb_version = tuple(
                    [int(i) for i in params["netbox-version"].split(".")]
                )
                if self.nb_version[0] == 3:  # check Netbox 3 compatibility
                    ret.result[instance] = self.nb_version >= self.compatible_ge_v3
                elif self.nb_version[0] == 4:  # check Netbox 4 compatibility
                    ret.result[instance] = self.nb_version >= self.compatible_ge_v4

        return ret

    def _verify_compatibility(self):
        """
        Verifies the compatibility of Netbox instances.

        This method checks the compatibility of Netbox instances by calling the
        `get_compatibility` method. If any of the instances are not compatible,
        it raises a RuntimeError with a message indicating which instances are
        not compatible.

        Raises:
            RuntimeError: If any of the Netbox instances are not compatible.
        """
        compatibility = self.get_compatibility()
        if not all(i is not False for i in compatibility.result.values()):
            raise RuntimeError(
                f"{self.name} - not all Netbox instances are compatible: {compatibility.result}"
            )

    def _query_netbox_status(self, name):
        """
        Queries the Netbox API for the status of a given instance.

        Args:
            name (str): The name of the Netbox instance to query.

        Returns:
            dict: A dictionary containing the status and any error message. The dictionary has the following keys:

                - "error" (str or None): Error message if the query failed, otherwise None.
                - "status" (bool): True if the query was successful, False otherwise.
                - Additional keys from the Netbox API response if the query was successful.

        Raises:
            None: All exceptions are caught and handled within the method.
        """
        params = self.netbox_inventory["instances"][name]
        ret = {
            "error": None,
            "status": True,
        }
        try:
            response = requests.get(
                f"{params['url']}/api/status",
                verify=params.get("ssl_verify", True),
                timeout=(self.netbox_connect_timeout, self.netbox_read_timeout),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Token {params['token']}",
                },
            )
            response.raise_for_status()
            ret.update(response.json())
        except Exception as e:
            ret["status"] = False
            msg = (
                f"{self.name} - failed to query Netbox API URL "
                f"'{params['url']}', token ends "
                f"with '..{params['token'][-6:]}'; error: '{e}'"
            )
            log.error(msg)
            ret["error"] = msg

        return ret

    def _get_instance_params(self, name: str) -> dict:
        """
        Retrieve instance parameters from the NetBox inventory.

        Args:
            name (str): The name of the instance to retrieve parameters for.

        Returns:
            dict: A dictionary containing the parameters of the specified instance.

        Raises:
            KeyError: If the specified instance name is not found in the inventory.

        If the `ssl_verify` parameter is set to False, SSL warnings will be disabled.
        Otherwise, SSL warnings will be enabled.
        """

        if name:
            ret = self.netbox_inventory["instances"][name]
        else:
            ret = self.netbox_inventory["instances"][self.default_instance]

        # check if need to disable SSL warnings
        if ret.get("ssl_verify") == False:
            requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
        else:
            requests.packages.urllib3.enable_warnings(InsecureRequestWarning)

        return ret

    def _get_pynetbox(self, instance):
        """
        Helper function to instantiate a pynetbox API object.

        Args:
            instance (str): The instance name for which to get the pynetbox API object.

        Returns:
            pynetbox.core.api.Api: An instantiated pynetbox API object.

        Raises:
            Exception: If the pynetbox library is not installed.

        If SSL verification is disabled in the instance parameters,
        this function will disable warnings for insecure requests.
        """
        params = self._get_instance_params(instance)

        if params.get("ssl_verify") == False:
            requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
            nb = pynetbox.api(url=params["url"], token=params["token"])
            nb.http_session.verify = False
        else:
            nb = pynetbox.api(url=params["url"], token=params["token"])

        return nb

    def _get_diskcache(self) -> FanoutCache:
        """
        Creates and returns a FanoutCache object.

        The FanoutCache is configured with the specified directory, number of shards,
        timeout, and size limit.

        Returns:
            FanoutCache: A configured FanoutCache instance.
        """
        return FanoutCache(
            directory=self.cache_dir,
            shards=4,
            timeout=1,  # 1 second
            size_limit=1073741824,  #  GigaByte
        )

    def cache_list(self, keys="*", details=False) -> list:
        """
        Retrieve a list of cache keys, optionally with details about each key.

        Args:
            keys (str): A pattern to match cache keys against. Defaults to "*".
            details (bool): If True, include detailed information about each cache key. Defaults to False.

        Returns:
            list: A list of cache keys or a list of dictionaries with detailed information if `details` is True.
        """
        self.cache.expire()
        ret = Result(task=f"{self.name}:cache_list", result=[])
        for cache_key in self.cache:
            if fnmatchcase(cache_key, keys):
                if details:
                    _, expires = self.cache.get(cache_key, expire_time=True)
                    expires = datetime.fromtimestamp(expires)
                    creation = expires - timedelta(seconds=self.cache_ttl)
                    age = datetime.now() - creation
                    ret.result.append(
                        {
                            "key": cache_key,
                            "age": str(age),
                            "creation": str(creation),
                            "expires": str(expires),
                        }
                    )
                else:
                    ret.result.append(cache_key)
        return ret

    def cache_clear(self, key=None, keys=None) -> list:
        """
        Clears specified keys from the cache.

        Args:
            key (str, optional): A specific key to remove from the cache.
            keys (str, optional): A glob pattern to match multiple keys to remove from the cache.

        Returns:
            list: A list of keys that were successfully removed from the cache.

        Raises:
            RuntimeError: If a specified key or a key matching the glob pattern could not be removed from the cache.

        Notes:

        - If neither `key` nor `keys` is provided, the function will return a message indicating that there is nothing to clear.
        - If `key` is provided, it will attempt to remove that specific key from the cache.
        - If `keys` is provided, it will attempt to remove all keys matching the glob pattern from the cache.
        """
        ret = Result(task=f"{self.name}:cache_clear", result=[])
        # check if has keys to clear
        if key == keys == None:
            ret.result = "Noting to clear, specify key or keys"
            return ret
        # remove specific key from cache
        if key:
            if key in self.cache:
                if self.cache.delete(key, retry=True):
                    ret.result.append(key)
                else:
                    raise RuntimeError(f"Failed to remove {key} from cache")
            else:
                ret.messages.append(f"Key {key} not in cache.")
        # remove all keys matching glob pattern
        if keys:
            for cache_key in self.cache:
                if fnmatchcase(cache_key, keys):
                    if self.cache.delete(cache_key, retry=True):
                        ret.result.append(cache_key)
                    else:
                        raise RuntimeError(f"Failed to remove {key} from cache")
        return ret

    def cache_get(self, key=None, keys=None, raise_missing=False) -> dict:
        """
        Retrieve values from the cache based on a specific key or a pattern of keys.

        Args:
            key (str, optional): A specific key to retrieve from the cache.
            keys (str, optional): A glob pattern to match multiple keys in the cache.
            raise_missing (bool, optional): If True, raises a KeyError if the specific
                key is not found in the cache. Defaults to False.

        Returns:
            dict: A dictionary containing the results of the cache retrieval. The keys are
                the cache keys and the values are the corresponding cache values.

        Raises:
            KeyError: If raise_missing is True and the specific key is not found in the cache.
        """
        ret = Result(task=f"{self.name}:cache_clear", result={})
        # get specific key from cache
        if key:
            if key in self.cache:
                ret.result[key] = self.cache[key]
            elif raise_missing:
                raise KeyError(f"Key {key} not in cache.")
        # get all keys matching glob pattern
        if keys:
            for cache_key in self.cache:
                if fnmatchcase(cache_key, keys):
                    ret.result[cache_key] = self.cache[cache_key]
        return ret

    def graphql(
        self,
        instance: str = None,
        dry_run: bool = False,
        obj: dict = None,
        filters: dict = None,
        fields: list = None,
        queries: dict = None,
        query_string: str = None,
    ) -> Union[dict, list]:
        """
        Function to query Netbox v3 or Netbox v4 GraphQL API.

        Args:
            instance: Netbox instance name
            dry_run: only return query content, do not run it
            obj: Object to query
            filters: Filters to apply to the query
            fields: Fields to retrieve in the query
            queries: Dictionary of queries to execute
            query_string: Raw query string to execute

        Returns:
            dict: GraphQL request data returned by Netbox

        Raises:
            RuntimeError: If required arguments are not provided
            Exception: If GraphQL query fails
        """
        nb_params = self._get_instance_params(instance)
        ret = Result(task=f"{self.name}:graphql")

        # form graphql query(ies) payload
        if queries:
            queries_list = []
            for alias, query_data in queries.items():
                query_data["alias"] = alias
                if self.nb_version[0] == 4:
                    queries_list.append(_form_query_v4(**query_data))
                elif self.nb_version[0] == 3:
                    queries_list.append(_form_query_v3(**query_data))
            queries_strings = "    ".join(queries_list)
            query = f"query {{{queries_strings}}}"
        elif obj and filters and fields:
            if self.nb_version[0] == 4:
                query = _form_query_v4(obj, filters, fields)
            elif self.nb_version[0] == 3:
                query = _form_query_v3(obj, filters, fields)
            query = f"query {{{query}}}"
        elif query_string:
            query = query_string
        else:
            raise RuntimeError(
                f"{self.name} - graphql method expects quieries argument or obj, filters, "
                f"fields arguments or query_string argument provided"
            )
        payload = json.dumps({"query": query})

        # form and return dry run response
        if dry_run:
            ret.result = {
                "url": f"{nb_params['url']}/graphql/",
                "data": payload,
                "verify": nb_params.get("ssl_verify", True),
                "headers": {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Token ...{nb_params['token'][-6:]}",
                },
            }
            return ret

        # send request to Netbox GraphQL API
        log.debug(
            f"{self.name} - sending GraphQL query '{payload}' to URL '{nb_params['url']}/graphql/'"
        )
        req = requests.post(
            url=f"{nb_params['url']}/graphql/",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Token {nb_params['token']}",
            },
            data=payload,
            verify=nb_params.get("ssl_verify", True),
            timeout=(self.netbox_connect_timeout, self.netbox_read_timeout),
        )
        try:
            req.raise_for_status()
        except Exception as e:
            raise Exception(
                f"{self.name} -  Netbox GraphQL query failed, query '{query}', "
                f"URL '{req.url}', status-code '{req.status_code}', reason '{req.reason}', "
                f"response content '{req.text}'"
            )

        # return results
        reply = req.json()
        if reply.get("errors"):
            msg = f"{self.name} - GrapQL query error '{reply['errors']}', query '{payload}'"
            log.error(msg)
            ret.errors.append(msg)
            if reply.get("data"):
                ret.result = reply["data"]  # at least return some data
        elif queries or query_string:
            ret.result = reply["data"]
        else:
            ret.result = reply["data"][obj]

        return ret

    def rest(
        self, instance: str = None, method: str = "get", api: str = "", **kwargs
    ) -> Union[dict, list]:
        """
        Sends a request to the Netbox REST API.

        Args:
            instance (str, optional): The instance name to get parameters for.
            method (str, optional): The HTTP method to use for the request (e.g., 'get', 'post'). Defaults to "get".
            api (str, optional): The API endpoint to send the request to. Defaults to "".
            **kwargs: Additional arguments to pass to the request (e.g., params, data, json).

        Returns:
            Union[dict, list]: The JSON response from the API, parsed into a dictionary or list.

        Raises:
            requests.exceptions.HTTPError: If the HTTP request returned an unsuccessful status code.
        """
        params = self._get_instance_params(instance)

        # send request to Netbox REST API
        response = getattr(requests, method)(
            url=f"{params['url']}/api/{api}/",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Token {params['token']}",
            },
            verify=params.get("ssl_verify", True),
            **kwargs,
        )

        response.raise_for_status()

        return response.json()

    def get_devices(
        self,
        filters: list = None,
        instance: str = None,
        dry_run: bool = False,
        devices: list = None,
        cache: Union[bool, str] = None,
    ) -> dict:
        """
        Retrieves device data from Netbox using the GraphQL API.

        Args:
            filters (list, optional): A list of filter dictionaries to filter devices.
            instance (str, optional): The Netbox instance name.
            dry_run (bool, optional): If True, only returns the query content without executing it. Defaults to False.
            devices (list, optional): A list of device names to query data for.
            cache (Union[bool, str], optional): Cache usage options:

                - True: Use data stored in cache if it is up to date, refresh it otherwise.
                - False: Do not use cache and do not update cache.
                - "refresh": Ignore data in cache and replace it with data fetched from Netbox.
                - "force": Use data in cache without checking if it is up to date.

        Returns:
            dict: A dictionary keyed by device name with device data.

        Raises:
            Exception: If the GraphQL query fails or if there are errors in the query result.
        """
        ret = Result(task=f"{self.name}:get_devices", result={})
        cache = self.cache_use if cache is None else cache
        instance = instance or self.default_instance
        filters = filters or []
        devices = devices or []
        queries = {}  # devices queries
        device_fields = [
            "name",
            "last_updated",
            "custom_field_data",
            "tags {name}",
            "device_type {model}",
            "role {name}",
            "config_context",
            "tenant {name}",
            "platform {name}",
            "serial",
            "asset_tag",
            "site {name slug tags{name} }",
            "location {name}",
            "rack {name}",
            "status",
            "primary_ip4 {address}",
            "primary_ip6 {address}",
            "airflow",
            "position",
        ]

        if cache == True or cache == "force":
            # retrieve last updated data from Netbox for devices
            last_updated_query = {
                f"devices_by_filter_{index}": {
                    "obj": "device_list",
                    "filters": filter_item,
                    "fields": ["name", "last_updated"],
                }
                for index, filter_item in enumerate(filters)
            }
            if devices:
                # use cache data without checking if it is up to date for cached devices
                if cache == "force":
                    for device_name in list(devices):
                        device_cache_key = f"get_devices::{device_name}"
                        if device_cache_key in self.cache:
                            devices.remove(device_name)
                            ret.result[device_name] = self.cache[device_cache_key]
                # query netbox last updated data for devices
                if self.nb_version[0] == 4:
                    dlist = '["{dl}"]'.format(dl='", "'.join(devices))
                    filters_dict = {"name": f"{{in_list: {dlist}}}"}
                elif self.nb_version[0] == 3:
                    filters_dict = {"name": devices}
                last_updated_query["devices_by_devices_list"] = {
                    "obj": "device_list",
                    "filters": filters_dict,
                    "fields": ["name", "last_updated"],
                }
            last_updated = self.graphql(
                queries=last_updated_query, instance=instance, dry_run=dry_run
            )
            last_updated.raise_for_status(f"{self.name} - get devices query failed")

            # return dry run result
            if dry_run:
                ret.result["get_devices_dry_run"] = last_updated.result
                return ret

            # try to retrieve device data from cache
            self.cache.expire()  # remove expired items from cache
            for devices_list in last_updated.result.values():
                for device in devices_list:
                    device_cache_key = f"get_devices::{device['name']}"
                    # check if cache is up to date and use it if so
                    if device_cache_key in self.cache and (
                        self.cache[device_cache_key]["last_updated"]
                        == device["last_updated"]
                        or cache == "force"
                    ):
                        ret.result[device["name"]] = self.cache[device_cache_key]
                        # remove device from list of devices to retrieve
                        if device["name"] in devices:
                            devices.remove(device["name"])
                    # cache old or no cache, fetch device data
                    elif device["name"] not in devices:
                        devices.append(device["name"])
        # ignore cache data, fetch data from netbox
        elif cache == False or cache == "refresh":
            queries = {
                f"devices_by_filter_{index}": {
                    "obj": "device_list",
                    "filters": filter_item,
                    "fields": device_fields,
                }
                for index, filter_item in enumerate(filters)
            }

        # fetch devices data from Netbox
        if devices or queries:
            if devices:
                if self.nb_version[0] == 4:
                    dlist = '["{dl}"]'.format(dl='", "'.join(devices))
                    filters_dict = {"name": f"{{in_list: {dlist}}}"}
                elif self.nb_version[0] == 3:
                    filters_dict = {"name": devices}
                queries["devices_by_devices_list"] = {
                    "obj": "device_list",
                    "filters": filters_dict,
                    "fields": device_fields,
                }

            # send queries
            query_result = self.graphql(
                queries=queries, instance=instance, dry_run=dry_run
            )

            # check for errors
            if query_result.errors:
                msg = f"{self.name} - get devices query failed with errors:\n{query_result.errors}"
                raise Exception(msg)

            # return dry run result
            if dry_run:
                ret.result["get_devices_dry_run"] = query_result.result
                return ret

            # process devices data
            devices_data = query_result.result
            for devices_list in devices_data.values():
                for device in devices_list:
                    if device["name"] not in ret.result:
                        device_name = device.pop("name")
                        # cache device data
                        if cache != False:
                            cache_key = f"get_devices::{device_name}"
                            self.cache.set(cache_key, device, expire=self.cache_ttl)
                        # add device data to return result
                        ret.result[device_name] = device

        return ret

    def get_interfaces(
        self,
        instance: str = None,
        devices: list = None,
        ip_addresses: bool = False,
        inventory_items: bool = False,
        dry_run: bool = False,
    ) -> dict:
        """
        Retrieve device interfaces from Netbox using GraphQL API.

        Args:
            instance (str, optional): Netbox instance name.
            devices (list, optional): List of devices to retrieve interfaces for.
            ip_addresses (bool, optional): If True, retrieves interface IPs. Defaults to False.
            inventory_items (bool, optional): If True, retrieves interface inventory items. Defaults to False.
            dry_run (bool, optional): If True, only return query content, do not run it. Defaults to False.

        Returns:
            dict: Dictionary keyed by device name with interface details.

        Raises:
            Exception: If no interfaces data is returned for the specified devices.
        """
        # form final result object
        ret = Result(
            task=f"{self.name}:get_interfaces", result={d: {} for d in devices}
        )
        intf_fields = [
            "name",
            "enabled",
            "description",
            "mtu",
            "parent {name}",
            "mac_address",
            "mode",
            "untagged_vlan {vid name}",
            "vrf {name}",
            "tagged_vlans {vid name}",
            "tags {name}",
            "custom_fields",
            "last_updated",
            "bridge {name}",
            "child_interfaces {name}",
            "bridge_interfaces {name}",
            "member_interfaces {name}",
            "wwn",
            "duplex",
            "speed",
            "id",
            "device {name}",
        ]

        # add IP addresses to interfaces fields
        if ip_addresses:
            intf_fields.append(
                "ip_addresses {address status role dns_name description custom_fields last_updated tenant {name} tags {name}}"
            )

        # form interfaces query dictionary
        queries = {
            "interfaces": {
                "obj": "interface_list",
                "filters": {"device": devices},
                "fields": intf_fields,
            }
        }

        # add query to retrieve inventory items
        if inventory_items:
            inv_filters = {"device": devices, "component_type": "dcim.interface"}
            inv_fields = [
                "name",
                "component {... on InterfaceType {id}}",
                "role {name}",
                "manufacturer {name}",
                "custom_fields",
                "label",
                "description",
                "tags {name}",
                "asset_tag",
                "serial",
                "part_id",
            ]
            queries["inventor_items"] = {
                "obj": "inventory_item_list",
                "filters": inv_filters,
                "fields": inv_fields,
            }

        query_result = self.graphql(instance=instance, queries=queries, dry_run=dry_run)

        # return dry run result
        if dry_run:
            return query_result

        interfaces_data = query_result.result

        # exit if no Interfaces returned
        if not interfaces_data.get("interfaces"):
            raise Exception(
                f"{self.name} - no interfaces data in '{interfaces_data}' returned by '{instance}' "
                f"for devices {', '.join(devices)}"
            )

        # process query results
        interfaces = interfaces_data.pop("interfaces")

        # process inventory items
        if inventory_items:
            inventory_items_list = interfaces_data.pop("inventor_items")
            # transform inventory items list to a dictionary keyed by intf_id
            inventory_items_dict = {}
            while inventory_items_list:
                inv_item = inventory_items_list.pop()
                # skip inventory items that does not assigned to components
                if inv_item.get("component") is None:
                    continue
                intf_id = str(inv_item.pop("component").pop("id"))
                inventory_items_dict.setdefault(intf_id, [])
                inventory_items_dict[intf_id].append(inv_item)
            # iterate over interfaces and add inventory items
            for intf in interfaces:
                intf["inventory_items"] = inventory_items_dict.pop(intf["id"], [])

        # transform interfaces list to dictionary keyed by device and interfaces names
        while interfaces:
            intf = interfaces.pop()
            _ = intf.pop("id")
            device_name = intf.pop("device").pop("name")
            intf_name = intf.pop("name")
            if device_name in ret.result:  # Netbox issue #16299
                ret.result[device_name][intf_name] = intf

        return ret

    def get_connections(
        self,
        devices: list,
        instance: str = None,
        dry_run: bool = False,
        cables: bool = False,
    ) -> dict:
        """
        Retrieve interface connection details for specified devices from Netbox.

        Args:
            devices (list): List of device names to retrieve connections for.
            instance (str, optional): Instance name for the GraphQL query.
            dry_run (bool, optional): If True, perform a dry run without making actual changes.
            cables (bool, optional): if True includes interfaces' directly attached cables details

        Returns:
            dict: A dictionary containing connection details for each device.

        Raises:
            Exception: If there is an error in the GraphQL query or data retrieval process.
        """
        # form final result dictionary
        ret = Result(
            task=f"{self.name}:get_connections", result={d: {} for d in devices}
        )

        # form lists of fields to request from netbox
        cable_fields = """
            cable {
                type
                status
                tenant {name}
                label
                tags {name}
                length
                length_unit
                custom_fields
            }
        """
        if self.nb_version[0] == 4:
            interfaces_fields = [
                "name",
                "device {name}",
                """connected_endpoints {
                __typename 
                ... on InterfaceType {name device {name}}
                ... on ProviderNetworkType {name}
                }""",
            ]
        elif self.nb_version[0] == 3:
            interfaces_fields = [
                "name",
                "device {name}",
                """connected_endpoints {
                __typename 
                ... on InterfaceType {name device {name}}
                }""",
            ]
        interfaces_fields.append(
            """
            link_peers {
                __typename
                ... on InterfaceType {name device {name}}
                ... on FrontPortType {name device {name}}
                ... on RearPortType {name device {name}}
            }
        """
        )
        console_ports_fields = [
            "name",
            "device {name}",
            """connected_endpoints {
              __typename 
              ... on ConsoleServerPortType {name device {name}}
            }""",
            """link_peers {
              __typename
              ... on ConsoleServerPortType {name device {name}}
              ... on FrontPortType {name device {name}}
              ... on RearPortType {name device {name}}
            }""",
        ]
        console_server_ports_fields = [
            "name",
            "device {name}",
            """connected_endpoints {
              __typename 
              ... on ConsolePortType {name device {name}}
            }""",
            """link_peers {
              __typename
              ... on ConsolePortType {name device {name}}
              ... on FrontPortType {name device {name}}
              ... on RearPortType {name device {name}}
            }""",
        ]

        # check if need to include cables info
        if cables is True:
            interfaces_fields.append(cable_fields)
            console_ports_fields.append(cable_fields)
            console_server_ports_fields.append(cable_fields)

        # form query dictionary with aliases to get data from Netbox
        queries = {
            "interface": {
                "obj": "interface_list",
                "filters": {"device": devices},
                "fields": interfaces_fields,
            },
            "consoleport": {
                "obj": "console_port_list",
                "filters": {"device": devices},
                "fields": console_ports_fields,
            },
            "consoleserverport": {
                "obj": "console_server_port_list",
                "filters": {"device": devices},
                "fields": console_server_ports_fields,
            },
        }

        # retrieve full list of devices interface with all cables
        query_result = self.graphql(queries=queries, instance=instance, dry_run=dry_run)

        # return dry run result
        if dry_run:
            return query_result

        all_ports = query_result.result

        # extract interfaces
        for port_type, ports in all_ports.items():
            for port in ports:
                endpoints = port["connected_endpoints"]
                # skip ports that have no remote device connected
                if not endpoints or not all(i for i in endpoints):
                    continue

                # extract required parameters
                cable = port.get("cable", {})
                device_name = port["device"]["name"]
                port_name = port["name"]
                link_peers = port["link_peers"]
                remote_termination_type = endpoints[0]["__typename"].lower()
                remote_termination_type = remote_termination_type.replace("type", "")

                # form initial connection dictionary
                connection = {
                    "breakout": len(endpoints) > 1,
                    "remote_termination_type": remote_termination_type,
                    "termination_type": port_type,
                }

                # add remote connection details
                if remote_termination_type == "providernetwork":
                    connection["remote_device"] = None
                    connection["remote_interface"] = None
                    connection["provider"] = endpoints[0]["name"]
                else:
                    remote_interface = endpoints[0]["name"]
                    if len(endpoints) > 1:
                        remote_interface = [i["name"] for i in endpoints]
                    connection["remote_interface"] = remote_interface
                    connection["remote_device"] = endpoints[0]["device"]["name"]

                # add cable and its peer details
                if cables:
                    peer_termination_type = link_peers[0]["__typename"].lower()
                    peer_termination_type = peer_termination_type.replace("type", "")
                    cable["peer_termination_type"] = peer_termination_type
                    cable["peer_device"] = link_peers[0].get("device", {}).get("name")
                    cable["peer_interface"] = link_peers[0].get("name")
                    if len(link_peers) > 1:  # handle breakout cable
                        cable["peer_interface"] = [i["name"] for i in link_peers]
                    connection["cable"] = cable

                ret.result[device_name][port_name] = connection

        return ret

    def _map_circuit(
        self, circuit: dict, ret: Result, instance: str, devices: list, cache: bool
    ) -> bool:
        """
        ThreadPoolExecutor target function to retrieve circuit details from Netbox

        Args:
            circuit (dict): The circuit data to be mapped.
            ret (Result): The result object to store the mapped data.
            instance (str): The instance of the Netbox API to use.
            devices (list): List of devices to check against the circuit endpoints.
            cache (bool): Flag to determine if the data should be cached.

        Returns:
            bool: True if the mapping is successful, False otherwise.
        """
        cid = circuit.pop("cid")
        ckt_cache_data = {}  # ckt data dictionary to save in cache
        circuit["tags"] = [i["name"] for i in circuit["tags"]]
        circuit["type"] = circuit["type"]["name"]
        circuit["provider"] = circuit["provider"]["name"]
        circuit["tenant"] = circuit["tenant"]["name"] if circuit["tenant"] else None
        circuit["provider_account"] = (
            circuit["provider_account"]["name"] if circuit["provider_account"] else None
        )
        termination_a = circuit["termination_a"]
        termination_z = circuit["termination_z"]
        termination_a = termination_a["id"] if termination_a else None
        termination_z = termination_z["id"] if termination_z else None

        log.info(f"{self.name}:get_circuits - {cid} tracing circuit terminations path")

        # retrieve A or Z termination path using Netbox REST API
        if termination_a is not None:
            circuit_path = self.rest(
                instance=instance,
                method="get",
                api=f"/circuits/circuit-terminations/{termination_a}/paths/",
            )
        elif termination_z is not None:
            circuit_path = self.rest(
                instance=instance,
                method="get",
                api=f"/circuits/circuit-terminations/{termination_z}/paths/",
            )
        else:
            return True

        # check if circuit ends connect to device or provider network
        if (
            not circuit_path
            or "name" not in circuit_path[0]["path"][0][0]
            or "name" not in circuit_path[0]["path"][-1][-1]
        ):
            return True

        # form A and Z connection endpoints
        end_a = {
            "device": circuit_path[0]["path"][0][0]
            .get("device", {})
            .get("name", False),
            "provider_network": "provider-network"
            in circuit_path[0]["path"][0][0]["url"],
            "name": circuit_path[0]["path"][0][0]["name"],
        }
        end_z = {
            "device": circuit_path[0]["path"][-1][-1]
            .get("device", {})
            .get("name", False),
            "provider_network": "provider-network"
            in circuit_path[0]["path"][-1][-1]["url"],
            "name": circuit_path[0]["path"][-1][-1]["name"],
        }
        circuit["is_active"] = circuit_path[0]["is_active"]

        # map path ends to devices
        if end_a["device"]:
            device_data = copy.deepcopy(circuit)
            device_data["interface"] = end_a["name"]
            if end_z["device"]:
                device_data["remote_device"] = end_z["device"]
                device_data["remote_interface"] = end_z["name"]
            elif end_z["provider_network"]:
                device_data["provider_network"] = end_z["name"]
            # save device data in cache
            ckt_cache_data[end_a["device"]] = device_data
            # include device data in result
            if end_a["device"] in devices:
                ret.result[end_a["device"]][cid] = device_data
        if end_z["device"]:
            device_data = copy.deepcopy(circuit)
            device_data["interface"] = end_z["name"]
            if end_a["device"]:
                device_data["remote_device"] = end_a["device"]
                device_data["remote_interface"] = end_a["name"]
            elif end_a["provider_network"]:
                device_data["provider_network"] = end_a["name"]
            # save device data in cache
            ckt_cache_data[end_z["device"]] = device_data
            # include device data in result
            if end_z["device"] in devices:
                ret.result[end_z["device"]][cid] = device_data

        # save data to cache
        if cache != False:
            ckt_cache_key = f"get_circuits::{cid}"
            if ckt_cache_data:
                self.cache.set(ckt_cache_key, ckt_cache_data, expire=self.cache_ttl)
                log.info(
                    f"{self.name}:get_circuits - {cid} cached circuit data for future use"
                )

        log.info(
            f"{self.name}:get_circuits - {cid} circuit data mapped to devices using data from Netbox"
        )
        return True

    def get_circuits(
        self,
        devices: list,
        cid: list = None,
        instance: str = None,
        dry_run: bool = False,
        cache: Union[bool, str] = True,
    ) -> dict:
        """

        Retrieve circuit information for specified devices from Netbox.

        Args:
            devices (list): List of device names to retrieve circuits for.
            cid (list, optional): List of circuit IDs to filter by.
            instance (str, optional): Netbox instance to query.
            dry_run (bool, optional): If True, perform a dry run without making changes. Defaults to False.
            cache (Union[bool, str], optional): Cache usage options:

                - True: Use data stored in cache if it is up to date, refresh it otherwise.
                - False: Do not use cache and do not update cache.
                - "refresh": Ignore data in cache and replace it with data fetched from Netbox.
                - "force": Use data in cache without checking if it is up to date.

        Returns:
            dict: dictionary keyed by device names with circuits data.

        Task to retrieve device's circuits data from Netbox.
        """
        log.info(
            f"{self.name}:get_circuits - {instance or self.default_instance} Netbox, "
            f"devices {', '.join(devices)}, cid {cid}"
        )

        # form final result object
        ret = Result(task=f"{self.name}:get_circuits", result={d: {} for d in devices})
        cache = self.cache_use if cache is None else cache
        cid = cid or []
        circuit_fields = [
            "cid",
            "tags {name}",
            "provider {name}",
            "commit_rate",
            "description",
            "status",
            "type {name}",
            "provider_account {name}",
            "tenant {name}",
            "termination_a {id last_updated}",
            "termination_z {id last_updated}",
            "custom_fields",
            "comments",
            "last_updated",
        ]

        # form initial circuits filters based on devices' sites and cid list
        circuits_filters_dict = {}
        device_data = self.get_devices(
            devices=copy.deepcopy(devices), instance=instance, cache=cache
        )
        sites = list(set([i["site"]["slug"] for i in device_data.result.values()]))
        if self.nb_version[0] == 4:
            circuits_filters_dict = {"site": sites}
            if cid:
                cid_list = '["{cl}"]'.format(cl='", "'.join(cid))
                circuits_filters_dict["cid"] = f"{{in_list: {cid_list}}}"
        elif self.nb_version[0] == 3:
            circuits_filters_dict = {"site": sites}
            if cid:
                cid_list = '["{cl}"]'.format(cl='", "'.join(cid))
                circuits_filters_dict["cid"] = cid_list

        log.info(
            f"{self.name}:get_circuits - constructed circuits filters: {circuits_filters_dict}"
        )

        if cache == True or cache == "force":
            log.info(f"{self.name}:get_circuits - retrieving circuits data from cache")
            cid_list = []  #  new cid list for follow up query
            # retrieve last updated data from Netbox for circuits and their terminations
            last_updated = self.graphql(
                obj="circuit_list",
                filters=circuits_filters_dict,
                fields=[
                    "cid",
                    "last_updated",
                    "termination_a {id last_updated}",
                    "termination_z {id last_updated}",
                ],
                dry_run=dry_run,
                instance=instance,
            )
            last_updated.raise_for_status(f"{self.name} - get circuits query failed")

            # return dry run result
            if dry_run:
                ret.result["get_circuits_dry_run"] = last_updated.result
                return ret

            # retrieve circuits data from cache
            self.cache.expire()  # remove expired items from cache
            for device in devices:
                for circuit in last_updated.result:
                    circuit_cache_key = f"get_circuits::{circuit['cid']}"
                    log.info(
                        f"{self.name}:get_circuits - searching cache for key {circuit_cache_key}"
                    )
                    # check if cache is up to date and use it if so
                    if circuit_cache_key in self.cache:
                        cache_ckt = self.cache[circuit_cache_key]
                        # check if device uses this circuit
                        if device not in cache_ckt:
                            continue
                        # use cache forcefully
                        if cache == "force":
                            ret.result[device][circuit["cid"]] = cache_ckt[device]
                        # check circuit cache is up to date
                        if cache_ckt[device]["last_updated"] != circuit["last_updated"]:
                            continue
                        if (
                            cache_ckt[device]["termination_a"]
                            and circuit["termination_a"]
                            and cache_ckt[device]["termination_a"]["last_updated"]
                            != circuit["termination_a"]["last_updated"]
                        ):
                            continue
                        if (
                            cache_ckt[device]["termination_z"]
                            and circuit["termination_z"]
                            and cache_ckt[device]["termination_z"]["last_updated"]
                            != circuit["termination_z"]["last_updated"]
                        ):
                            continue
                        ret.result[device][circuit["cid"]] = cache_ckt[device]
                        log.info(
                            f"{self.name}:get_circuits - {circuit['cid']} retrieved data from cache"
                        )
                    elif circuit["cid"] not in cid_list:
                        cid_list.append(circuit["cid"])
                        log.info(
                            f"{self.name}:get_circuits - {circuit['cid']} no cache data found, fetching from Netbox"
                        )
            # form new filters dictionary to fetch remaining circuits data
            circuits_filters_dict = {}
            if cid_list:
                cid_list = '["{cl}"]'.format(cl='", "'.join(cid_list))
                if self.nb_version[0] == 4:
                    circuits_filters_dict["cid"] = f"{{in_list: {cid_list}}}"
                elif self.nb_version[0] == 3:
                    circuits_filters_dict["cid"] = cid_list
        # ignore cache data, fetch circuits from netbox
        elif cache == False or cache == "refresh":
            pass

        if circuits_filters_dict:
            query_result = self.graphql(
                obj="circuit_list",
                filters=circuits_filters_dict,
                fields=circuit_fields,
                dry_run=dry_run,
                instance=instance,
            )
            query_result.raise_for_status(f"{self.name} - get circuits query failed")

            # return dry run result
            if dry_run is True:
                return query_result

            all_circuits = query_result.result

            # iterate over circuits and map them to devices
            log.info(
                f"{self.name}:get_circuits - retrieved data for {len(all_circuits)} "
                f"circuits from netbox, mapping circuits to devices"
            )
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                results = [
                    executor.submit(
                        self._map_circuit, circuit, ret, instance, devices, cache
                    )
                    for circuit in all_circuits
                ]
                for _ in concurrent.futures.as_completed(results):
                    continue

        return ret

    def get_nornir_inventory(
        self,
        filters: list = None,
        devices: list = None,
        instance: str = None,
        interfaces: Union[dict, bool] = False,
        connections: Union[dict, bool] = False,
        circuits: Union[dict, bool] = False,
        nbdata: bool = True,
        primary_ip: str = "ip4",
    ) -> dict:
        """
        Retrieve and construct Nornir inventory from NetBox data.

        Args:
            filters (list, optional): List of filters to apply when retrieving devices from NetBox.
            devices (list, optional): List of specific devices to retrieve from NetBox.
            instance (str, optional): NetBox instance to use.
            interfaces (Union[dict, bool], optional): If True, include interfaces data
                    in the inventory. If a dict, use it as arguments for the get_interfaces method.
            connections (Union[dict, bool], optional): If True, include connections data
                    in the inventory. If a dict, use it as arguments for the get_connections method.
            circuits (Union[dict, bool], optional): If True, include circuits data in the
                    inventory. If a dict, use it as arguments for the get_circuits method.
            nbdata (bool, optional): If True, include a copy of NetBox device's data in the host's data.
            primary_ip (str, optional): Specify whether to use 'ip4' or 'ip6' for the primary
                    IP address. Defaults to 'ip4'.

        Returns:
            dict: Nornir inventory dictionary containing hosts and their respective data.
        """
        hosts = {}
        inventory = {"hosts": hosts}
        ret = Result(task=f"{self.name}:get_nornir_inventory", result=inventory)

        # check Netbox status
        netbox_status = self.get_netbox_status(instance=instance)
        if netbox_status.result[instance or self.default_instance]["status"] is False:
            return ret

        # retrieve devices data
        nb_devices = self.get_devices(
            filters=filters, devices=devices, instance=instance
        )

        # form Nornir hosts inventory
        for device_name, device in nb_devices.result.items():
            host = device["config_context"].pop("nornir", {})
            host.setdefault("data", {})
            name = host.pop("name", device_name)
            hosts[name] = host
            # add platform if not provided in device config context
            if not host.get("platform"):
                if device["platform"]:
                    host["platform"] = device["platform"]["name"]
                else:
                    log.warning(f"{self.name} - no platform found for '{name}' device")
            # add hostname if not provided in config context
            if not host.get("hostname"):
                if device["primary_ip4"] and primary_ip in ["ip4", "ipv4"]:
                    host["hostname"] = device["primary_ip4"]["address"].split("/")[0]
                elif device["primary_ip6"] and primary_ip in ["ip6", "ipv6"]:
                    host["hostname"] = device["primary_ip6"]["address"].split("/")[0]
                else:
                    host["hostname"] = name
            # add netbox data to host's data
            if nbdata is True:
                host["data"].update(device)

        # return if no hosts found for provided parameters
        if not hosts:
            log.warning(f"{self.name} - no viable hosts returned by Netbox")
            return ret

        # add interfaces data
        if interfaces:
            # decide on get_interfaces arguments
            kwargs = interfaces if isinstance(interfaces, dict) else {}
            # add 'interfaces' key to all hosts' data
            for host in hosts.values():
                host["data"].setdefault("interfaces", {})
            # query interfaces data from netbox
            nb_interfaces = self.get_interfaces(
                devices=list(hosts), instance=instance, **kwargs
            )
            # save interfaces data to hosts' inventory
            while nb_interfaces.result:
                device, device_interfaces = nb_interfaces.result.popitem()
                hosts[device]["data"]["interfaces"] = device_interfaces

        # add connections data
        if connections:
            # decide on get_interfaces arguments
            kwargs = connections if isinstance(connections, dict) else {}
            # add 'connections' key to all hosts' data
            for host in hosts.values():
                host["data"].setdefault("connections", {})
            # query connections data from netbox
            nb_connections = self.get_connections(
                devices=list(hosts), instance=instance, **kwargs
            )
            # save connections data to hosts' inventory
            while nb_connections.result:
                device, device_connections = nb_connections.result.popitem()
                hosts[device]["data"]["connections"] = device_connections

        # add circuits data
        if circuits:
            # decide on get_interfaces arguments
            kwargs = circuits if isinstance(circuits, dict) else {}
            # add 'circuits' key to all hosts' data
            for host in hosts.values():
                host["data"].setdefault("circuits", {})
            # query circuits data from netbox
            nb_circuits = self.get_circuits(
                devices=list(hosts), instance=instance, **kwargs
            )
            # save circuits data to hosts' inventory
            while nb_circuits.result:
                device, device_circuits = nb_circuits.result.popitem()
                hosts[device]["data"]["circuits"] = device_circuits

        return ret

    def update_device_facts(
        self,
        instance: str = None,
        dry_run: bool = False,
        datasource: str = "nornir",
        timeout: int = 60,
        devices: list = None,
        batch_size: int = 10,
        **kwargs,
    ) -> dict:
        """
        Updates the device facts in NetBox:

        - serial number

        Args:
            instance (str, optional): The NetBox instance to use.
            dry_run (bool, optional): If True, no changes will be made to NetBox.
            datasource (str, optional): The data source to use. Supported datasources:

                - **nornir** - uses Nornir Service parse task to retrieve devices' data
                    using NAPALM get_facts getter

            timeout (int, optional): The timeout for the job execution. Defaults to 60.
            devices (list, optional): The list of devices to update.
            batch_size (int, optional): The number of devices to process in each batch.
            **kwargs: Additional keyword arguments to pass to the job.

        Returns:
            dict: A dictionary containing the results of the update operation.

        Raises:
            Exception: If a device does not exist in NetBox.
            UnsupportedServiceError: If the specified datasource is not supported.
        """
        result = {}
        devices = devices or []
        instance = instance or self.default_instance
        ret = Result(task=f"{self.name}:update_device_facts", result=result)
        nb = self._get_pynetbox(instance)
        kwargs["add_details"] = True

        if datasource == "nornir":
            for i in range(0, len(devices), batch_size):
                kwargs["FL"] = devices[i : i + batch_size]
                kwargs["getters"] = "get_facts"
                self.event(
                    f"retrieving facts data for devices {', '.join(kwargs['FL'])}",
                    resource=instance,
                )
                data = self.client.run_job(
                    "nornir",
                    "parse",
                    kwargs=kwargs,
                    workers="all",
                    timeout=timeout,
                )
                for worker, results in data.items():
                    if results["failed"]:
                        log.error(
                            f"{worker} get_facts failed, errors: {'; '.join(results['errors'])}"
                        )
                        continue
                    for host, host_data in results["result"].items():
                        if host_data["napalm_get"]["failed"]:
                            log.error(
                                f"{host} facts update failed: '{host_data['napalm_get']['exception']}'"
                            )
                            self.event(
                                f"{host} facts update failed",
                                resource=instance,
                                status="failed",
                                severity="WARNING",
                            )
                            continue
                        nb_device = nb.dcim.devices.get(name=host)
                        if not nb_device:
                            raise Exception(f"'{host}' does not exist in Netbox")
                        facts = host_data["napalm_get"]["result"]["get_facts"]
                        # update serial number
                        nb_device.serial = facts["serial_number"]
                        if not dry_run:
                            nb_device.save()
                        result[host] = {
                            "update_device_facts_dry_run"
                            if dry_run
                            else "update_device_facts": {
                                "serial": facts["serial_number"],
                            }
                        }
                        self.event(f"{host} facts updated", resource=instance)
        else:
            raise UnsupportedServiceError(
                f"'{datasource}' datasource service not supported"
            )

        return ret

    def update_device_interfaces(
        self,
        instance: str = None,
        dry_run: bool = False,
        datasource: str = "nornir",
        timeout: int = 60,
        devices: list = None,
        create: bool = True,
        batch_size: int = 10,
        **kwargs,
    ) -> dict:
        """
        Update or create device interfaces in Netbox. Interface parameters updated:

        - interface name
        - interface description
        - mtu
        - mac address
        - admin status
        - speed

        Args:
            instance (str, optional): The instance name to use.
            dry_run (bool, optional): If True, no changes will be made to Netbox.
            datasource (str, optional): The data source to use. Supported datasources:

                - **nornir** - uses Nornir Service parse task to retrieve devices' data
                    using NAPALM get_interfaces getter

            timeout (int, optional): The timeout for the job.
            devices (list, optional): List of devices to update.
            create (bool, optional): If True, new interfaces will be created if they do not exist.
            batch_size (int, optional): The number of devices to process in each batch.
            **kwargs: Additional keyword arguments to pass to the job.

        Returns:
            dict: A dictionary containing the results of the update operation.

        Raises:
            Exception: If a device does not exist in Netbox.
            UnsupportedServiceError: If the specified datasource is not supported.
        """
        result = {}
        instance = instance or self.default_instance
        ret = Result(task=f"{self.name}:update_device_interfaces", result=result)
        nb = self._get_pynetbox(instance)

        if datasource == "nornir":
            for i in range(0, len(devices), batch_size):
                kwargs["FL"] = devices[i : i + batch_size]
                kwargs["getters"] = "get_interfaces"
                data = self.client.run_job(
                    "nornir",
                    "parse",
                    kwargs=kwargs,
                    workers="all",
                    timeout=timeout,
                )
                for worker, results in data.items():
                    if results["failed"]:
                        log.error(
                            f"{worker} get_interfaces failed, errors: {'; '.join(results['errors'])}"
                        )
                        continue
                    for host, host_data in results["result"].items():
                        updated, created = {}, {}
                        result[host] = {
                            "update_device_interfaces_dry_run"
                            if dry_run
                            else "update_device_interfaces": updated,
                            "created_device_interfaces_dry_run"
                            if dry_run
                            else "created_device_interfaces": created,
                        }
                        interfaces = host_data["napalm_get"]["get_interfaces"]
                        nb_device = nb.dcim.devices.get(name=host)
                        if not nb_device:
                            raise Exception(f"'{host}' does not exist in Netbox")
                        nb_interfaces = nb.dcim.interfaces.filter(
                            device_id=nb_device.id
                        )
                        # update existing interfaces
                        for nb_interface in nb_interfaces:
                            if nb_interface.name not in interfaces:
                                continue
                            interface = interfaces.pop(nb_interface.name)
                            nb_interface.description = interface["description"]
                            nb_interface.mtu = interface["mtu"]
                            nb_interface.speed = interface["speed"] * 1000
                            nb_interface.mac_address = interface["mac_address"]
                            nb_interface.enabled = interface["is_enabled"]
                            if dry_run is not True:
                                nb_interface.save()
                            updated[nb_interface.name] = interface
                            self.event(
                                f"{host} updated interface {nb_interface.name}",
                                resource=instance,
                            )
                        # create new interfaces
                        if create is not True:
                            continue
                        for interface_name, interface in interfaces.items():
                            interface["type"] = "other"
                            nb_interface = nb.dcim.interfaces.create(
                                name=interface_name,
                                device={"name": nb_device.name},
                                type=interface["type"],
                            )
                            nb_interface.description = interface["description"]
                            nb_interface.mtu = interface["mtu"]
                            nb_interface.speed = interface["speed"] * 1000
                            nb_interface.mac_address = interface["mac_address"]
                            nb_interface.enabled = interface["is_enabled"]
                            if dry_run is not True:
                                nb_interface.save()
                            created[interface_name] = interface
                            self.event(
                                f"{host} created interface {nb_interface.name}",
                                resource=instance,
                            )
        else:
            raise UnsupportedServiceError(
                f"'{datasource}' datasource service not supported"
            )

        return ret

    def update_device_ip(
        self,
        instance: str = None,
        dry_run: bool = False,
        datasource: str = "nornir",
        timeout: int = 60,
        devices: list = None,
        create: bool = True,
        batch_size: int = 10,
        **kwargs,
    ) -> dict:
        """
        Update the IP addresses of devices in Netbox.

        Args:
            instance (str, optional): The instance name to use.
            dry_run (bool, optional): If True, no changes will be made.
            datasource (str, optional): The data source to use. Supported datasources:

                - **nornir** - uses Nornir Service parse task to retrieve devices' data
                    using NAPALM get_interfaces_ip getter

            timeout (int, optional): The timeout for the operation.
            devices (list, optional): The list of devices to update.
            create (bool, optional): If True, new IP addresses will be created if they do not exist.
            batch_size (int, optional): The number of devices to process in each batch.
            **kwargs: Additional keyword arguments.

        Returns:
            dict: A dictionary containing the results of the update operation.

        Raises:
            Exception: If a device does not exist in Netbox.
            UnsupportedServiceError: If the specified datasource is not supported.
        """
        result = {}
        instance = instance or self.default_instance
        ret = Result(task=f"{self.name}:update_device_ip", result=result)
        nb = self._get_pynetbox(instance)

        if datasource == "nornir":
            for i in range(0, len(devices), batch_size):
                kwargs["FL"] = devices[i : i + batch_size]
                kwargs["getters"] = "get_interfaces_ip"
                data = self.client.run_job(
                    "nornir",
                    "parse",
                    kwargs=kwargs,
                    workers="all",
                    timeout=timeout,
                )
                for worker, results in data.items():
                    if results["failed"]:
                        log.error(
                            f"{worker} get_interfaces_ip failed, errors: {'; '.join(results['errors'])}"
                        )
                        continue
                    for host, host_data in results["result"].items():
                        updated, created = {}, {}
                        result[host] = {
                            "updated_ip_dry_run" if dry_run else "updated_ip": updated,
                            "created_ip_dry_run" if dry_run else "created_ip": created,
                        }
                        interfaces = host_data["napalm_get"]["get_interfaces_ip"]
                        nb_device = nb.dcim.devices.get(name=host)
                        if not nb_device:
                            raise Exception(f"'{host}' does not exist in Netbox")
                        nb_interfaces = nb.dcim.interfaces.filter(
                            device_id=nb_device.id
                        )
                        # update interface IP addresses
                        for nb_interface in nb_interfaces:
                            if nb_interface.name not in interfaces:
                                continue
                            interface = interfaces.pop(nb_interface.name)
                            # merge v6 into v4 addresses to save code repetition
                            interface["ipv4"].update(interface.pop("ipv6", {}))
                            # update/create IP addresses
                            for ip, ip_data in interface["ipv4"].items():
                                prefix_length = ip_data["prefix_length"]
                                # get IP address info from Netbox
                                nb_ip = nb.ipam.ip_addresses.filter(
                                    address=f"{ip}/{prefix_length}"
                                )
                                if len(nb_ip) > 1:
                                    log.warning(
                                        f"{host} got multiple {ip}/{prefix_length} IP addresses from Netbox, "
                                        f"NorFab Netbox Service only supports handling of non-duplicate IPs."
                                    )
                                    continue
                                # decide what to do
                                if not nb_ip and create is False:
                                    continue
                                elif not nb_ip and create is True:
                                    if dry_run is not True:
                                        nb_ip = nb.ipam.ip_addresses.create(
                                            address=f"{ip}/{prefix_length}"
                                        )
                                        nb_ip.assigned_object_type = "dcim.interface"
                                        nb_ip.assigned_object_id = nb_interface.id
                                        nb_ip.status = "active"
                                        nb_ip.save()
                                    created[f"{ip}/{prefix_length}"] = nb_interface.name
                                    self.event(
                                        f"{host} created IP address {ip}/{prefix_length} for {nb_interface.name} interface",
                                        resource=instance,
                                    )
                                elif nb_ip:
                                    nb_ip = list(nb_ip)[0]
                                    nb_ip.assigned_object_type = "dcim.interface"
                                    nb_ip.assigned_object_id = nb_interface.id
                                    nb_ip.status = "active"
                                    if dry_run is not True:
                                        nb_ip.save()
                                    updated[nb_ip.address] = nb_interface.name
                                    self.event(
                                        f"{host} updated IP address {ip}/{prefix_length} for {nb_interface.name} interface",
                                        resource=instance,
                                    )

        else:
            raise UnsupportedServiceError(
                f"'{datasource}' datasource service not supported"
            )

        return ret

    def get_next_ip(
        self,
        subnet: str,
        description: str = None,
        device: str = None,
        interface: str = None,
        vrf: str = None,
        tags: list = None,
        dns_name: str = None,
        tenant: str = None,
        comments: str = None,
        instance: str = None,
        dry_run: bool = False,
    ) -> dict:
        """
        Allocate the next available IP address from a given subnet.

        Args:
            subnet (str): The subnet from which to allocate the IP address.
            description (str, optional): A description for the allocated IP address.
            device (str, optional): The device associated with the IP address.
            interface (str, optional): The interface associated with the IP address.
            vrf (str, optional): The VRF (Virtual Routing and Forwarding) instance.
            tags (list, optional): A list of tags to associate with the IP address.
            dns_name (str, optional): The DNS name for the IP address.
            tenant (str, optional): The tenant associated with the IP address.
            comments (str, optional): Additional comments for the IP address.
            instance (str, optional): The NetBox instance to use.
            dry_run (bool, optional): If True, do not actually allocate the IP address. Defaults to False.

        Returns:
            dict: A dictionary containing the result of the IP allocation.
        """
        nb = self._get_pynetbox(instance)
        nb_prefix = nb.ipam.prefixes.get(prefix=subnet, vrf=vrf)
        nb_ip = nb_prefix.available_ips.create()
        if description is not None:
            nb_ip.description = description
        nb_ip.save()

        return Result(result=str(nb_ip))
