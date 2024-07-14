import pprint
import pytest
import random

def get_nb_version(nfclient, instance=None) -> tuple:
    ret = nfclient.run_job(
        b"netbox",
        "get_netbox_status",
        workers="any",
        kwargs={"instance": instance}
    )
    # pprint.pprint(f">>>>>>>>>>>> {ret}")
    for w, instances_data in ret.items():
        for instance, instance_data in instances_data.items():
            return tuple([int(i) for i in instance_data["netbox-version"].split(".")])

                
class TestNetboxWorker:
    @pytest.mark.skip(reason="TBD")
    def test_get_netbox_inventory(self, nfclient):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_get_netbox_version(self, nfclient):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_get_netbox_status(self, nfclient):
        pass
        
    @pytest.mark.skip(reason="TBD")
    def test_get_netbox_compatibility(self, nfclient):
        pass


class TestNetboxGrapQL:
    nb_version = None
    
    def test_graphql_query_string(self, nfclient):
        ret = nfclient.run_job(
            b"netbox",
            "graphql",
            workers="any",
            kwargs={"query_string": "query DeviceListQuery { device_list { name } }"},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert "Traceback" not in res, f"{worker} - received error"
            assert "device_list" in res, f"{worker} no device list returned"
            assert isinstance(
                res["device_list"], list
            ), f"{worker} unexpected device list payload type, was expecting list"
            assert (
                len(res["device_list"]) > 0
            ), f"{worker} returned no devices in device list"

    def test_graphql_query_string_with_instance(self, nfclient):
        ret = nfclient.run_job(
            b"netbox",
            "graphql",
            workers="any",
            kwargs={
                "query_string": "query DeviceListQuery { device_list { name } }",
                "instance": "prod",
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert "Traceback" not in res, f"{worker} - received error"
            assert "device_list" in res, f"{worker} no device list returned"
            assert isinstance(
                res["device_list"], list
            ), f"{worker} unexpected device list payload type, was expecting list"
            assert (
                len(res["device_list"]) > 0
            ), f"{worker} returned no devices in device list"

    def test_graphql_query_string_dry_run(self, nfclient):
        ret = nfclient.run_job(
            b"netbox",
            "graphql",
            workers="any",
            kwargs={
                "query_string": "query DeviceListQuery { device_list { name } }",
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert "Traceback" not in res, f"{worker} - received error"
            assert all(
                k in res for k in ["headers", "data", "verify", "url"]
            ), f"{worker} - not all dry run data returned"

    def test_graphql_query_string_error(self, nfclient):
        ret = nfclient.run_job(
            b"netbox",
            "graphql",
            workers="any",
            kwargs={
                "query_string": "query DeviceListQuery { device_list { name } ",
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert (
                "errors" in res
            ), f"{worker} did not return errors fro malformed graphql query"

    def test_form_graphql_query_dry_run(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        if self.nb_version[0] == 4:
            ret = nfclient.run_job(
                b"netbox",
                "graphql",
                workers="any",
                kwargs={
                    "obj": "device_list",
                    "fields": ["name", "platform {name}"],
                    "filters": {"q": "ceos", "platform": "arista_eos"},
                    "dry_run": True,
                },
            )
            pprint.pprint(ret, width=200)
            for worker, res in ret.items():
                assert res["data"] == (
                    '{"query": "query {device_list(filters: {q: \\"ceos\\", platform: \\"arista_eos\\"}) {name platform {name}}}"}'
                ), f"{worker} did not return correct query string"
        elif self.nb_version[0] == 3:
            ret = nfclient.run_job(
                b"netbox",
                "graphql",
                workers="any",
                kwargs={
                    "obj": "device_list",
                    "fields": ["name", "platform {name}"],
                    "filters": {"name__ic": "ceos", "platform": "arista_eos"},
                    "dry_run": True,
                },
            )
            pprint.pprint(ret, width=200)
            for worker, res in ret.items():
                assert res["data"] == (
                    '{"query": "query {device_list(name__ic: \\"ceos\\", platform: \\"arista_eos\\") {name platform {name}}}"}'
                ), f"{worker} did not return correct query string"

    def test_form_graphql_query_dry_run_composite_filter(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        if self.nb_version[0] == 4:
            ret = nfclient.run_job(
                b"netbox",
                "graphql",
                workers="any",
                kwargs={
                    "obj": "interface_list",
                    "fields": ["name"],
                    "filters": {"q": "eth", "type": '{exact: "virtual"}'},
                    "dry_run": True,
                },
            )
            pprint.pprint(ret, width=200)
    
            for worker, res in ret.items():
                assert res["data"] == (
                    '{"query": "query {interface_list(filters: {q: \\"eth\\", type: {exact: \\"virtual\\"}}) {name}}"}'
                ), f"{worker} did not return correct query string"
        elif self.nb_version[0] == 3:
            pytest.skip("Only for Netbox v4")
                    

    def test_form_graphql_query_dry_run_list_filter(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        if self.nb_version[0] == 4:
            ret = nfclient.run_job(
                b"netbox",
                "graphql",
                workers="any",
                kwargs={
                    "obj": "ip_address_list",
                    "fields": ["address"],
                    "filters": {"address": ["1.0.10.3/32", "1.0.10.1/32"]},
                    "dry_run": True,
                },
            )
            pprint.pprint(ret, width=200)
    
            for worker, res in ret.items():
                assert res["data"] == (
                    '{"query": "query {ip_address_list(filters: {address: [\\"1.0.10.3/32\\", \\"1.0.10.1/32\\"]}) {address}}"}'
                ), f"{worker} did not return correct query string"
        elif self.nb_version[0] == 3:
            ret = nfclient.run_job(
                b"netbox",
                "graphql",
                workers="any",
                kwargs={
                    "obj": "ip_address_list",
                    "fields": ["address"],
                    "filters": {"address": ["1.0.10.3/32", "1.0.10.1/32"]},
                    "dry_run": True,
                },
            )
            pprint.pprint(ret, width=200)
    
            for worker, res in ret.items():
                assert res["data"] == (
                    '{"query": "query {ip_address_list(address: [\\"1.0.10.3/32\\", \\"1.0.10.1/32\\"]) {address}}"}'
                ), f"{worker} did not return correct query string"

    def test_form_graphql_query(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        if self.nb_version[0] == 4:
            ret = nfclient.run_job(
                b"netbox",
                "graphql",
                workers="any",
                kwargs={
                    "obj": "device_list",
                    "fields": ["name", "platform {name}"],
                    "filters": {"q": "ceos", "platform": "arista_eos"},
                },
            )
            pprint.pprint(ret)
    
            for worker, res in ret.items():
                assert isinstance(res, list), f"{worker} - unexpected result type"
                for item in res:
                    assert (
                        "name" in item and "platform" in item
                    ), f"{worker} - no name and platform returned: {item}"
        elif self.nb_version[0] == 3:
            ret = nfclient.run_job(
                b"netbox",
                "graphql",
                workers="any",
                kwargs={
                    "obj": "device_list",
                    "fields": ["name", "platform {name}"],
                    "filters": {"name__ic": "ceos", "platform": "arista_eos"},
                },
            )
            pprint.pprint(ret)
    
            for worker, res in ret.items():
                assert isinstance(res, list), f"{worker} - unexpected result type"
                for item in res:
                    assert (
                        "name" in item and "platform" in item
                    ), f"{worker} - no name and platform returned: {item}"
                    

    def test_form_graphql_queries_with_aliases_dry_run(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        if self.nb_version[0] == 4:
            ret = nfclient.run_job(
                b"netbox",
                "graphql",
                workers="any",
                kwargs={
                    "queries": {
                        "devices": {
                            "obj": "device_list",
                            "fields": ["name", "platform {name}"],
                            "filters": {"q": "ceos", "platform": "arista_eos"},
                        },
                        "interfaces": {
                            "obj": "interface_list",
                            "fields": ["name"],
                            "filters": {"q": "eth", "type": '{exact: "virtual"}'},
                        },
                        "addresses": {
                            "obj": "ip_address_list",
                            "fields": ["address"],
                            "filters": {"address": ["1.0.10.3/32", "1.0.10.1/32"]},
                        },
                    },
                    "dry_run": True,
                },
            )
            pprint.pprint(ret, width=200)
    
            for worker, res in ret.items():
                assert res["data"] == (
                    '{"query": "query {devices: device_list(filters: {q: \\"ceos\\", platform: '
                    + '\\"arista_eos\\"}) {name platform {name}}    interfaces: interface_list(filters: '
                    + '{q: \\"eth\\", type: {exact: \\"virtual\\"}}) {name}    addresses: '
                    + 'ip_address_list(filters: {address: [\\"1.0.10.3/32\\", \\"1.0.10.1/32\\"]}) {address}}"}'
                ), f"{worker} did not return correct query string"
        elif self.nb_version[0] == 3:
            ret = nfclient.run_job(
                b"netbox",
                "graphql",
                workers="any",
                kwargs={
                    "queries": {
                        "devices": {
                            "obj": "device_list",
                            "fields": ["name", "platform {name}"],
                            "filters": {"name__ic": "ceos", "platform": "arista_eos"},
                        },
                        "interfaces": {
                            "obj": "interface_list",
                            "fields": ["name"],
                            "filters": {"name__ic": "eth", "type": "virtual"},
                        },
                        "addresses": {
                            "obj": "ip_address_list",
                            "fields": ["address"],
                            "filters": {"address": ["1.0.10.3/32", "1.0.10.1/32"]},
                        },
                    },
                    "dry_run": True,
                },
            )
            pprint.pprint(ret, width=200)
    
            for worker, res in ret.items():
                assert res["data"] == (
                    '{"query": "query {devices: device_list(name__ic: \\"ceos\\", platform: \\"arista_eos\\") ' +
                    '{name platform {name}}    interfaces: interface_list(name__ic: \\"eth\\", type: \\"virtual\\") ' +
                    '{name}    addresses: ip_address_list(address: [\\"1.0.10.3/32\\", \\"1.0.10.1/32\\"]) {address}}"}'
                ), f"{worker} did not return correct query string"

    def test_form_graphql_queries_with_aliases(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        if self.nb_version[0] == 4:
            ret = nfclient.run_job(
                b"netbox",
                "graphql",
                workers="any",
                kwargs={
                    "queries": {
                        "devices": {
                            "obj": "device_list",
                            "fields": ["name", "platform {name}"],
                            "filters": {"q": "ceos", "platform": "arista_eos"},
                        },
                        "interfaces": {
                            "obj": "interface_list",
                            "fields": ["name"],
                            "filters": {"q": "eth", "type": '{exact: "virtual"}'},
                        },
                        "addresses": {
                            "obj": "ip_address_list",
                            "fields": ["address"],
                            "filters": {"address": '{in_list: ["1.0.10.3/32", "1.0.10.1/32"]}'},
                        },
                    },
                },
            )
            pprint.pprint(ret, width=200)
    
            for worker, res in ret.items():
                assert all(
                    k in res for k in ["devices", "interfaces", "addresses"]
                ), f"{worker} - did not return some data"
        elif self.nb_version[0] == 3:
            ret = nfclient.run_job(
                b"netbox",
                "graphql",
                workers="any",
                kwargs={
                    "queries": {
                        "devices": {
                            "obj": "device_list",
                            "fields": ["name", "platform {name}"],
                            "filters": {"name__ic": "ceos", "platform": "arista_eos"},
                        },
                        "interfaces": {
                            "obj": "interface_list",
                            "fields": ["name"],
                            "filters": {"name__ic": "eth", "type": "virtual"},
                        },
                        "addresses": {
                            "obj": "ip_address_list",
                            "fields": ["address"],
                            "filters": {"address": ["1.0.10.3/32", "1.0.10.1/32"]},
                        },
                    },
                },
            )
            pprint.pprint(ret, width=200)
    
            for worker, res in ret.items():
                assert all(
                    k in res for k in ["devices", "interfaces", "addresses"]
                ), f"{worker} - did not return some data"


class TestGetInterfaces:
    nb_version = None
    
    def test_get_interfaces(self, nfclient):
        ret = nfclient.run_job(
            b"netbox",
            "get_interfaces",
            workers="any",
            kwargs={
                "devices": ["ceos1", "fceos4"]
            },
        )
        pprint.pprint(ret)
        
        for worker, res in ret.items():
            assert "ceos1" in res, f"{worker} returned no results for ceos1"
            assert "fceos4" in res, f"{worker} returned no results for fceos4"
            for device, interfaces in res.items():
                assert isinstance(interfaces, dict), f"{worker}:{device} did not return interfaces dictionary" 
                for intf_name, intf_data in interfaces.items():
                    assert all(
                        k in intf_data for k in [
                            "enabled",
                            "description",
                            "mtu",
                            "parent",
                            "mac_address",
                            "mode",
                            "untagged_vlan",
                            "vrf",
                            "tagged_vlans",
                            "tags",
                            "custom_fields",
                            "last_updated",
                            "bridge",
                            "child_interfaces",
                            "bridge_interfaces",
                            "member_interfaces",
                            "wwn",
                            "duplex",
                            "speed",
                        ]
                    ), f"{worker}:{device}:{intf_name} not all data returned" 
                    

    def test_get_interfaces_with_instance(self, nfclient):
        ret = nfclient.run_job(
            b"netbox",
            "get_interfaces",
            workers="any",
            kwargs={
                "devices": ["ceos1", "fceos4"],
                "instance": "prod"
            },
        )
        pprint.pprint(ret)
        
        for worker, res in ret.items():
            assert "ceos1" in res, f"{worker} returned no results for ceos1"
            assert "fceos4" in res, f"{worker} returned no results for fceos4"
            for device, interfaces in res.items():
                assert isinstance(interfaces, dict), f"{worker}:{device} did not return interfaces dictionary" 
                for intf_name, intf_data in interfaces.items():
                    assert all(
                        k in intf_data for k in [
                            "enabled",
                            "description",
                            "mtu",
                            "parent",
                            "mac_address",
                            "mode",
                            "untagged_vlan",
                            "vrf",
                            "tagged_vlans",
                            "tags",
                            "custom_fields",
                            "last_updated",
                            "bridge",
                            "child_interfaces",
                            "bridge_interfaces",
                            "member_interfaces",
                            "wwn",
                            "duplex",
                            "speed",
                        ]
                    ), f"{worker}:{device}:{intf_name} not all data returned" 
                    
    def test_get_interfaces_dry_run(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)
        
        ret = nfclient.run_job(
            b"netbox",
            "get_interfaces",
            workers="any",
            kwargs={
                "devices": ["ceos1", "fceos4"],
                "dry_run": True
            },
        )
        pprint.pprint(ret)
        
        if self.nb_version[0] == 4:
            for worker, res in ret.items():
                assert res["data"] == (
                    '{"query": "query {interfaces: interface_list(filters: {device: [\\"ceos1\\", ' +
                    '\\"fceos4\\"]}) {name enabled description mtu parent {name} mac_address mode ' +
                    'untagged_vlan {vid name} vrf {name} tagged_vlans {vid name} tags {name} ' +
                    'custom_fields last_updated bridge {name} child_interfaces {name} bridge_interfaces ' +
                    '{name} member_interfaces {name} wwn duplex speed id device {name}}}"}'
                ), f"{worker} did not return correct query string"
        elif self.nb_version[0] == 3:
            for worker, res in ret.items():
                assert res["data"] == (
                    '{"query": "query {interfaces: interface_list(device: [\\"ceos1\\", \\"fceos4\\"]) ' +
                    '{name enabled description mtu parent {name} mac_address mode untagged_vlan {vid name} ' +
                    'vrf {name} tagged_vlans {vid name} tags {name} custom_fields last_updated bridge ' +
                    '{name} child_interfaces {name} bridge_interfaces {name} member_interfaces {name} wwn ' +
                    'duplex speed id device {name}}}"}'
                ), f"{worker} did not return correct query string"
            
            
    def test_get_interfaces_add_ip(self, nfclient):
        ret = nfclient.run_job(
            b"netbox",
            "get_interfaces",
            workers="any",
            kwargs={
                "devices": ["ceos1", "fceos4"],
                "ip_addresses": True
            },
        )
        pprint.pprint(ret)
        
        for worker, res in ret.items():
            assert "ceos1" in res, f"{worker} returned no results for ceos1"
            assert "fceos4" in res, f"{worker} returned no results for fceos4"
            for device, interfaces in res.items():
                assert isinstance(interfaces, dict), f"{worker}:{device} did not return interfaces dictionary" 
                for intf_name, intf_data in interfaces.items():
                    assert "ip_addresses" in intf_data, f"{worker}:{device}:{intf_name} no IP addresses data returned"
                    for ip in intf_data["ip_addresses"]:
                        assert all(
                            k in ip for k in [
                                "address", 
                                "status", 
                                "role", 
                                "dns_name", 
                                "description", 
                                "custom_fields", 
                                "last_updated", 
                                "tenant", 
                                "tags"
                            ]
                        ), f"{worker}:{device}:{intf_name} not all IP data returned" 
                        
                        
    def test_get_interfaces_add_inventory_items(self, nfclient):
        ret = nfclient.run_job(
            b"netbox",
            "get_interfaces",
            workers="any",
            kwargs={
                "devices": ["ceos1", "fceos4"],
                "inventory_items": True,
            },
        )
        pprint.pprint(ret, width=200)
        
        for worker, res in ret.items():
            assert "ceos1" in res, f"{worker} returned no results for ceos1"
            assert "fceos4" in res, f"{worker} returned no results for fceos4"
            for device, interfaces in res.items():
                assert isinstance(interfaces, dict), f"{worker}:{device} did not return interfaces dictionary" 
                for intf_name, intf_data in interfaces.items():
                    assert "inventory_items" in intf_data, f"{worker}:{device}:{intf_name} no inventory items data returned"
                    for item in intf_data["inventory_items"]:
                        assert all(
                            k in item for k in [
                                "name",
                                "role",
                                "manufacturer",
                                "custom_fields",
                                "label",
                                "description",
                                "tags",
                                "asset_tag",
                                "serial",
                                "part_id",
                            ]
                        ), f"{worker}:{device}:{intf_name} not all inventory item data returned" 
                        
                        
class TestGetDevices:
    nb_version = None
    
    def test_with_devices_list(self, nfclient):
        ret = nfclient.run_job(
            b"netbox",
            "get_devices",
            workers="any",
            kwargs={
                "devices": ["ceos1", "fceos4"]
            },
        )
        pprint.pprint(ret)
        
        for worker, res in ret.items():
            assert "ceos1" in res, f"{worker} returned no results for ceos1"
            assert "fceos4" in res, f"{worker} returned no results for fceos4"
            for device, device_data in res.items():
                assert isinstance(device_data, dict), f"{worker}:{device} did not return device data as dictionary" 
                assert all(
                    k in device_data for k in [
                        "last_updated",
                        "custom_field_data",
                        "tags",
                        "device_type",
                        "config_context",
                        "tenant",
                        "platform",
                        "serial",
                        "asset_tag",
                        "site",
                        "location",
                        "rack",
                        "status",
                        "primary_ip4",
                        "primary_ip6",
                        "airflow",
                        "position",
                    ]
                ), f"{worker}:{device} not all data returned" 
                assert "role" in device_data or "devcie_role" in device_data, f"{worker}:{device} nodevice role info returned" 
                
    def test_with_filters(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)
    
        if self.nb_version[0] == 4:
            ret = nfclient.run_job(
                b"netbox",
                "get_devices",
                workers="any",
                kwargs={
                    "filters": [
                        {"name": '{in_list: ["ceos1", "fceos4"]}'},
                        {"q": "390"},
                    ]
                },
            )
        elif self.nb_version[0] == 3:
            ret = nfclient.run_job(
                b"netbox",
                "get_devices",
                workers="any",
                kwargs={
                    "filters": [
                        {"name": ["ceos1", "fceos4"]},
                        {"name__ic": "390"},
                    ]
                },
            )
        pprint.pprint(ret)
                
        for worker, res in ret.items():
            assert "ceos1" in res, f"{worker} returned no results for ceos1"
            assert "fceos3_390" in res, f"{worker} returned no results for fceos3_390"
            assert "fceos4" in res, f"{worker} returned no results for fceos4"
            for device, device_data in res.items():
                assert isinstance(device_data, dict), f"{worker}:{device} did not return device data as dictionary" 
                assert all(
                    k in device_data for k in [
                        "last_updated",
                        "custom_field_data",
                        "tags",
                        "device_type",
                        "config_context",
                        "tenant",
                        "platform",
                        "serial",
                        "asset_tag",
                        "site",
                        "location",
                        "rack",
                        "status",
                        "primary_ip4",
                        "primary_ip6",
                        "airflow",
                        "position",
                    ]
                ), f"{worker}:{device} not all data returned" 
                assert "role" in device_data or "devcie_role" in device_data, f"{worker}:{device} nodevice role info returned" 
                
                
    def test_with_filters_dry_run(self, nfclient):
        ret = nfclient.run_job(
            b"netbox",
            "get_devices",
            workers="any",
            kwargs={
                "filters": [
                    {"name": ["ceos1", "fceos4"]},
                    {"q": "390"},
                ],
                "dry_run": True
            },
        )
        pprint.pprint(ret)
        
        for worker, res in ret.items():
            assert "Traceback" not in res, f"{worker} - received error"
            assert all(
                k in res for k in ["headers", "data", "verify", "url"]
            ), f"{worker} - not all dry run data returned"


class TestGetConnections:

    def test_get_connections(self, nfclient):
        ret = nfclient.run_job(
            b"netbox",
            "get_connections",
            workers="any",
            kwargs={
                "devices": ["fceos4", "fceos5"],
            },
        )
        pprint.pprint(ret)
        
        for worker, res in ret.items():
            assert "fceos5" in res, f"{worker} returned no results for fceos5"
            assert "fceos4" in res, f"{worker} returned no results for fceos4"
            assert "ConsolePort1" in res["fceos4"], f"{worker}:fceos4 no console ports data returned"
            assert "ConsoleServerPort1" in res["fceos5"], f"{worker}:fceos5 no console server ports data returned"
            for device, interfaces in res.items():
                assert isinstance(interfaces, dict), f"{worker}:{device} did not return interfaces dictionary" 
                for intf_name, intf_data in interfaces.items():
                    assert all(
                        k in intf_data for k in [
                            "breakout",
                            "remote_device",
                            "remote_interface",
                            "remote_termination_type",
                            "termination_type"
                        ]
                    ), f"{worker}:{device}:{intf_name} not all data returned" 
                    # verify provider network connection handling
                    if device == "fceos4" and intf_name == "eth201":
                        assert "provider" in intf_data, f"{worker}:{device}:{intf_name} no provider data" 
                        assert intf_data["remote_termination_type"] == "providernetwork"
                        assert intf_data["remote_device"] == None
                        assert intf_data["remote_interface"] == None
                    # verify breakout handling
                    if device == "fceos5" and intf_name == "eth1":
                        assert intf_data["breakout"] == True, f"{worker}:{device}:{intf_name} was expecting breakout connection" 
                        assert isinstance(intf_data["remote_interface"], list)
                        assert len(intf_data["remote_interface"]) > 1

    def test_get_connections_dry_run(self, nfclient):
        ret = nfclient.run_job(
            b"netbox",
            "get_connections",
            workers="any",
            kwargs={
                "devices": ["fceos4", "fceos5"],
                "dry_run": True
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert "Traceback" not in res, f"{worker} - received error"
            assert all(
                k in res for k in ["headers", "data", "verify", "url"]
            ), f"{worker} - not all dry run data returned"

    def test_get_connections_and_cables(self, nfclient):
        ret = nfclient.run_job(
            b"netbox",
            "get_connections",
            workers="any",
            kwargs={
                "devices": ["fceos4", "fceos5"],
                "cables": True
            },
        )
        pprint.pprint(ret)
        
        for worker, res in ret.items():
            assert "fceos5" in res, f"{worker} returned no results for fceos5"
            assert "fceos4" in res, f"{worker} returned no results for fceos4"
            for device, interfaces in res.items():
                assert isinstance(interfaces, dict), f"{worker}:{device} did not return interfaces dictionary" 
                for intf_name, intf_data in interfaces.items():
                    assert "cable" in intf_data, f"{worker}:{device}:{intf_name} no cable data returned" 
                    assert all(
                        k in intf_data["cable"] for k in [
                            "custom_fields",
                            "label",
                            "length",
                            "length_unit",
                            "peer_device",
                            "peer_interface",
                            "peer_termination_type",
                            "status",
                            "tags",
                            "tenant",
                            "type",
                        ]
                    ), f"{worker}:{device}:{intf_name} not all cable data returned" 
                    # verify circuit connection handling
                    if device == "fceos4" and intf_name == "eth201":
                        assert intf_data["cable"]["peer_termination_type"] == "circuittermination"
                        assert intf_data["cable"]["peer_device"] == None
                        assert intf_data["cable"]["peer_interface"] == None
                    
    def test_get_connections_and_circuits(self, nfclient):
        ret = nfclient.run_job(
            b"netbox",
            "get_connections",
            workers="any",
            kwargs={
                "devices": ["fceos4", "fceos5"],
                "circuits": True
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert "fceos5" in res, f"{worker} returned no results for fceos5"
            assert "fceos4" in res, f"{worker} returned no results for fceos4"
            for device, interfaces in res.items():
                assert isinstance(interfaces, dict), f"{worker}:{device} did not return interfaces dictionary" 
                for intf_name, intf_data in interfaces.items():
                    if device == "fceos5" and intf_name == "eth8":
                        assert "circuit" in intf_data, f"{worker}:{device}:{intf_name} no circuit data returned" 
                        assert all(
                            k in intf_data["circuit"] for k in [
                                "cid",
                                "commit_rate",
                                "custom_fields",
                                "description",
                                "provider",
                                "status",
                                "tags",
                            ]
                        ), f"{worker}:{device}:{intf_name} not all cable data returned" 
                    
                    
    def test_get_connections_and_circuits_and_cables(self, nfclient):
        ret = nfclient.run_job(
            b"netbox",
            "get_connections",
            workers="any",
            kwargs={
                "devices": ["fceos4", "fceos5"],
                "circuits": True,
                "cables": True
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert "fceos5" in res, f"{worker} returned no results for fceos5"
            assert "fceos4" in res, f"{worker} returned no results for fceos4"
            for device, interfaces in res.items():
                assert isinstance(interfaces, dict), f"{worker}:{device} did not return interfaces dictionary" 
                for intf_name, intf_data in interfaces.items():
                    # verify crcuit data
                    if device == "fceos5" and intf_name == "eth8":
                        assert "circuit" in intf_data, f"{worker}:{device}:{intf_name} no circuit data returned" 
                        assert all(
                            k in intf_data["circuit"] for k in [
                                "cid",
                                "commit_rate",
                                "custom_fields",
                                "description",
                                "provider",
                                "status",
                                "tags",
                            ]
                        ), f"{worker}:{device}:{intf_name} not all cable data returned" 
                    # verify cable data
                    assert "cable" in intf_data, f"{worker}:{device}:{intf_name} no cable data returned" 
                    assert all(
                        k in intf_data["cable"] for k in [
                            "custom_fields",
                            "label",
                            "length",
                            "length_unit",
                            "peer_device",
                            "peer_interface",
                            "peer_termination_type",
                            "status",
                            "tags",
                            "tenant",
                            "type",
                        ]
                    ), f"{worker}:{device}:{intf_name} not all cable data returned" 
                    # verify circuit connection handling
                    if device == "fceos4" and intf_name == "eth201":
                        assert intf_data["cable"]["peer_termination_type"] == "circuittermination"
                        assert intf_data["cable"]["peer_device"] == None
                        assert intf_data["cable"]["peer_interface"] == None
    
    
class TestGetNornirInventory:
    nb_version = None
    
    def test_with_devices(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_nornir_inventory",
            workers="any",
            kwargs={
                "devices": ["ceos1", "fceos4", "nonexist"]
            },
        )
        pprint.pprint(ret)
        
        for worker, res in ret.items():
            assert "ceos1" in res["hosts"], f"{worker} returned no results for ceos1"
            assert "fceos4" in res["hosts"], f"{worker} returned no results for fceos4"
            for device, data in res["hosts"].items():
                assert all(
                    k in data for k in [
                        "data",
                        "hostname", 
                        "platform"
                    ]
                ), f"{worker}:{device} not all data returned"
        
    def test_with_filters(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)
    
        if self.nb_version[0] == 4:
            ret = nfclient.run_job(
                "netbox",
                "get_nornir_inventory",
                workers="any",
                kwargs={
                    "filters": [
                        {"name": '{in_list: ["ceos1"]}'},
                        {"name": '{contains: "fceos"}'},
                    ]
                },
            )
        elif self.nb_version[0] == 3:
            ret = nfclient.run_job(
                "netbox",
                "get_nornir_inventory",
                workers="any",
                kwargs={
                    "filters": [
                        {"name": ["ceos1"]},
                        {"name__ic":"fceos"},
                    ]
                },
            )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert "ceos1" in res["hosts"], f"{worker} returned no results for ceos1"
            assert "fceos4" in res["hosts"], f"{worker} returned no results for fceos4"
            for device, data in res["hosts"].items():
                assert all(
                    k in data for k in [
                        "data",
                        "hostname", 
                        "platform"
                    ]
                ), f"{worker}:{device} not all data returned"
                
        
    def test_source_platform_from_config_context(self, nfclient):
        # for iosxr1 platform data encoded in config context
        ret = nfclient.run_job(
            "netbox",
            "get_nornir_inventory",
            workers="any",
            kwargs={
                "devices": ["iosxr1"]
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert "iosxr1" in res["hosts"], f"{worker} returned no results for iosxr1"
            for device, data in res["hosts"].items():
                assert all(
                    k in data for k in [
                        "data",
                        "hostname", 
                        "platform"
                    ]
                ), f"{worker}:{device} not all data returned"
                
        
    def test_with_devices_nbdata_is_true(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_nornir_inventory",
            workers="any",
            kwargs={
                "devices": ["ceos1", "fceos4"],
                "nbdata": True
            },
        )
        pprint.pprint(ret)
        
        for worker, res in ret.items():
            assert "ceos1" in res["hosts"], f"{worker} returned no results for ceos1"
            assert "fceos4" in res["hosts"], f"{worker} returned no results for fceos4"
            for device, data in res["hosts"].items():
                assert all(
                    k in data for k in [
                        "data",
                        "hostname", 
                        "platform"
                    ]
                ), f"{worker}:{device} not all device data returned"
                assert all(
                    k in data["data"] for k in [
                        "airflow",
                        "asset_tag",
                        "config_context",
                        "custom_field_data",
                        "device_type",
                        "last_updated",
                        "location",
                        "platform",
                        "position",
                        "primary_ip4",
                        "primary_ip6",
                        "rack",
                        "role",
                        "serial",
                        "site",
                        "status",
                        "tags",
                        "tenant",
                    ]
                ), f"{worker}:{device} not all nbdata returned"
        
    def test_with_devices_add_interfaces(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_nornir_inventory",
            workers="any",
            kwargs={
                "devices": ["ceos1", "fceos4"],
                "interfaces": True
            },
        )
        pprint.pprint(ret)
        
        for worker, res in ret.items():
            assert "ceos1" in res["hosts"], f"{worker} returned no results for ceos1"
            assert "fceos4" in res["hosts"], f"{worker} returned no results for fceos4"
            for device, data in res["hosts"].items():
                assert data["data"]["interfaces"], f"{worker}:{device} no interfaces data returned"
                for intf_name, intf_data in data["data"]["interfaces"].items():
                    assert all(
                        k in intf_data for k in [
                            "vrf",
                            "mode", 
                            "description",
                        ]
                    ), f"{worker}:{device}:{intf_name} not all interface data returned"
        
    def test_with_devices_add_interfaces_with_ip_and_inventory(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_nornir_inventory",
            workers="any",
            kwargs={
                "devices": ["ceos1", "fceos4"],
                "interfaces": {
                    "ip_addresses": True,
                    "inventory_items": True
                }
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert "ceos1" in res["hosts"], f"{worker} returned no results for ceos1"
            assert "fceos4" in res["hosts"], f"{worker} returned no results for fceos4"
            for device, data in res["hosts"].items():
                assert data["data"]["interfaces"], f"{worker}:{device} no interfaces data returned"
                for intf_name, intf_data in data["data"]["interfaces"].items():
                    assert "ip_addresses" in intf_data, f"{worker}:{device}:{intf_name} no ip addresses data returned"
                    assert "inventory_items" in intf_data, f"{worker}:{device}:{intf_name} no invetnory data returned"
                    
        
    def test_with_devices_add_connections(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_nornir_inventory",
            workers="any",
            kwargs={
                "devices": ["fceos4", "fceos5"],
                "connections": True
            },
        )
        pprint.pprint(ret)
        
        for worker, res in ret.items():
            assert "fceos5" in res["hosts"], f"{worker} returned no results for fceos5"
            assert "fceos4" in res["hosts"], f"{worker} returned no results for fceos4"
            for device, data in res["hosts"].items():
                assert data["data"]["connections"], f"{worker}:{device} no connections data returned"
                for intf_name, intf_data in data["data"]["connections"].items():
                    assert all(
                        k in intf_data for k in [
                            "remote_interface",
                            "remote_device", 
                        ]
                    ), f"{worker}:{device}:{intf_name} not all connection data returned"
        
    @pytest.mark.skip(reason="TBD")
    def test_with_devices_add_circuits(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_nornir_inventory",
            workers="any",
            kwargs={
                "devices": ["ceos1", "fceos4"]
            },
        )
        pprint.pprint(ret)
        
        
class TestGetCircuits:
    nb_version = None
    
    def test_get_circuits_dry_run(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        if self.nb_version[0] == 3:
            ret = nfclient.run_job(
                b"netbox",
                "get_circuits",
                workers="any",
                kwargs={
                    "devices": ["fceos4", "fceos5"],
                    "dry_run": True,
                },
            )
            pprint.pprint(ret, width=200)
            for worker, res in ret.items():
                assert res["data"] == (
                    '{"query": "query {circuit_list(site: ' +
                    '[\\"saltnornir-lab\\"]) {cid tags {name} ' +
                    'provider {name} commit_rate description status ' +
                    'type {name} provider_account {name} tenant ' +
                    '{name} termination_a {id} termination_z {id} ' +
                    'custom_fields comments}}"}'
                ), f"{worker} did not return correct query string"
                
                
    def test_get_circuits(self, nfclient):
        ret = nfclient.run_job(
            b"netbox",
            "get_circuits",
            workers="any",
            kwargs={
                "devices": ["fceos4", "fceos5"],
            },
        )
        pprint.pprint(ret, width=200)
        for worker, res in ret.items():
            assert "fceos5" in res, f"{worker} returned no results for fceos5"
            assert "fceos4" in res, f"{worker} returned no results for fceos4"
            for device, device_data in res.items():
                for cid, cid_data in device_data.items():
                    if cid=="CID3":
                        assert all(
                            k in cid_data for k in [
                                "tags",
                                "provider",
                                "commit_rate",
                                "description",
                                "status",
                                "type",
                                "provider_account",
                                "tenant",
                                "custom_fields",
                                "comments",
                                "provider_account",
                                "provider_network",
                            ]
                        ), f"{worker}:{device}:{cid} not all circuit data returned" 
                    else:
                        assert all(
                            k in cid_data for k in [
                                "tags",
                                "provider",
                                "commit_rate",
                                "description",
                                "status",
                                "type",
                                "provider_account",
                                "tenant",
                                "custom_fields",
                                "comments",
                                "remote_device",
                                "remote_interface",
                            ]
                        ), f"{worker}:{device}:{cid} not all circuit data returned" 