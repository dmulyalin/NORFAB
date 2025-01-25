import json
import logging
import sys
import importlib.metadata
import requests
import copy
import os
import concurrent.futures

from fnmatch import fnmatchcase
from datetime import datetime, timedelta
from norfab.core.worker import NFPWorker, Result
from typing import Union
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from norfab.core.exceptions import UnsupportedServiceError
from diskcache import FanoutCache

try:
    import pynetbox

    HAS_PYNETBOX = True
except ImportError:
    HAS_PYNETBOX = False

log = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# HELPER FUNCTIONS
# ----------------------------------------------------------------------


def _form_query_v4(obj, filters, fields, alias=None):
    """
    Helper function to form graphql query

    :param obj: string, object to return data for e.g. device, interface, ip_address
    :param filters: dictionary of key-value pairs to filter by
    :param fields: list of data fields to return
    :param alias: string, alias value for requested object
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
    Helper function to form graphql query

    :param obj: string, obj to return data for e.g. device, interface, ip_address
    :param filters: dictionary of key-value pairs to filter by
    :param fields: list of data fields to return
    :param alias: string, alias value for requested obj
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
    :param broker: broker URL to connect to
    :param service: name of the service with worker belongs to
    :param worker_name: name of this worker
    :param exit_event: if set, worker need to stop/exit
    :param init_done_event: event to set when worker done initializing
    :param log_keve: logging level of this worker
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
        broker,
        worker_name,
        service: str = b"netbox",
        exit_event=None,
        init_done_event=None,
        log_level=None,
        log_queue: object = None,
    ):
        super().__init__(broker, service, worker_name, exit_event, log_level, log_queue)
        self.init_done_event = init_done_event

        # get inventory from broker
        self.inventory = self.load_inventory()
        if not self.inventory:
            log.critical(
                f"{self.name} - Broker {self.broker} returned no inventory for {self.name}, killing myself..."
            )
            self.destroy()

        assert self.inventory.get(
            "instances"
        ), f"{self.name} - inventory has no Netbox instances"

        # extract parameters from imvemtory
        self.netbox_connect_timeout = self.inventory.get("netbox_connect_timeout", 10)
        self.netbox_read_timeout = self.inventory.get("netbox_read_timeout", 300)
        self.cache_use = self.inventory.get("cache_use", True)
        self.cache_ttl = self.inventory.get("cache_ttl", 31557600)  # 1 Year

        # find default instance
        for name, params in self.inventory["instances"].items():
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
        self.cache.close()

    # ----------------------------------------------------------------------
    # Netbox Service Functions that exposed for calling
    # ----------------------------------------------------------------------

    def get_netbox_inventory(self) -> dict:
        return Result(
            task=f"{self.name}:get_netbox_inventory", result=dict(self.inventory)
        )

    def get_netbox_version(self, **kwargs) -> dict:
        libs = {
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

        return Result(task=f"{self.name}:get_netbox_version", result=libs)

    def get_netbox_status(self, instance=None) -> dict:
        ret = Result(result={}, task=f"{self.name}:get_netbox_status")
        if instance:
            ret.result[instance] = self._query_netbox_status(instance)
        else:
            for name in self.inventory["instances"].keys():
                ret.result[name] = self._query_netbox_status(name)
        return ret

    def get_compatibility(self) -> dict:
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
        compatibility = self.get_compatibility()
        if not all(i is not False for i in compatibility.result.values()):
            raise RuntimeError(
                f"{self.name} - not all Netbox instances are compatible: {compatibility.result}"
            )

    def _query_netbox_status(self, name):
        params = self.inventory["instances"][name]
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
        Helper function to get inventory params for Netbox instance.

        :param name: Netbox instance name
        """
        if name:
            ret = self.inventory["instances"][name]
        else:
            ret = self.inventory["instances"][self.default_instance]

        # check if need to disable SSL warnings
        if ret.get("ssl_verify") == False:
            requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
        else:
            requests.packages.urllib3.enable_warnings(InsecureRequestWarning)

        return ret

    def _get_pynetbox(self, instance):
        """Helper function to instantiate pynetbox api object"""
        if not HAS_PYNETBOX:
            msg = f"{self.name} - failed to import pynetbox library, is it installed?"
            log.error(msg)
            raise Exception(msg)

        params = self._get_instance_params(instance)

        if params.get("ssl_verify") == False:
            requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
            nb = pynetbox.api(url=params["url"], token=params["token"])
            nb.http_session.verify = False
        else:
            nb = pynetbox.api(url=params["url"], token=params["token"])

        return nb

    def _get_diskcache(self) -> FanoutCache:
        return FanoutCache(
            directory=self.cache_dir,
            shards=4,
            timeout=1,  # 1 second
            size_limit=1073741824,  #  GigaByte
        )

    def cache_list(self, keys="*", details=False) -> list:
        """
        List cache keys.

        :param keys: Pattern to match keys to list
        :param details: if True add key details, returns just key name otherwise
        :returns: List of cache keys names if details False, else return list of
            key dictionaries with extra information like age and expire time.
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
        Clears specified cache entries.

        :param key: Specific key to clear from the cache
        :param keys: Pattern to match multiple keys to clear from the cache
        :returns: List of cleared keys.
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
        Return data stored in specified cache entries.

        :param key: Specific key to get cached data for
        :param keys: Pattern to match multiple keys to return cached data
        :param raise_missing: if True raises KeyError for missing key
        :returns: Requested keys cached data.
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
        Function to query Netbox v4 GraphQL API

        :param instance: Netbox instance name
        :param dry_run: only return query content, do not run it
        :param obj: Object to query
        :param filters: Filters to apply to the query
        :param fields: Fields to retrieve in the query
        :param queries: Dictionary of queries to execute
        :param query_string: Raw query string to execute
        :return: GraphQL request data returned by Netbox
        :raises RuntimeError: If required arguments are not provided
        :raises Exception: If GraphQL query fails
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
        Method to query Netbox REST API.

        :param instance: Netbox instance name
        :param method: requests method name e.g. get, post, put etc.
        :param api: api url to query e.g. "extras" or "dcim/interfaces" etc.
        :param kwargs: any additional requests method's arguments
        :return: REST API Query result
        :raises Exception: If REST API query fails
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
        Function to retrieve devices data from Netbox using GraphQL API.

        :param filters: list of filters dictionaries to filter devices
        :param instance: Netbox instance name
        :param dry_run: only return query content, do not run it
        :param devices: list of device names to query data for
        :param cache: if `True` use data stored in cache if it is up to date
            refresh it otherwise, `False` do not use cache do not update cache,
            `refresh` ignore data in cache and replace it with data fetched
            from Netbox, `force` use data in cache without checking if it is up
            to date
        :return: dictionary keyed by device name with device data
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
        Function to retrieve device interfaces from Netbox using GraphQL API.

        :param instance: Netbox instance name
        :param devices: list of devices to retrieve interfaces for
        :param ip_addresses: if True, retrieves interface IPs
        :param inventory_items: if True, retrieves interface inventory items
        :param dry_run: only return query content, do not run it
        :return: dictionary keyed by device name with interface details
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
        Function to retrieve device connections data from Netbox using GraphQL API.

        :param instance: Netbox instance name
        :param devices: list of devices to retrieve interface for
        :param dry_run: only return query content, do not run it
        :param cables: if True includes interfaces' directly attached cables details
        :return: dictionary keyed by device name with connections data
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

        :param circuit: Dictionary with circuit data
        :param ret: Result object to save results into
        :param instance: Netbox instance name
        :param devices: list of devices to map circuits for
        :param cache: if `True` or 'refresh' update cache, `False` do not update cache
        """
        cid = circuit.pop("cid")
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
        if end_a["device"] and end_a["device"] in devices:
            ret.result[end_a["device"]][cid] = copy.deepcopy(circuit)
            ret.result[end_a["device"]][cid]["interface"] = end_a["name"]
            if end_z["device"]:
                ret.result[end_a["device"]][cid]["remote_device"] = end_z["device"]
                ret.result[end_a["device"]][cid]["remote_interface"] = end_z["name"]
            elif end_z["provider_network"]:
                ret.result[end_a["device"]][cid]["provider_network"] = end_z["name"]
            # save data to cache
            if cache != False:
                cache_key = f"get_circuits::{end_a['device']}::{cid}"
                self.cache.set(
                    cache_key, ret.result[end_a["device"]][cid], expire=self.cache_ttl
                )
        if end_z["device"] and end_z["device"] in devices:
            ret.result[end_z["device"]][cid] = copy.deepcopy(circuit)
            ret.result[end_z["device"]][cid]["interface"] = end_z["name"]
            if end_a["device"]:
                ret.result[end_z["device"]][cid]["remote_device"] = end_a["device"]
                ret.result[end_z["device"]][cid]["remote_interface"] = end_a["name"]
            elif end_a["provider_network"]:
                ret.result[end_z["device"]][cid]["provider_network"] = end_a["name"]
            # save data to cache
            if cache != False:
                cache_key = f"get_circuits::{end_z['device']}::{cid}"
                self.cache.set(
                    cache_key, ret.result[end_z["device"]][cid], expire=self.cache_ttl
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
        Task to retrieve device's circuits data from Netbox.

        :param devices: list of devices to retrieve interface for
        :param instance: Netbox instance name
        :param dry_run: only return query content, do not run it
        :param cid: list of circuit identifiers to retrieve data for
        :param cache: if `True` use data stored in cache if it is up to date
            refresh it otherwise, `False` do not use cache do not update cache,
            `refresh` ignore data in cache and replace it with data fetched
            from Netbox, `force` use data in cache without checking if it is up
            to date
        :return: dictionary keyed by device names with circuits data values
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
                    circuit_cache_key = f"get_circuits::{device}::{circuit['cid']}"
                    # check if cache is up to date and use it if so
                    if circuit_cache_key in self.cache:
                        cache_ckt = self.cache[circuit_cache_key]
                        # use cache forcefully
                        if cache == "force":
                            ret.result[device][circuit["cid"]] = cache_ckt
                        # check circuit cache is up to date
                        if cache_ckt["last_updated"] != circuit["last_updated"]:
                            continue
                        if (
                            cache_ckt["termination_a"]
                            and circuit["termination_a"]
                            and cache_ckt["termination_a"]["last_updated"]
                            != circuit["termination_a"]["last_updated"]
                        ):
                            continue
                        if (
                            cache_ckt["termination_z"]
                            and circuit["termination_z"]
                            and cache_ckt["termination_z"]["last_updated"]
                            != circuit["termination_z"]["last_updated"]
                        ):
                            continue
                        ret.result[device][circuit["cid"]] = cache_ckt
                    elif circuit["cid"] not in cid_list:
                        cid_list.append(circuit["cid"])
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
                f"{self.name}:get_circuits - mapping device endpoints for {len(all_circuits)} circuits"
            )
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
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
        Method to query Netbox devices data and construct Nornir inventory.

        :param filters: List of filters to apply when querying devices.
        :param devices: List of specific devices to query.
        :param instance: Netbox instance name to query.
        :param interfaces: Whether to include interfaces data. If a dict is provided,
            it will be used as arguments for the query.
        :param connections: Whether to include connections data. If a dict is provided,
            it will be used as arguments for the query.
        :param circuits: Whether to include circuits data. If a dict is provided,
            it will be used as arguments for the query.
        :param nbdata: Whether to include Netbox devices data in the host's data
        :param primary_ip: Primary IP version to use for the hostname.
        :returns: Nornir Inventory compatible dictionary
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
        **kwargs,
    ) -> dict:
        """
        Function to update device facts in Netbox using information
        provided by NAPALM get_facts getter:

        - serial number

        :param instance: Netbox instance name
        :param dry_run: return information that would be pushed to Netbox but do not push it
        :param datasource: service name to use to retrieve devices' data, default is nornir parse task
        :param timeout: seconds to wait before timeout data retrieval job
        :param kwargs: any additional arguments to send to service for device data retrieval
        :returns: dictionary keyed by device name with updated details
        """
        result = {}
        instance = instance or self.default_instance
        ret = Result(task=f"{self.name}:update_device_facts", result=result)
        nb = self._get_pynetbox(instance)
        kwargs["add_details"] = True

        if datasource == "nornir":
            if devices:
                kwargs["FL"] = devices
            data = self.client.run_job(
                "nornir",
                "parse",
                kwargs=kwargs,
                workers="all",
                timeout=timeout,
            )
            for worker, results in data.items():
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
            raise UnsupportedServiceError(f"'{datasource}' service not supported")

        return ret

    def update_device_interfaces(
        self,
        instance: str = None,
        dry_run: bool = False,
        datasource: str = "nornir",
        timeout: int = 60,
        devices: list = None,
        create: bool = True,
        **kwargs,
    ) -> dict:
        """
        Function to update device interfaces in Netbox using information
        provided by NAPALM get_interfaces getter:

        - interface name
        - interface description
        - mtu
        - mac address
        - admin status
        - speed

        :param instance: Netbox instance name
        :param dry_run: return information that would be pushed to Netbox but do not push it
        :param datasource: service name to use to retrieve devices' data, default is nornir parse task
        :param timeout: seconds to wait before timeout data retrieval job
        :param create: create missing interfaces
        :param kwargs: any additional arguments to send to service for device data retrieval
        :returns: dictionary keyed by device name with update details
        """
        result = {}
        instance = instance or self.default_instance
        ret = Result(task=f"{self.name}:update_device_interfaces", result=result)
        nb = self._get_pynetbox(instance)

        if datasource == "nornir":
            if devices:
                kwargs["FL"] = devices
            kwargs["getters"] = "get_interfaces"
            data = self.client.run_job(
                "nornir",
                "parse",
                kwargs=kwargs,
                workers="all",
                timeout=timeout,
            )
            for worker, results in data.items():
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
                    nb_interfaces = nb.dcim.interfaces.filter(device_id=nb_device.id)
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
            raise UnsupportedServiceError(f"'{datasource}' service not supported")

        return ret

    def update_device_ip(
        self,
        instance: str = None,
        dry_run: bool = False,
        datasource: str = "nornir",
        timeout: int = 60,
        devices: list = None,
        create: bool = True,
        **kwargs,
    ) -> dict:
        pass

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
        Method to retrieve existing or allocate new IP address in Netbox.

        :param subnet: IPv4 or IPv6 subnet e.g. ``10.0.0.0/24`` to allocate next
            available IP Address from
        :param description: IP address description to record in Netbox database
        :param device: device name to find interface for and link IP address with
        :param interface: interface name to link IP address with, ``device`` attribute
            also must be provided
        """
        nb = self._get_pynetbox(instance)
        nb_prefix = nb.ipam.prefixes.get(prefix=subnet, vrf=vrf)
        nb_ip = nb_prefix.available_ips.create()
        if description is not None:
            nb_ip.description = description
        nb_ip.save()

        return Result(result=str(nb_ip))
