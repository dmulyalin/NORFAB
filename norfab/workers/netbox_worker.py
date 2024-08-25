"""

### Netbox Worker Inventory Reference



#### Sample Netbox Worker Inventory

``` yaml
service: netbox
broker_endpoint: "tcp://127.0.0.1:5555"
instances:
  prod:
    default: True
    url: "http://192.168.4.130:8000/"
    token: "0123456789abcdef0123456789abcdef01234567"
    ssl_verify: False
  dev:
    url: "http://192.168.4.131:8000/"
    token: "0123456789abcdef0123456789abcdef01234567"
    ssl_verify: False
  preprod:
    url: "http://192.168.4.132:8000/"
    token: "0123456789abcdef0123456789abcdef01234567"
    ssl_verify: False
```

#### Sample Nornir Worker Netbox Inventory

``` yaml
netbox:
  retry: 3
  retry_interval: 1
  instance: prod
  interfaces:
    ip_addresses: True
    inventory_items: True
  connections:
    cables: True
    circuits: True
  nbdata: True
  primary_ip: "ipv4"
  devices:
    - fceos4
    - fceos5
    - fceos8
    - ceos1
  filters: 
    - q: fceos3
    - manufacturer: cisco
      platform: cisco_xr
```
"""

import json
import logging
import sys
import importlib.metadata
import requests
import copy

from norfab.core.worker import NFPWorker, Result
from typing import Union
from requests.packages.urllib3.exceptions import InsecureRequestWarning

log = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# CONSTANTS
# ----------------------------------------------------------------------

DEVICE_FIELDS = [
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
    "site {name tags{name}}",
    "location {name}",
    "rack {name}",
    "status",
    "primary_ip4 {address}",
    "primary_ip6 {address}",
    "airflow",
    "position",
]

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
        service,
        worker_name,
        exit_event=None,
        init_done_event=None,
        log_level="WARNING",
    ):
        super().__init__(broker, service, worker_name, exit_event, log_level)
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

        # find default instance
        for name, params in self.inventory["instances"].items():
            if params.get("default") is True:
                self.default_instance = name
                break
        else:
            self.default_instance = name

        # check Netbox compatibility
        self._verify_compatibility()

        self.init_done_event.set()
        log.info(f"{self.name} - Started")

    # ----------------------------------------------------------------------
    # Netbox Service Functions that exposed for calling
    # ----------------------------------------------------------------------

    def get_netbox_inventory(self) -> Result:
        return Result(
            name=f"{self.name}:get_netbox_inventory", result=dict(self.inventory)
        )

    def get_netbox_version(self, **kwargs) -> Result:
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

        return Result(name=f"{self.name}:get_netbox_version", result=libs)

    def get_netbox_status(self, instance=None) -> Result:
        ret = Result(result={}, name=f"{self.name}:get_netbox_status")
        if instance:
            ret.result[instance] = self._query_netbox_status(instance)
        else:
            for name in self.inventory["instances"].keys():
                ret.result[name] = self._query_netbox_status(name)
        return ret

    def get_compatibility(self) -> Result:
        ret = Result(name=f"{self.name}:get_compatibility", result={})
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
                timeout=(3, 600),
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
        params = self._get_instance_params(instance)

        if params.get("ssl_verify") == False:
            requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
            nb = pynetbox.api(url=params["url"], token=params["token"])
            nb.http_session.verify = False
        else:
            nb = pynetbox.api(url=params["url"], token=params["token"])

        return nb

    def graphql(
        self,
        instance: str = None,
        dry_run: bool = False,
        obj: dict = None,
        filters: dict = None,
        fields: list = None,
        queries: dict = None,
        query_string: str = None,
    ) -> Result:
        """
        Function to query Netbox v4 GraphQL API

        :param instance: Netbox instance name
        :param dry_run: only return query content, do not run it
        """
        nb_params = self._get_instance_params(instance)
        ret = Result(name=f"{self.name}:graphql")

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
            timeout=(3, 600),
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
    ) -> dict:
        """
        Method to query Netbox REST API.

        :param instance: Netbox instance name
        :param method: requests method name e.g. get, post, put etc.
        :param api: api url to query e.g. "extras" or "dcim/interfaces" etc.
        :param kwargs: any additional requests method's arguments
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
    ) -> Result:
        """
        Function to retrieve devices data from Netbox using GraphQL API.

        :param filters: list of filters dictionaries to filter devices
        :param instance: Netbox instance name
        :param dry_run: only return query content, do not run it
        :param devices: list of device names to query data for
        :return: dictionary keyed by device name with device data
        """
        ret = Result(name=f"{self.name}:get_devices", result={})
        instance = instance or self.default_instance
        filters = filters or []

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
            "site {name tags{name}}",
            "location {name}",
            "rack {name}",
            "status",
            "primary_ip4 {address}",
            "primary_ip6 {address}",
            "airflow",
            "position",
        ]

        # form queries dictionary out of filters
        queries = {
            f"devices_by_filter_{index}": {
                "obj": "device_list",
                "filters": filter_item,
                "fields": device_fields,
            }
            for index, filter_item in enumerate(filters)
        }

        # add devices list query
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
        query_result = self.graphql(queries=queries, instance=instance, dry_run=dry_run)
        devices_data = query_result.result

        # return dry run result
        if dry_run:
            return query_result

        # check for errors
        if query_result.errors:
            msg = f"{self.name} - get devices query failed with errors:\n{query_result.errors}"
            raise Exception(msg)

        # process devices
        for devices_list in devices_data.values():
            for device in devices_list:
                if device["name"] not in ret.result:
                    ret.result[device.pop("name")] = device

        return ret

    def get_interfaces(
        self,
        instance: str = None,
        devices: list = None,
        ip_addresses: bool = False,
        inventory_items: bool = False,
        dry_run: bool = False,
    ) -> Result:
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
            name=f"{self.name}:get_interfaces", result={d: {} for d in devices}
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
        circuits: bool = False,
    ) -> Result:
        """
        Function to retrieve device connections data from Netbox using GraphQL API.

        :param instance: Netbox instance name
        :param devices: list of devices to retrieve interface for
        :param dry_run: only return query content, do not run it
        :param cables: if True includes interfaces' directly attached cables details
        :param circuits: if True includes interfaces' circuits termination details
        :return: dictionary keyed by device name with connections data
        """
        # form final result dictionary
        ret = Result(
            name=f"{self.name}:get_connections", result={d: {} for d in devices}
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

        # add circuits info
        if circuits is True:
            interfaces_fields.append(
                """
                link_peers {
                    __typename
                    ... on InterfaceType {name device {name}}
                    ... on FrontPortType {name device {name}}
                    ... on RearPortType {name device {name}}
                    ... on CircuitTerminationType {
                        circuit{
                            cid 
                            description 
                            tags{name} 
                            provider{name} 
                            status
                            custom_fields
                            commit_rate
                        }
                    }
                }
            """
            )
        else:
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

                # handle circuits
                if (
                    circuits and "circuit" in link_peers[0]
                ):  # add circuit connection details
                    connection["circuit"] = link_peers[0]["circuit"]

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

    def get_circuits(
        self,
        devices: list,
        instance: str = None,
        dry_run: bool = False,
    ):
        """
        Function to retrieve device circuits data from Netbox using GraphQL API.

        :param devices: list of devices to retrieve interface for
        :param instance: Netbox instance name
        :param dry_run: only return query content, do not run it
        :return: dictionary keyed by device name with circuits data
        """
        # form final result object
        ret = Result(name=f"{self.name}:get_circuits", result={d: {} for d in devices})

        device_sites_fields = ["site {slug}"]
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
            "termination_a {id}",
            "termination_z {id}",
            "custom_fields",
            "comments",
        ]

        # retrieve list of hosts' sites
        if self.nb_version[0] == 4:
            dlist = '["{dl}"]'.format(dl='", "'.join(devices))
            device_filters_dict = {"name": f"{{in_list: {dlist}}}"}
        elif self.nb_version[0] == 3:
            device_filters_dict = {"name": devices}
        device_sites = self.graphql(
            obj="device_list",
            filters=device_filters_dict,
            fields=device_sites_fields,
            instance=instance,
        )
        sites = list(set([i["site"]["slug"] for i in device_sites.result]))

        # retrieve all circuits for devices' sites
        if self.nb_version[0] == 4:
            circuits_filters_dict = {"site": sites}
        elif self.nb_version[0] == 3:
            circuits_filters_dict = {"site": sites}

        query_result = self.graphql(
            obj="circuit_list",
            filters=circuits_filters_dict,
            fields=circuit_fields,
            dry_run=dry_run,
            instance=instance,
        )

        # return dry run result
        if dry_run is True:
            return query_result

        all_circuits = query_result.result

        # iterate over circuits and map them to devices
        for circuit in all_circuits:
            cid = circuit.pop("cid")
            circuit["tags"] = [i["name"] for i in circuit["tags"]]
            circuit["type"] = circuit["type"]["name"]
            circuit["provider"] = circuit["provider"]["name"]
            circuit["tenant"] = circuit["tenant"]["name"] if circuit["tenant"] else None
            circuit["provider_account"] = (
                circuit["provider_account"]["name"]
                if circuit["provider_account"]
                else None
            )
            termination_a = circuit.pop("termination_a")
            termination_z = circuit.pop("termination_z")
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
                continue

            # check if circuit ends connect to device or provider network
            if (
                not circuit_path
                or "name" not in circuit_path[0]["path"][0][0]
                or "name" not in circuit_path[0]["path"][-1][-1]
            ):
                continue

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
            if end_z["device"] and end_z["device"] in devices:
                ret.result[end_z["device"]][cid] = copy.deepcopy(circuit)
                ret.result[end_z["device"]][cid]["interface"] = end_z["name"]
                if end_a["device"]:
                    ret.result[end_z["device"]][cid]["remote_device"] = end_a["device"]
                    ret.result[end_z["device"]][cid]["remote_interface"] = end_a["name"]
                elif end_a["provider_network"]:
                    ret.result[end_z["device"]][cid]["provider_network"] = end_a["name"]

        return ret

    def get_nornir_inventory(
        self,
        filters: list = None,
        devices: list = None,
        instance: str = None,
        interfaces: Union[dict, bool] = False,
        connections: Union[dict, bool] = False,
        circuits: Union[dict, bool] = False,
        nbdata: bool = False,
        primary_ip: str = "ip4",
    ) -> Result:
        """
        Method to query Netbox and return devices data in Nornir inventory format.
        """
        hosts = {}
        inventory = {"hosts": hosts}
        ret = Result(name=f"{self.name}:get_nornir_inventory", result=inventory)

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

    def get_next_ip(
        self,
        prefix: str,
        device: str = None,
        interface: str = None,
        secondary: bool = False,
        instance: str = None,
        dry_run: bool = False,
        kwargs: dict = None,
    ):
        """
        Method to allocate next available IP address in Netbox
        """
