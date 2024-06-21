import pynetbox
import re
import logging
import requests

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(pathname)s:%(lineno)d %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)

NB_VERSION = None
NB_URL = "http://192.168.4.130:8000/"
NB_URL_SSL = "https://192.168.4.130:443/"
NB_USERNAME = "admin"
NB_PASSWORD = "admin"
NB_API_TOKEN = "0123456789abcdef0123456789abcdef01234567"
NB_SECRETS_PRIVATE_KEY = """
-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEAqlYAwxqIYx1rE3ZHfbSVKpVQXdvjkDYvFAIzApenoGZMr95u
nam1x/Zx6zPISdZt67Wy+g3W4by2TcpKArncAMA/mKUAgBDhob2pa2XUdKs/Mkhk
Dz7A9dbSmx9kMwkw/dmVq5F988ffVZWB+o8nRXkB/sbbIykeg6SFG+P9/OJfO1bb
JsBxpLAkRu1w7Gxmc62UdhQjniFwTQEEeCJhHnMsLfiBXHwJKVVbmWdTTV/fIVdi
cUYgm8fBzt17uaTqi6cNt/MFZd9EjIeKI6K06k5hNRSiIWUqhp8+LP0vwvV/TCc6
AFpbr/6jfwooNyJWyva6Q4Bni6s5xcyS6a7PQQIDAQABAoIBACGu9aIfTFKrRdoY
pO0FCY1c7wJMghzpthgTEkLEOhv0Ntx9VCr93Spgf+kGuafuTRjUOsMLew9zKarK
4qVU2x5T5g+Zq3ZnwDKjho3sGl4C4jGfkpfYLUDAHTAbPk2AVw2P2jLOB9XuE6pB
MS2a4uVwVzZqXPnAPx5BqafZB0gbKfoEjYabJRlplqLd19qYalcmmnd/qfWq8AQr
FL6acCeXiz5Su/Si0pVYG91V31rERG8K+BTYD60BpMd7uXuHlZhEmZZnELmHdYrE
AMS65kmL3w6PBHvk45CLZqJlq6Syj7zY69qqPxT31/rDWY8BDjY2GgFTCFiePM7V
e1fH77UCgYEAwx/gp4wVRRE6QUt6JiC4+pjpw0/bM1fsVVOK1Xa3kbWzpLCeq9zd
0Z3Vv4VquSawlKRlktRU2UPPJpB0bqq82zocY8LFKRwDALZEVQge8kiiBDig4ylB
ZoD0oaFIBMy5GlloPwwN1nPDCg4QrBC6lZz3FP886etWbeGroGdDYKUCgYEA33pS
fcuJDQdSHLZuoYUDQFOUBq3fMIQOvZFu21dNO/GqV4uxP1hXt6rkj4LS3UA6fqBL
mlTu8ACZpBN2GAqD1AqRi7/rt+unCbFw8OTnJQKC8/aZRE/Xub3klZs7mquab9qb
7Hz00zKu+HVUIJStQL9LQzO4KAHA8XX3v3nitW0CgYAbFOmRV5f8Jg/30An8EL6b
yW1odkTuM13R2e6DAh8oUhfE296p69W9qjJoipPtbrlDaC3Q2zeLkCXILHR8h6X+
p2oZToce1Yx1JNcHFkF1Ty9tdo6d+LPjDjLl3ASq5d8rEQ2u8nVZNmfzlVArEYdU
DJ0ehO5naQpt5cx0TuDDIQKBgQCB6Kilabj8suG/wSkkiZ7vOOaWz2Ir4Mh02GL5
7JEAJKaiB5l8uk0bfqMo7aLIbPrT+ziXuYHAUIj/wTRoG0yw6YfcFi/flYRfdR+z
WU0ozYH0cch81nEQD1wev8NxUQoQtaLoYWcskoz177Z8zhC8z7bflOQblZFki+/+
BcuNLQKBgHp3+eFXuzAvGCpA1hczjUPTlVHOpP6AXW6nmiAjC1gD/T08GT7te++N
6OnAaBM9ufB6j5h+Dj/d3IfSi183yq5UoZG5RaajluEqEiz9YVOPFgGW9rZlatIp
vbHXhXuOco78DrAGLALXh8+TLESqu4XXsJJrIHcBA8tbYN9dDuHo
-----END RSA PRIVATE KEY-----
"""

# which Netbox secrets plugin to use
NB_SECRETS_PLUGIN = "netbox_secrets"

# Import this into Netbox manually
patch_panel_import_data = """
---
manufacturer: Generic
model: 24-port LC Patch Panel
slug: 24-port-lc-patch-panel
u_height: 1
front-ports:
  - name: FrontPort1
    type: lc
    rear_port: RearPortTrunk1
    rear_port_position: 1
  - name: FrontPort2
    type: lc
    rear_port: RearPortTrunk1
    rear_port_position: 2
  - name: FrontPort3
    type: lc
    rear_port: RearPortTrunk1
    rear_port_position: 3
  - name: FrontPort4
    type: lc
    rear_port: RearPortTrunk1
    rear_port_position: 4
  - name: FrontPort5
    type: lc
    rear_port: RearPort5
  - name: FrontPort6
    type: lc
    rear_port: RearPort6
  - name: FrontPort7
    type: lc
    rear_port: RearPort7
  - name: FrontPort8
    type: lc
    rear_port: RearPort8
rear-ports:
  - name: RearPortTrunk1
    type: mpo
    positions: 4
  - name: RearPort5
    type: lc
    positions: 1
  - name: RearPort6
    type: lc
    positions: 1
  - name: RearPort7
    type: lc
    positions: 1
  - name: RearPort8
    type: lc
    positions: 1
"""


def slugify(name):
    return re.sub("\W+", "-", name.lower())


# list of netbox deice inventory keys to verify device data retrieved from Netbox
netbox_device_data_keys = [
    "airflow",
    "asset_tag",
    "config_context",
    "custom_field_data",
    "device_type",
    "last_updated",
    "location",
    "name",
    "platform",
    "position",
    "primary_ip4",
    "primary_ip6",
    "rack",
    "serial",
    "site",
    "status",
    "tags",
    "tenant",
]

netbox_tasks_device_data_keys = [
    "airflow",
    "asset_tag",
    "cluster",
    "comments",
    "config_context",
    "created",
    "custom_fields",
    "device_type",
    "display",
    "face",
    "id",
    "last_updated",
    "local_context_data",
    "location",
    "name",
    "parent_device",
    "platform",
    "position",
    "primary_ip",
    "primary_ip4",
    "primary_ip6",
    "rack",
    "serial",
    "site",
    "status",
    "tags",
    "tenant",
    "url",
    "vc_position",
    "vc_priority",
    "virtual_chassis",
]

regions = [
    {"name": "APAC"},
    {"name": "EMEA"},
]

tenants = [{"name": "SALTNORNIR"}, {"name": "NORFAB"}]

sites = [
    {
        "name": "SALTNORNIR-LAB",
        "tenant": {"name": "SALTNORNIR"},
        "region": {"name": "APAC"},
    },
    {
        "name": "SALTNORNIR-LAB2",
        "tenant": {"name": "SALTNORNIR"},
        "region": {"name": "APAC"},
    },
    {
        "name": "NORFAB-LAB",
        "tenant": {"name": "NORFAB"},
        "region": {"name": "APAC"},
    },
]

racks = [
    {
        "name": "R101",
        "site": {"name": "SALTNORNIR-LAB"},
        "tenant": {"name": "SALTNORNIR"},
    },
    {
        "name": "R201",
        "site": {"name": "SALTNORNIR-LAB"},
        "tenant": {"name": "SALTNORNIR"},
    },
    {
        "name": "R301",
        "site": {"name": "SALTNORNIR-LAB"},
        "tenant": {"name": "SALTNORNIR"},
    },
    {
        "name": "R401",
        "site": {"name": "SALTNORNIR-LAB2"},
        "tenant": {"name": "SALTNORNIR"},
    },
    {
        "name": "R123",
        "site": {"name": "NORFAB-LAB"},
        "tenant": {"name": "NORFAB"},
    },
]

manufacturers = [
    {"name": "SaltNornir"},
    {"name": "SaltStack"},
    {"name": "Arista"},
    {"name": "Cisco"},
    {"name": "Generic"},
]

tags = [
    {"name": "nrp3"},
    {"name": "ACCESS"},
    {"name": "nornir-worker-1"},
    {"name": "nornir-worker-2"},
    {"name": "NORFAB"},
]

device_types = [
    {
        "model": "Salt-Nornir-Proxy-Minion",
        "manufacturer": {"name": "SaltStack"},
    },
    {
        "model": "KeyMaster",
        "manufacturer": {"name": "SaltNornir"},
    },
    {
        "model": "Arista cEOS",
        "manufacturer": {"name": "Arista"},
    },
    {
        "model": "XVR9000",
        "manufacturer": {"name": "Cisco"},
    },
    {
        "model": "24-port LC Patch Panel",
        "manufacturer": {"name": "Generic"},
        "front-ports": [
            {
                "name": "FrontPort1",
                "type": "lc",
                "rear_port": "RearPortTrunk1",
                "rear_port_position": 1,
            },
            {
                "name": "FrontPort2",
                "type": "lc",
                "rear_port": "RearPortTrunk1",
                "rear_port_position": 2,
            },
            {
                "name": "FrontPort3",
                "type": "lc",
                "rear_port": "RearPortTrunk1",
                "rear_port_position": 3,
            },
            {
                "name": "FrontPort4",
                "type": "lc",
                "rear_port": "RearPortTrunk1",
                "rear_port_position": 4,
            },
            {"name": "FrontPort5", "type": "lc", "rear_port": "RearPort5"},
            {"name": "FrontPort6", "type": "lc", "rear_port": "RearPort6"},
            {"name": "FrontPort7", "type": "lc", "rear_port": "RearPort7"},
            {"name": "FrontPort8", "type": "lc", "rear_port": "RearPort8"},
        ],
        "rear-ports": [
            {"name": "RearPortTrunk1", "type": "mpo", "positions": 4},
            {"name": "RearPort5", "type": "lc", "positions": 1},
            {"name": "RearPort6", "type": "lc", "positions": 1},
            {"name": "RearPort7", "type": "lc", "positions": 1},
            {"name": "RearPort8", "type": "lc", "positions": 1},
        ],
    },
]

device_roles = [
    {"name": "VirtualRouter", "color": "00ff00"},  # green
    {"name": "KeyMaster", "color": "ff0000"},  # red
    {"name": "ProxyMinion", "color": "0000ff"},  # blue
    {"name": "PatchPanel", "color": "0000fa"},
]

platforms = [
    {
        "name": "arista_eos",
        "manufacturer": {"name": "Arista"},
    },
    {
        "name": "cisco_xr",
    },
]

ip_addresses = [
    {"address": "1.0.1.4/32"},
    {"address": "1.0.1.5/32"},
    {"address": "1.0.100.1/32"},
    {"address": "10.0.0.1/30"},
    {"address": "10.0.0.2/30"},
    {"address": "10.0.1.1/30"},
    {"address": "10.0.1.2/30"},
]
# add more ip addresses
ip_addresses.extend([{"address": f"1.0.10.{i}/32"} for i in range(1, 11)])

vlans = [{"name": f"VLAN_{i}", "vid": 100 + i} for i in range(1, 6)]

interfaces = [
    {"name": "loopback0", "device": {"name": "fceos4"}, "type": "virtual"},
    {"name": "loopback0", "device": {"name": "fceos5"}, "type": "virtual"},
    {
        "name": "Port-Channel1",
        "device": {"name": "fceos4"},
        "type": "lag",
        "description": "Main uplink interface",
    },
    {
        "name": "eth101",
        "device": {"name": "fceos4"},
        "type": "1000base-t",
        "mtu": 1500,
        "mode": "tagged",
        "lag": {"name": "Port-Channel1"},
    },
    {
        "name": "eth102",
        "device": {"name": "fceos4"},
        "type": "1000base-t",
        "mtu": 1500,
        "mode": "tagged",
        "lag": {"name": "Port-Channel1"},
    },
    {
        "name": "eth201",
        "device": {"name": "fceos4"},
        "type": "1000base-t",
        "mode": "tagged",
        "tagged_vlans": [102, 103, 104, 105],
        "untagged_vlan": 101,
    },
    {"name": "loopback0", "device": {"name": "ceos1"}, "type": "virtual"},
    {"name": "eth11", "device": {"name": "fceos4"}, "type": "10gbase-x-sfpp"},
    {
        "name": "eth11.123",
        "device": {"name": "fceos4"},
        "type": "virtual",
        "parent": {"name": "eth11"},
    },
    {"name": "eth11", "device": {"name": "fceos5"}, "type": "10gbase-x-sfpp"},
    {
        "name": "eth11.123",
        "device": {"name": "fceos5"},
        "type": "virtual",
        "parent": {"name": "eth11"},
    },
    {"name": "eth30", "device": {"name": "fceos4"}, "type": "10gbase-x-sfpp"},
]

# add Containerlab devices interfaces
interfaces.extend(
    [
        {
            "name": intf,
            "device": {"name": host},
            "type": "virtual",
        }
        for intf in ["Management0", "Ethernet1", "Ethernet2", "Ethernet3", "Ethernet4"]
        for host in ["ceos-spine-1", "ceos-spine-2"]
    ]
)


# add more interfaces
interfaces.extend(
    [
        {
            "name": f"eth{i}",
            "device": {"name": "fceos4"},
            "type": "1000base-t",
            "mtu": 1500,
            "mode": "tagged",
            "description": f"Interface {i} description",
        }
        for i in range(1, 11)
    ]
)
interfaces.extend(
    [
        {
            "name": f"eth{i}",
            "device": {"name": "fceos5"},
            "type": "1000base-t",
            "mtu": 1500,
            "mode": "tagged",
            "description": f"Interface {i} description",
        }
        for i in range(1, 11)
    ]
)
# add sub-interfaces
interfaces.extend(
    [
        {
            "name": f"eth{i}.1{i}",
            "device": {"name": "fceos4"},
            "type": "virtual",
            "mtu": 1500,
            "mode": "tagged",
            "parent": {"name": f"eth{i}"},
            "description": f"Sub-Interface {i} description",
        }
        for i in range(1, 11)
    ]
)

power_outlet_ports = [
    {"name": "PowerOutlet-1", "device": {"name": "fceos4"}, "type": "iec-60320-c5"},
    {"name": "PowerOutlet-2", "device": {"name": "fceos4"}, "type": "iec-60320-c5"},
]

power_ports = [
    {"name": "PowerPort-1", "device": {"name": "fceos5"}, "type": "iec-60320-c6"},
    {"name": "PowerPort-2", "device": {"name": "fceos5"}, "type": "iec-60320-c6"},
]

inventory_items_roles = [
    {"name": "Transceiver", "slug": "transceiver", "color": "ff0000"}
]

inventory_items = [
    {
        "name": "SFP-1G-T",
        "device": {"name": "fceos4"},
        "manufacturer": {"name": "Cisco"},
        "role": {"slug": "transceiver"},
        "component_type": "dcim.interface",
        "component": {"name": "eth1"},
    },
    {
        "name": "SFP-1G-T",
        "device": {"name": "fceos4"},
        "manufacturer": {"name": "Cisco"},
        "role": {"slug": "transceiver"},
        "component_type": "dcim.interface",
        "component": {"name": "eth3"},
    },
]

# add Containerlab devices interfaces inventory items
inventory_items.extend(
    [
        {
            "name": "SFP-1G-T",
            "device": {"name": host},
            "manufacturer": {"name": "Cisco"},
            "role": {"slug": "transceiver"},
            "component_type": "dcim.interface",
            "component": {"name": intf},
        }
        for intf in ["Ethernet1", "Ethernet2"]
        for host in ["ceos-spine-1", "ceos-spine-2"]
    ]
)

console_server_ports = [
    {"name": "ConsoleServerPort1", "device": {"name": "fceos5"}},
    {"name": "ConsoleServerPort2", "device": {"name": "fceos5"}},
]

console_ports = [
    {"name": "ConsolePort1", "device": {"name": "fceos4"}},
    {"name": "ConsolePort2", "device": {"name": "fceos4"}},
]

vrfs = [
    {"name": "MGMT"},
    {"name": "CUST1-Flinch34"},
    {"name": "OOB_CTRL"},
    {"name": "Signalling"},
    {"name": "Voice"},
]

ip_adress_to_devices = [
    {
        "address": "1.0.1.4/32",
        "interface": "loopback0",
        "device": "fceos4",
        "role": "loopback",
        "primary_device_ip": True,
    },
    {
        "address": "1.0.1.5/32",
        "interface": "loopback0",
        "device": "fceos5",
        "role": "loopback",
        "primary_device_ip": True,
    },
    {
        "address": "1.0.100.1/32",
        "interface": "eth1.11",
        "device": "fceos4",
        "vrf": {"name": vrfs[1]["name"]},
    },
    {
        "address": "10.0.0.1/30",
        "interface": "eth11.123",
        "device": "fceos4",
        "vrf": {"name": "MGMT"},
    },
    {
        "address": "10.0.0.2/30",
        "interface": "eth11.123",
        "device": "fceos5",
        "vrf": {"name": "MGMT"},
    },
    {
        "address": "10.0.1.1/30",
        "interface": "eth11",
        "device": "fceos4",
        "vrf": {"name": "OOB_CTRL"},
    },
    {
        "address": "10.0.1.2/30",
        "interface": "eth11",
        "device": "fceos5",
        "vrf": {"name": "OOB_CTRL"},
    },
]
# associate IP addresses to subinterfaces
ip_adress_to_devices.extend(
    [
        {
            "address": f"1.0.10.{i}/32",
            "interface": f"eth{i}.1{i}",
            "device": "fceos4",
            "vrf": {"name": vrfs[min(i, 4)]["name"]},
        }
        for i in range(1, 11)
    ]
)

# create interface connections
# supported teminaton types - "dcim.consoleport", "dcim.interface", "dcim.consoleserverport" etc.
connections = [
    # breakout cables
    {
        "type": "cat6a",
        "a_terminations": [
            {
                "device": "fceos4",
                "interface": f"eth1",
                "termination_type": "dcim.interface",
            },
            {
                "device": "fceos4",
                "interface": f"eth10",
                "termination_type": "dcim.interface",
            },
        ],
        "b_terminations": [
            {
                "device": "fceos5",
                "interface": f"eth1",
                "termination_type": "dcim.interface",
            },
            {
                "device": "fceos5",
                "interface": f"eth10",
                "termination_type": "dcim.interface",
            },
        ],
        "status": "connected",
        "tenant": {"slug": "saltnornir"},
    },
    {
        "type": "cat6a",
        "a_terminations": [
            {
                "device": "fceos4",
                "interface": f"eth2",
                "termination_type": "dcim.interface",
            },
        ],
        "b_terminations": [
            {
                "device": "fceos5",
                "interface": f"eth9",
                "termination_type": "dcim.interface",
            },
            {
                "device": "fceos5",
                "interface": f"eth2",
                "termination_type": "dcim.interface",
            },
        ],
        "status": "connected",
        "tenant": {"slug": "saltnornir"},
    },
    {
        "type": "cat6a",
        "a_terminations": [
            {
                "device": "fceos4",
                "interface": f"eth8",
                "termination_type": "dcim.interface",
            },
            {
                "device": "fceos4",
                "interface": f"eth9",
                "termination_type": "dcim.interface",
            },
            {
                "device": "fceos4",
                "interface": f"eth3",
                "termination_type": "dcim.interface",
            },
        ],
        "b_terminations": [
            {
                "device": "fceos5",
                "interface": f"eth3",
                "termination_type": "dcim.interface",
            }
        ],
        "status": "connected",
        "tenant": {"slug": "saltnornir"},
    },
    # point to point interface connections
    {
        "type": "cat6a",
        "a_terminations": [
            {
                "device": "fceos4",
                "interface": f"eth4",
                "termination_type": "dcim.interface",
            },
        ],
        "b_terminations": [
            {
                "device": "fceos5",
                "interface": f"eth4",
                "termination_type": "dcim.interface",
            }
        ],
        "status": "connected",
        "tenant": {"slug": "saltnornir"},
    },
    {
        "type": "cat6a",
        "a_terminations": [
            {
                "device": "fceos4",
                "interface": f"eth6",
                "termination_type": "dcim.interface",
            },
        ],
        "b_terminations": [
            {
                "device": "fceos5",
                "interface": f"eth6",
                "termination_type": "dcim.interface",
            }
        ],
        "status": "connected",
        "tenant": {"slug": "saltnornir"},
    },
    # patch panel connections
    {
        "type": "smf",
        "a_terminations": [
            {
                "device": "PatchPanel-1",
                "interface": "RearPortTrunk1",
                "termination_type": "dcim.rearport",
            },
        ],
        "b_terminations": [
            {
                "device": "PatchPanel-2",
                "interface": "RearPortTrunk1",
                "termination_type": "dcim.rearport",
            }
        ],
        "status": "planned",
        "tenant": {"slug": "saltnornir"},
    },
    {
        "type": "smf",
        "a_terminations": [
            {
                "device": "fceos4",
                "interface": "eth7",
                "termination_type": "dcim.interface",
            },
        ],
        "b_terminations": [
            {
                "device": "PatchPanel-1",
                "interface": "FrontPort1",
                "termination_type": "dcim.frontport",
            }
        ],
        "status": "connected",
        "tenant": {"slug": "saltnornir"},
    },
    {
        "type": "smf",
        "a_terminations": [
            {
                "device": "fceos5",
                "interface": "eth7",
                "termination_type": "dcim.interface",
            },
        ],
        "b_terminations": [
            {
                "device": "PatchPanel-2",
                "interface": "FrontPort1",
                "termination_type": "dcim.frontport",
            }
        ],
        "status": "connected",
        "tenant": {"slug": "saltnornir"},
    },
    {
        "type": "smf",
        "a_terminations": [
            {
                "device": "fceos4",
                "interface": "eth30",
                "termination_type": "dcim.interface",
            },
        ],
        "b_terminations": [
            {
                "device": "PatchPanel-1",
                "interface": "FrontPort8",
                "termination_type": "dcim.frontport",
            }
        ],
        "status": "connected",
        "tenant": {"slug": "saltnornir"},
    },
    # console connections
    {
        "type": "cat6a",
        "a_terminations": [
            {
                "device": "fceos4",
                "interface": "ConsolePort1",
                "termination_type": "dcim.consoleport",
            }
        ],
        "b_terminations": [
            {
                "device": "fceos5",
                "interface": "ConsoleServerPort1",
                "termination_type": "dcim.consoleserverport",
            }
        ],
        "status": "connected",
        "tenant": {"slug": "saltnornir"},
    },
    {
        "type": "cat6a",
        "a_terminations": [
            {
                "device": "fceos4",
                "interface": "ConsolePort2",
                "termination_type": "dcim.consoleport",
            }
        ],
        "b_terminations": [
            {
                "device": "fceos5",
                "interface": "ConsoleServerPort2",
                "termination_type": "dcim.consoleserverport",
            }
        ],
        "status": "connected",
        "tenant": {"slug": "saltnornir"},
    },
    # power connections
    {
        "type": "power",
        "a_terminations": [
            {
                "device": "fceos4",
                "interface": "PowerOutlet-1",
                "termination_type": "dcim.poweroutlet",
            }
        ],
        "b_terminations": [
            {
                "device": "fceos5",
                "interface": "PowerPort-1",
                "termination_type": "dcim.powerport",
            }
        ],
        "status": "connected",
        "tenant": {"slug": "saltnornir"},
    },
    {
        "type": "power",
        "a_terminations": [
            {
                "device": "fceos4",
                "interface": "PowerOutlet-2",
                "termination_type": "dcim.poweroutlet",
            }
        ],
        "b_terminations": [
            {
                "device": "fceos5",
                "interface": "PowerPort-2",
                "termination_type": "dcim.powerport",
            }
        ],
        "status": "connected",
        "tenant": {"slug": "saltnornir"},
    },
    # circuit cables
    {
        "type": "smf",
        "a_terminations": [
            {
                "device": "PatchPanel-1",
                "interface": "FrontPort6",
                "termination_type": "dcim.frontport",
            },
        ],
        "b_terminations": [
            {
                "device": "fceos4",
                "interface": "eth11",
                "termination_type": "dcim.interface",
            }
        ],
        "status": "connected",
    },
    {
        "type": "smf",
        "a_terminations": [
            {
                "device": "PatchPanel-3",
                "interface": "FrontPort6",
                "termination_type": "dcim.frontport",
            },
        ],
        "b_terminations": [
            {
                "device": "fceos5",
                "interface": "eth11",
                "termination_type": "dcim.interface",
            }
        ],
        "status": "connected",
    },
]

devices = [
    {
        "name": "fceos4",
        "device_type": {"slug": slugify("Arista cEOS")},
        "device_role": {"name": "VirtualRouter"},
        "tenant": {"name": "SALTNORNIR"},
        "site": {"name": "SALTNORNIR-LAB"},
        "rack": {"name": "R101"},
        "position": 40,
        "face": "front",
        "serial": "FNS123451",
        "asset_tag": "UUID-123451",
        "tags": [{"name": "nrp3"}],
        "platform": {"name": "arista_eos"},
        "local_context_data": {
            "domain_name": "lab.io",
            "lo0_ip": "1.0.1.4",
            "syslog_servers": ["10.0.0.3", "10.0.0.4"],
            "secrets": {
                "bgp": f"nb://{NB_SECRETS_PLUGIN}/keymaster-1/BGP/peers_pass",
                "secret1": f"nb://{NB_SECRETS_PLUGIN}/fceos4/SaltSecrets/secret1",
                "secret2": f"nb://{NB_SECRETS_PLUGIN}/SaltSecrets/secret2",
                "secret3": f"nb://{NB_SECRETS_PLUGIN}/secret3",
                "secret4": "nb://secret4",
            },
        },
    },
    {
        "name": "fceos5",
        "device_type": {"slug": slugify("Arista cEOS")},
        "device_role": {"name": "VirtualRouter"},
        "tenant": {"name": "SALTNORNIR"},
        "site": {"name": "SALTNORNIR-LAB"},
        "rack": {"name": "R201"},
        "position": 40,
        "face": "front",
        "platform": {"name": "arista_eos"},
        "local_context_data": {
            "nornir": {
                "platform": "arista_eos",
                "hostname": "10.0.1.10",
                "port": "6002",
                "username": f"nb://{NB_SECRETS_PLUGIN}/keymaster-1/SaltNornirCreds/username",
                "password": f"nb://{NB_SECRETS_PLUGIN}/keymaster-1/SaltNornirCreds/password",
            }
        },
    },
    {
        "name": "keymaster-1",
        "device_type": {"slug": slugify("KeyMaster")},
        "device_role": {"name": "KeyMaster"},
        "tenant": {"name": "SALTNORNIR"},
        "site": {"name": "SALTNORNIR-LAB"},
    },
    {
        "name": "nrp3",
        "device_type": {"slug": slugify("Salt-Nornir-Proxy-Minion")},
        "device_role": {"name": "ProxyMinion"},
        "tenant": {"name": "SALTNORNIR"},
        "site": {"name": "SALTNORNIR-LAB"},
        "local_context_data": {
            "proxy": {"proxy_always_alive": True},
            "hosts": {
                "fceos6": {
                    "hostname": "1.2.3.4",
                    "platform": "arista_eos",
                    "port": "22",
                    "username": f"nb://{NB_SECRETS_PLUGIN}/keymaster-1/SaltNornirCreds/username",
                    "password": f"nb://{NB_SECRETS_PLUGIN}/keymaster-1/SaltNornirCreds/password",
                    "data": {
                        "secrets": [
                            {
                                "bgp": f"nb://{NB_SECRETS_PLUGIN}/keymaster-1/BGP/peers_pass"
                            },
                            {
                                "snmp": f"nb://{NB_SECRETS_PLUGIN}/keymaster-1/SNMP/community"
                            },
                            f"nb://{NB_SECRETS_PLUGIN}/keymaster-1/OSPF/hello_secret",
                        ]
                    },
                },
                "fceos7": {
                    "hostname": "1.2.3.5",
                    "platform": "arista_eos",
                    "port": "22",
                    "username": "nornir",
                    "password": "nornir",
                    "data": {
                        "bgp": {
                            "peers": [
                                {
                                    "bgp_peer_secret": f"nb://{NB_SECRETS_PLUGIN}/keymaster-1/BGP_PEERS/10.0.1.1"
                                },
                                {
                                    "bgp_peer_secret": f"nb://{NB_SECRETS_PLUGIN}/keymaster-1/BGP_PEERS/10.0.1.2"
                                },
                                {
                                    "bgp_peer_secret": f"nb://{NB_SECRETS_PLUGIN}/keymaster-1/BGP_PEERS/10.0.1.3"
                                },
                            ]
                        }
                    },
                },
                "fceos8": {},
            },
            "foo": "bar",
            "nrp3_foobar_key": "nb://nrp3_foobar_key_secret",
            "nornir": {
                "actions": {
                    "foobar": {
                        "function": "nr.cli",
                        "args": ["show clock"],
                        "description": "test action",
                    }
                }
            },
        },
    },
    {
        "name": "ceos1",
        "device_type": {"slug": slugify("Arista cEOS")},
        "device_role": {"name": "VirtualRouter"},
        "tenant": {"name": "SALTNORNIR"},
        "site": {"name": "SALTNORNIR-LAB"},
        "rack": {"name": "R201"},
        "position": 41,
        "face": "front",
        "platform": {"name": "arista_eos"},
        "local_context_data": {
            "secrets_test": {"OSPF_KEY": f"nb://{NB_SECRETS_PLUGIN}/OSPF/hello_secret"},
            "nornir": {
                "hostname": "10.0.1.4",
            },
            "dns_servers": ["1.2.3.4", "8.8.8.8"],
        },
    },
    {
        "name": "fceos8",
        "device_type": {"slug": slugify("Arista cEOS")},
        "device_role": {"name": "VirtualRouter"},
        "tenant": {"name": "SALTNORNIR"},
        "site": {"name": "SALTNORNIR-LAB"},
        "rack": {"name": "R201"},
        "position": 8,
        "face": "front",
        "platform": {"name": "arista_eos"},
        "local_context_data": {
            "nornir": {
                "platform": "arista_eos",
                "hostname": "10.0.1.10",
                "port": "6008",
                "username": f"nb://{NB_SECRETS_PLUGIN}/keymaster-1/SaltNornirCreds/username",
                "password": f"nb://{NB_SECRETS_PLUGIN}/keymaster-1/SaltNornirCreds/password",
            }
        },
    },
    {
        "name": "iosxr1",
        "device_type": {"slug": slugify("XVR9000")},
        "device_role": {"name": "VirtualRouter"},
        "tenant": {"name": "SALTNORNIR"},
        "site": {"name": "SALTNORNIR-LAB"},
        "rack": {"name": "R201"},
        "position": 31,
        "face": "front",
        "local_context_data": {
            "nornir": {"platform": "cisco_xr", "hostname": "sandbox-iosxr-1.cisco.com"}
        },
    },
    {
        "name": "PatchPanel-1",
        "device_type": {"slug": slugify("24-port-lc-patch-panel")},
        "device_role": {"name": "PatchPanel"},
        "tenant": {"name": "SALTNORNIR"},
        "site": {"name": "SALTNORNIR-LAB"},
        "rack": {"name": "R101"},
        "position": 41,
        "face": "front",
    },
    {
        "name": "PatchPanel-2",
        "device_type": {"slug": slugify("24-port-lc-patch-panel")},
        "device_role": {"name": "PatchPanel"},
        "tenant": {"name": "SALTNORNIR"},
        "site": {"name": "SALTNORNIR-LAB"},
        "rack": {"name": "R201"},
        "position": 42,
        "face": "front",
    },
    {
        "name": "PatchPanel-3",
        "device_type": {"slug": slugify("24-port-lc-patch-panel")},
        "device_role": {"name": "PatchPanel"},
        "tenant": {"name": "SALTNORNIR"},
        "site": {"name": "SALTNORNIR-LAB2"},
        "rack": {"name": "R401"},
        "position": 41,
        "face": "front",
    },
    {
        "name": "ceos-spine-1",
        "device_type": {"slug": slugify("Arista cEOS")},
        "device_role": {"name": "VirtualRouter"},
        "tenant": {"name": "NORFAB"},
        "site": {"name": "NORFAB-LAB"},
        "rack": {"name": "R123"},
        "position": 40,
        "face": "front",
        "serial": "FNS12345678",
        "asset_tag": "UUID-FNS12345678",
        "tags": [{"name": "nornir-worker-1"}, {"name": "NORFAB"}],
        "platform": {"name": "arista_eos"},
        "local_context_data": {
            "domain_name": "norfablab.io",
            "nornir": {"hostname": "192.168.4.130", "port": 2200},
        },
    },
    {
        "name": "ceos-spine-2",
        "device_type": {"slug": slugify("Arista cEOS")},
        "device_role": {"name": "VirtualRouter"},
        "tenant": {"name": "NORFAB"},
        "site": {"name": "NORFAB-LAB"},
        "rack": {"name": "R123"},
        "position": 41,
        "face": "front",
        "serial": "FNS123456789",
        "asset_tag": "UUID-FNS123456789",
        "tags": [{"name": "nornir-worker-1"}, {"name": "NORFAB"}],
        "platform": {"name": "arista_eos"},
        "local_context_data": {
            "domain_name": "norfablab.io",
            "nornir": {"hostname": "192.168.4.130", "port": 2201},
        },
    },
]
# add fceos3_390-fceos3_399 devices to test multi-threading retrieval
for i in range(10):
    devices.append(
        {
            "name": f"fceos3_39{i}",
            "device_type": {"slug": slugify("Arista cEOS")},
            "device_role": {"name": "VirtualRouter"},
            "tenant": {"name": "SALTNORNIR"},
            "site": {"name": "SALTNORNIR-LAB"},
            "rack": {"name": "R201"},
            "face": "front",
            "platform": {"name": "arista_eos"},
            "tags": [{"name": "nrp3"}],
            "local_context_data": {
                "nornir": {
                    "platform": "arista_eos",
                    "hostname": "10.0.1.10",
                    "port": str(5390 + 1),
                    "password": "nornir",
                    "username": "nornir",
                    "data": {
                        "secrets": [
                            {
                                "bgp": f"nb://{NB_SECRETS_PLUGIN}/keymaster-1/BGP/peers_pass"
                            },
                            {
                                "snmp": f"nb://{NB_SECRETS_PLUGIN}/keymaster-1/SNMP/community"
                            },
                        ]
                    },
                }
            },
        }
    )


netbox_secrets_roles = [
    {"name": "SaltNornirCreds"},
    {"name": "SaltSecrets"},
    {"name": "BGP"},
    {"name": "SNMP"},
    {"name": "ISIS"},
    {"name": "OSPF"},
    {"name": "SSH"},
    {"name": "Credentials"},
    {"name": "BGP_PEERS"},
]

netbox_secrets_secrets = [
    {
        "name": "secret1",
        "role": {"name": "SaltSecrets"},
        "device": "fceos4",
        "plaintext": "secret1_value",
    },
    {
        "name": "secret2",
        "role": {"name": "SaltSecrets"},
        "device": "fceos4",
        "plaintext": "secret2_value",
    },
    {
        "name": "secret3",
        "role": {"name": "SaltSecrets"},
        "device": "fceos4",
        "plaintext": "secret3_value",
    },
    {
        "name": "secret4",
        "role": {"name": "SaltSecrets"},
        "device": "fceos4",
        "plaintext": "secret4_value",
    },
    {
        "name": "nrp3_foobar_key_secret",
        "role": {"name": "SaltSecrets"},
        "device": "nrp3",
        "plaintext": "nrp3_foobar_key_value",
    },
    {
        "name": "username",
        "role": {"name": "SaltNornirCreds"},
        "device": "keymaster-1",
        "plaintext": "nornir",
    },
    {
        "name": "password",
        "role": {"name": "SaltNornirCreds"},
        "device": "keymaster-1",
        "plaintext": "nornir",
    },
    {
        "name": "username",
        "role": {"name": "SaltNornirCreds"},
        "device": "fceos4",
        "plaintext": "nornir",
    },
    {
        "name": "password",
        "role": {"name": "SaltNornirCreds"},
        "device": "fceos4",
        "plaintext": "nornir",
    },
    {
        "name": "peers_pass",
        "role": {"name": "BGP"},
        "device": "keymaster-1",
        "plaintext": "123456bgppeer",
    },
    {
        "name": "community",
        "role": {"name": "SNMP"},
        "device": "keymaster-1",
        "plaintext": "qwerty123456",
    },
    {
        "name": "admin_user",
        "role": {"name": "Credentials"},
        "device": "keymaster-1",
        "plaintext": "Nornir123",
    },
    {
        "name": "10.0.1.1",
        "role": {"name": "BGP_PEERS"},
        "device": "keymaster-1",
        "plaintext": "BGPSecret1",
    },
    {
        "name": "10.0.1.2",
        "role": {"name": "BGP_PEERS"},
        "device": "keymaster-1",
        "plaintext": "BGPSecret2",
    },
    {
        "name": "10.0.1.3",
        "role": {"name": "BGP_PEERS"},
        "device": "keymaster-1",
        "plaintext": "BGPSecret3",
    },
    {
        "name": "hello_secret",
        "role": {"name": "OSPF"},
        "device": "keymaster-1",
        "plaintext": "q1w2e3r45t5y",
    },
]

circuit_providers = [{"name": "Provider1"}]

circuit_provider_networks = [
    {"name": "Provider1-Net1", "provider": {"name": "Provider1"}}
]

provider_accounts = [
    {"provider": {"slug": slugify("Provider1")}, "account": "test_account"}
]

circuit_types = [{"name": "DarkFibre"}]

circuits = [
    {
        "provider": {"slug": slugify("Provider1")},
        "type": {"slug": slugify("DarkFibre")},
        "status": "active",
        "cid": "CID1",
        "termination_a": {
            "device": "fceos4",
            "interface": "eth101",
            "termination_type": "dcim.interface",
            "cable": {"type": "smf"},
            "site": "SALTNORNIR-LAB",
        },
        "termination_b": {
            "device": "fceos5",
            "interface": "eth8",
            "termination_type": "dcim.interface",
            "cable": {"type": "smf"},
            "site": "SALTNORNIR-LAB",
        },
        "provider_account": {"account": "test_account"},
    },
    {
        "provider": {"slug": slugify("Provider1")},
        "type": {"slug": slugify("DarkFibre")},
        "status": "active",
        "cid": "CID2",
        "termination_a": {
            "device": "PatchPanel-1",
            "interface": "RearPort6",
            "termination_type": "dcim.rearport",
            "cable": {"type": "smf"},
            "site": "SALTNORNIR-LAB",
        },
        "termination_b": {
            "device": "PatchPanel-3",
            "interface": "RearPort6",
            "termination_type": "dcim.rearport",
            "cable": {"type": "smf"},
            "site": "SALTNORNIR-LAB2",
        },
        "provider_account": {"account": "test_account"},
        "tags": [{"name": "ACCESS"}],
        "description": "some description",
        "comments": "some comments",
        "commit_rate": 10000,
    },
    {
        "provider": {"slug": slugify("Provider1")},
        "type": {"slug": slugify("DarkFibre")},
        "status": "active",
        "cid": "CID3",
        "termination_a": {
            "device": "fceos4",
            "interface": "eth201",
            "termination_type": "dcim.interface",
            "cable": {"type": "smf"},
            "site": "SALTNORNIR-LAB",
        },
        "termination_b": {"provider_network": "Provider1-Net1"},
        "provider_account": {"account": "test_account"},
        "tags": [{"name": "ACCESS"}],
    },
    {
        "provider": {"slug": slugify("Provider1")},
        "type": {"slug": slugify("DarkFibre")},
        "status": "planned",
        "cid": "CID4",
        "termination_a": {
            "device": "fceos4",
            "interface": "eth5",
            "termination_type": "dcim.interface",
            "cable": {"type": "smf"},
            "site": "SALTNORNIR-LAB",
        },
        "termination_b": None,
        "provider_account": {"account": "test_account"},
    },
]

config_templates = [
    {
        "name": "Arista cEOS Configuration",
        "template_code": """
{% for server in dns_servers -%}
ip name-server {{ server }}
{% endfor %}        
        """,
        "associated_devices": ["ceos1"],
    }
]


def _netbox_secrets_get_session_key():
    """
    Function to retrieve netbox_secrets session key
    """
    url = NB_URL + "/api/plugins/secrets/get-session-key/"
    token = "Token " + NB_API_TOKEN
    # send request to netbox
    req = requests.post(
        url,
        headers={"authorization": token},
        json={
            "private_key": NB_SECRETS_PRIVATE_KEY.strip(),
            "preserve_key": True,
        },
    )
    if req.status_code == 200:
        log.info("netbox_data obtained netbox-secrets session key")
        return req.json()["session_key"]
    else:
        raise RuntimeError(
            f"netbox_data failed to get netbox_secrets session-key, "
            f"status-code '{req.status_code}', reason '{req.reason}', response "
            f"content '{req.text}'"
        )


def create_regions():
    log.info("creating regions")
    for region in regions:
        region.setdefault("slug", slugify(region["name"]))
        try:
            nb.dcim.regions.create(**region)
        except Exception as e:
            log.error(f"creating region '{region}' error '{e}'")


def ceate_tenants():
    log.info("creating tenants")
    for tenant in tenants:
        tenant.setdefault("slug", slugify(tenant["name"]))
        try:
            nb.tenancy.tenants.create(**tenant)
        except Exception as e:
            log.error(f"creating tenant '{tenant}' error '{e}'")


def create_sites():
    log.info("creating sites")
    for site in sites:
        site.setdefault("slug", slugify(site["name"]))
        try:
            nb.dcim.sites.create(**site)
        except Exception as e:
            log.error(f"creating site '{site}' error '{e}'")


def create_racks():
    log.info("creating racks")
    for rack in racks:
        rack.setdefault("slug", slugify(rack["name"]))
        try:
            nb.dcim.racks.create(**rack)
        except Exception as e:
            log.error(f"creating rack '{rack}' error '{e}'")


def create_manufacturers():
    log.info("creating manufacturers")
    for manufacturer in manufacturers:
        manufacturer.setdefault("slug", slugify(manufacturer["name"]))
        try:
            nb.dcim.manufacturers.create(**manufacturer)
        except Exception as e:
            log.error(f"creating manufacturer '{manufacturer}' error '{e}'")


def create_tags():
    log.info("creating tags")
    for tag in tags:
        tag.setdefault("slug", slugify(tag["name"]))
        try:
            nb.extras.tags.create(**tag)
        except Exception as e:
            log.error(f"creating tag '{tag}' error '{e}'")


def create_platforms():
    log.info("creating platforms")
    for platform in platforms:
        platform.setdefault("slug", slugify(platform["name"]))
        try:
            nb.dcim.platforms.create(**platform)
        except Exception as e:
            log.error(f"creating platform '{platform}' error '{e}'")


def create_device_types():
    log.info("creating device types")
    for device_type in device_types:
        device_type.setdefault("slug", slugify(device_type["model"]))
        front_ports = device_type.pop("front-ports", [])
        rear_ports = device_type.pop("rear-ports", [])
        try:
            device_type = nb.dcim.device_types.create(**device_type)
            # add rear ports
            for rear_port in rear_ports:
                nb.dcim.rear_port_templates.create(
                    **rear_port, device_type=device_type.id
                )
            # add rear ports
            for front_port in front_ports:
                rear_port = nb.dcim.rear_port_templates.get(
                    devicetype_id=device_type.id, name=front_port.pop("rear_port")
                )
                nb.dcim.front_port_templates.create(
                    **front_port, device_type=device_type.id, rear_port=rear_port.id
                )
        except Exception as e:
            log.error(f"creating device type '{device_type}' error '{e}'")


def create_device_roles():
    log.info("creating device roles")
    for device_role in device_roles:
        device_role.setdefault("slug", slugify(device_role["name"]))
        try:
            nb.dcim.device_roles.create(**device_role)
        except Exception as e:
            log.error(f"creating device role '{device_role}' error '{e}'")


def create_ip_addresses():
    log.info("creating ip addresses")
    for ip_address in ip_addresses:
        try:
            nb.ipam.ip_addresses.create(**ip_address)
        except Exception as e:
            log.error(f"creating ip address '{ip_address}' error '{e}'")


def create_vrfs():
    log.info("creating vrfs")
    for vrf in vrfs:
        try:
            nb.ipam.vrfs.create(**vrf)
        except Exception as e:
            log.error(f"creating vrf '{vrf}' error '{e}'")


def create_vlans():
    log.info("creating vlans")
    for vlan in vlans:
        try:
            nb.ipam.vlans.create(**vlan)
        except Exception as e:
            log.error(f"creating vlan '{vlan}' error '{e}'")


def create_interfaces():
    log.info("creating interfaces")
    # create parent interfaces
    for interface in interfaces:
        # skip child interfaces
        if "parent" in interface:
            continue
        try:
            if "tagged_vlans" in interface:
                for index, vid in enumerate(interface["tagged_vlans"]):
                    nb_vlan = nb.ipam.vlans.get(vid=str(vid))
                    interface["tagged_vlans"][index] = nb_vlan.id
            if "untagged_vlan" in interface:
                nb_vlan = nb.ipam.vlans.get(vid=str(interface["untagged_vlan"]))
                interface["untagged_vlan"] = nb_vlan.id
            nb.dcim.interfaces.create(**interface)
        except Exception as e:
            log.error(f"creating interface '{interface}' error '{e}'")
    # create child interfaces
    log.info("creating child interfaces")
    for interface in interfaces:
        # skip non child interfaces
        if "parent" not in interface:
            continue
        try:
            nb_parent_intf = nb.dcim.interfaces.get(
                name=interface["parent"]["name"], device=interface["device"]["name"]
            )
            interface["parent"] = nb_parent_intf.id
            nb.dcim.interfaces.create(**interface)
        except Exception as e:
            log.error(f"creating interface '{interface}' error '{e}'")


def create_console_server_ports():
    log.info("creating console server ports")
    for port in console_server_ports:
        try:
            nb.dcim.console_server_ports.create(**port)
        except Exception as e:
            log.error(f"creating console server port '{port}' error '{e}'")


def create_console_ports():
    log.info("creating console ports")
    for port in console_ports:
        try:
            nb.dcim.console_ports.create(**port)
        except Exception as e:
            log.error(f"creating console port '{port}' error '{e}'")


def create_devices():
    log.info("creating devices")
    for device in devices:
        device.setdefault("slug", slugify(device["name"]))
        #  'device_role' field on the Device model has been renamed to 'role' starting Netbox 3.6
        if NB_VERSION >= 3.6:
            device["role"] = device.pop("device_role")
        try:
            nb.dcim.devices.create(**device)
        except Exception as e:
            log.error(f"creating device '{device}' error '{e}'")


def associate_ip_adress_to_devices():
    """Function to associate IP adresses to device intefaces and to associate vrfs to interfaces and ip adresses"""
    log.info("associating primary ip adresses to devices")
    for i in ip_adress_to_devices:
        device = nb.dcim.devices.get(name=i["device"])
        interface = nb.dcim.interfaces.get(name=i["interface"], device=i["device"])
        ip = nb.ipam.ip_addresses.get(address=i["address"])
        ip.assigned_object_id = interface.id
        ip.assigned_object_type = "dcim.interface"
        if i.get("vrf"):
            vrf = nb.ipam.vrfs.get(name=i["vrf"]["name"])
            ip.vrf = vrf.id
            interface.vrf = vrf.id
            interface.save()
        ip.save()
        if i.get("primary_device_ip"):
            device.primary_ip4 = ip.id
            device.save()


# {
#     "type": "cat6a",
#     "a_terminations": [{"device": "fceos4", "interface": f"eth{i}", "termination_type": "dcim.interface"}],
#     "b_terminations": [{"device": "fceos5", "interface": f"eth{i}", "termination_type": "dcim.interface"}],
#     "status": "active",
#     "tenant": {"slug": "saltnornir"},
# }
def create_connections():
    log.info("creatig connections")
    for connection in connections:

        a_termination_type = connection["a_terminations"][0]["termination_type"]
        if a_termination_type == "dcim.interface":
            query_endpoint = nb.dcim.interfaces
        elif a_termination_type == "dcim.consoleport":
            query_endpoint = nb.dcim.console_ports
        elif a_termination_type == "dcim.consoleserverport":
            query_endpoint = nb.dcim.console_server_ports
        elif a_termination_type == "dcim.frontport":
            query_endpoint = nb.dcim.front_ports
        elif a_termination_type == "dcim.rearport":
            query_endpoint = nb.dcim.rear_ports
        elif a_termination_type == "dcim.powerport":
            query_endpoint = nb.dcim.power_ports
        elif a_termination_type == "dcim.poweroutlet":
            query_endpoint = nb.dcim.power_outlets
        else:
            raise ValueError(f"Unsupported a_termination_type '{a_termination_type}'")
        nb_interfaces_a = [
            query_endpoint.get(
                device=tp["device"],
                name=tp["interface"],
            )
            for tp in connection["a_terminations"]
        ]

        b_termination_type = connection["b_terminations"][0]["termination_type"]
        if b_termination_type == "dcim.interface":
            query_endpoint = nb.dcim.interfaces
        elif b_termination_type == "dcim.consoleport":
            query_endpoint = nb.dcim.console_ports
        elif b_termination_type == "dcim.consoleserverport":
            query_endpoint = nb.dcim.console_server_ports
        elif b_termination_type == "dcim.frontport":
            query_endpoint = nb.dcim.front_ports
        elif b_termination_type == "dcim.rearport":
            query_endpoint = nb.dcim.rear_ports
        elif b_termination_type == "dcim.powerport":
            query_endpoint = nb.dcim.power_ports
        elif b_termination_type == "dcim.poweroutlet":
            query_endpoint = nb.dcim.power_outlets
        else:
            raise ValueError(f"Unsupported a_termination_type '{b_termination_type}'")
        nb_interfaces_b = [
            query_endpoint.get(
                device=tp["device"],
                name=tp["interface"],
            )
            for tp in connection["b_terminations"]
        ]

        connection["a_terminations"] = [
            {
                "object_type": connection["a_terminations"][0]["termination_type"],
                "object_id": nb_interface_a.id,
            }
            for nb_interface_a in nb_interfaces_a
        ]
        connection["b_terminations"] = [
            {
                "object_type": connection["b_terminations"][0]["termination_type"],
                "object_id": nb_interface_b.id,
            }
            for nb_interface_b in nb_interfaces_b
        ]

        nb.dcim.cables.create(**connection)


def create_netbox_secrets_roles():
    log.info("creating netbox_secrets secret roles")
    session_key = _netbox_secrets_get_session_key()
    url = NB_URL + "/api/plugins/secrets/secret-roles/"
    token = "Token " + NB_API_TOKEN
    for role in netbox_secrets_roles:
        role.setdefault("slug", slugify(role["name"]))
        # send request to netbox
        req = requests.post(
            url,
            headers={"X-Session-Key": session_key, "authorization": token},
            json=role,
        )
        if req.status_code != 201:
            log.error(
                f"netbox_data failed to create netbox_secrets secret role '{role}', "
                f"status-code '{req.status_code}', reason '{req.reason}', response "
                f"content '{req.text}'"
            )


def create_netbox_secrets_secrets():
    log.info("creating netbox_secrets secrets")
    session_key = _netbox_secrets_get_session_key()
    url = NB_URL + "/api/plugins/secrets/secrets/"
    token = "Token " + NB_API_TOKEN
    for secret in netbox_secrets_secrets:
        device = nb.dcim.devices.get(name=secret.pop("device"))
        secret["assigned_object_id"] = device.id
        secret["assigned_object_type"] = "dcim.device"
        # send request to netbox
        req = requests.post(
            url,
            headers={"X-Session-Key": session_key, "authorization": token},
            json=secret,
        )
        if req.status_code != 201:
            log.error(
                f"netbox_data failed to create netbox_secrets secret '{secret}', "
                f"status-code '{req.status_code}', reason '{req.reason}', response "
                f"content '{req.text}'"
            )


def create_inventory_items_roles():
    log.info("creating inventory items roles")
    for role in inventory_items_roles:
        try:
            nb.dcim.inventory_item_roles.create(**role)
        except Exception as e:
            log.error(f"creating inventory item role '{role}' error '{e}'")


def create_inventory_items():
    log.info("creating inventory items")
    for item in inventory_items:
        component = item.pop("component")
        interface = nb.dcim.interfaces.get(
            device=item["device"]["name"],
            name=component["name"],
        )
        try:
            nb.dcim.inventory_items.create(**item, component_id=interface.id)
        except Exception as e:
            log.error(f"creating inventory item '{item}' error '{e}'")


def create_circuit_providers():
    log.info("creating curcuit providerss")
    for item in circuit_providers:
        try:
            nb.circuits.providers.create(**item, slug=slugify(item["name"]))
        except Exception as e:
            log.error(f"creating circuit provider '{item}' error '{e}'")


def create_circuit_types():
    log.info("creating curcuit types")
    for item in circuit_types:
        try:
            nb.circuits.circuit_types.create(**item, slug=slugify(item["name"]))
        except Exception as e:
            log.error(f"creating circuit type '{item}' error '{e}'")


# "provider": {"slug": slugify("Provider1")},
# "type": {"slug": slugify("DarkFibre")},
# "status": "active",
# "cid": "CID1",
# "termination_a": {"device": "fceos4", "interface": "eth101", "cable": {"type": "smf"}},
# "termination_b": {"device": "fceos5", "interface": "eth8", "cable": {"type": "smf"}}
def create_circuits():
    log.info("creating curcuits")
    for item in circuits:
        try:
            termination_a = item.pop("termination_a")
            termination_b = item.pop("termination_b")
            # provider account supported starting with netbox 3.5 only
            if NB_VERSION < 3.5:
                _ = circuit.pop("provider_account")
            circuit = nb.circuits.circuits.create(**item)
            # add termination A
            if termination_a and "provider_network" in termination_a:
                cterm_a = nb.circuits.circuit_terminations.create(
                    circuit=circuit.id,
                    term_side="A",
                    provider_network={"name": termination_a["provider_network"]},
                )
            elif termination_a:
                cterm_a = nb.circuits.circuit_terminations.create(
                    circuit=circuit.id,
                    term_side="A",
                    site={"slug": slugify(termination_a["site"])},
                )
            # add termination B
            if termination_b and "provider_network" in termination_b:
                cterm_z = nb.circuits.circuit_terminations.create(
                    circuit=circuit.id,
                    term_side="Z",
                    provider_network={"name": termination_b["provider_network"]},
                )
            elif termination_b:
                cterm_z = nb.circuits.circuit_terminations.create(
                    circuit=circuit.id,
                    term_side="Z",
                    site={"slug": slugify(termination_b["site"])},
                )
            # add cable A
            if termination_a and "provider_network" not in termination_a:
                cable_a = termination_a.pop("cable", None)
                if termination_a["termination_type"] == "dcim.interface":
                    intf_a = nb.dcim.interfaces.get(
                        device=termination_a["device"], name=termination_a["interface"]
                    )
                elif termination_a["termination_type"] == "dcim.rearport":
                    intf_a = nb.dcim.rear_ports.get(
                        device=termination_a["device"], name=termination_a["interface"]
                    )
                nb.dcim.cables.create(
                    **cable_a,
                    a_terminations=[
                        {
                            "object_type": termination_a["termination_type"],
                            "object_id": intf_a.id,
                        }
                    ],
                    b_terminations=[
                        {
                            "object_type": "circuits.circuittermination",
                            "object_id": cterm_a.id,
                        }
                    ],
                )
            # add cable B
            if termination_b and "provider_network" not in termination_b:
                cable_b = termination_b.pop("cable", None)
                if termination_b["termination_type"] == "dcim.interface":
                    intf_b = nb.dcim.interfaces.get(
                        device=termination_b["device"], name=termination_b["interface"]
                    )
                elif termination_b["termination_type"] == "dcim.rearport":
                    intf_b = nb.dcim.rear_ports.get(
                        device=termination_b["device"], name=termination_b["interface"]
                    )
                nb.dcim.cables.create(
                    **cable_b,
                    a_terminations=[
                        {
                            "object_type": termination_b["termination_type"],
                            "object_id": intf_b.id,
                        }
                    ],
                    b_terminations=[
                        {
                            "object_type": "circuits.circuittermination",
                            "object_id": cterm_z.id,
                        }
                    ],
                )
        except Exception as e:
            log.exception(f"creating circuit '{item}' error '{e}'")


def create_power_outlet_ports():
    log.info("creating power outlet ports")
    for item in power_outlet_ports:
        try:
            nb.dcim.power_outlets.create(**item)
        except Exception as e:
            log.error(f"creating power outlet port '{item}' error '{e}'")


def create_power_ports():
    log.info("creating power ports")
    for item in power_ports:
        try:
            nb.dcim.power_ports.create(**item)
        except Exception as e:
            log.error(f"creating power port '{item}' error '{e}'")


def create_circuit_provider_accounts():
    log.info("creating provider accounts")
    for item in provider_accounts:
        try:
            nb.circuits.provider_accounts.create(**item)
        except Exception as e:
            log.error(f"creating provider account '{item}' error '{e}'")


def create_config_templates():
    log.info("creating config templates")
    for item in config_templates:
        associated_devices = item.pop("associated_devices")
        try:
            nb.extras.config_templates.create(**item)
        except Exception as e:
            log.error(f"creating config template '{item['name']}' error '{e}'")
        for device in associated_devices:
            try:
                nb_device = nb.dcim.devices.get(name=device)
                print(nb_device.config_template)
            except Exception as e:
                log.error(
                    f"creating config template '{item['name']}' error associating with device {'device'} '{e}'"
                )


def creat_circuit_provider_networks():
    log.info("creating circuit provider networks")
    for item in circuit_provider_networks:
        try:
            nb.circuits.provider_networks.create(**item)
        except Exception as e:
            log.error(f"creating provider network '{item}' error '{e}'")


# -----------------------------------------------------------------------------------
# DELETE functions
# -----------------------------------------------------------------------------------


def delete_netbox_secrets_secrets():
    log.info("deleting netbox_secrets secrets")
    session_key = _netbox_secrets_get_session_key()
    url = NB_URL + "api/plugins/secrets/secrets/"
    token = "Token " + NB_API_TOKEN
    req = requests.get(
        url, headers={"X-Session-Key": session_key, "authorization": token}, json={}
    )
    if req.status_code != 200:
        raise SystemExit(
            f"netbox_data failed to retrieve netbox_secrets secrets from '{url}', toke '{token}', "
            f"status-code '{req.status_code}', reason '{req.reason}', response "
            f"content '{req.text}'"
        )
    # delete secrets one by one
    for secret in req.json()["results"]:
        req = requests.delete(
            url + f"/{secret['id']}",
            headers={"X-Session-Key": session_key, "authorization": token},
            json={},
        )
        if req.status_code != 204:
            log.error(
                f"netbox_data failed to delete netbox_secrets secret '{secret}', "
                f"status-code '{req.status_code}', reason '{req.reason}', response "
                f"content '{req.text}'"
            )


def delete_netbox_secrets_roles():
    log.info("deleting netbox_secrets secret roles")
    session_key = _netbox_secrets_get_session_key()
    url = NB_URL + "/api/plugins/secrets/secret-roles/"
    token = "Token " + NB_API_TOKEN
    # get existing roles
    req = requests.get(
        url, headers={"X-Session-Key": session_key, "authorization": token}, json={}
    )
    if req.status_code != 200:
        log.error(
            f"netbox_data failed to get netbox_secrets secret roles, "
            f"status-code '{req.status_code}', reason '{req.reason}', response "
            f"content '{req.text}'"
        )
    # delete roles
    req = requests.delete(
        url,
        headers={"X-Session-Key": session_key, "authorization": token},
        json=[{"id": i["id"]} for i in req.json()["results"]],
    )
    if req.status_code != 204:
        log.error(
            f"netbox_data failed to delete netbox_secrets secret roles, "
            f"status-code '{req.status_code}', reason '{req.reason}', response "
            f"content '{req.text}'"
        )


def delete_devices():
    log.info("deleting devices")
    for device in devices:
        try:
            nb_device = nb.dcim.devices.get(name=device["name"])
            if nb_device:
                nb_device.delete()
        except Exception as e:
            log.error(f"deleting device '{device}' error '{e}'")


def delete_ip_addresses():
    log.info("deleting ip addresses")
    for ip_address in ip_addresses:
        try:
            ip = nb.ipam.ip_addresses.filter(address=ip_address["address"])
            for ip in ip:
                ip.delete()
        except Exception as e:
            log.error(f"deleting ip address '{ip_address}' error '{e}'")


def delete_vrfs():
    log.info("deleting vrfs")
    for vrf in vrfs:
        try:
            vrf_nb = nb.ipam.vrfs.filter(name=vrf["name"])
            if vrf_nb:
                for v in vrf_nb:
                    v.delete()
        except Exception as e:
            log.error(f"deleting vrf '{vrf}' error '{e}'")


def delete_vlans():
    log.info("deleting vlans")
    for vlan in vlans:
        try:
            vlan_nb = nb.ipam.vlans.filter(name=vlan["name"])
            if vlan_nb:
                for v in vlan_nb:
                    v.delete()
        except Exception as e:
            log.error(f"deleting vlan '{vlan}' error '{e}'")


def delete_device_roles():
    log.info("delete device roles")
    for device_role in device_roles:
        try:
            nb_device_role = nb.dcim.device_roles.get(name=device_role["name"])
            if nb_device_role:
                nb_device_role.delete()
        except Exception as e:
            log.error(f"deleting device role '{device_role}' error '{e}'")


def delete_device_types():
    log.info("deleting device types")
    for device_type in device_types:
        try:
            nb_device_type = nb.dcim.device_types.get(
                model=device_type["model"],
                manufacturer=slugify(device_type["manufacturer"]["name"]),
            )
            if nb_device_type:
                nb_device_type.delete()
        except Exception as e:
            log.error(f"deleting device type '{device_type}' error '{e}'")


def delete_platforms():
    log.info("deleting platforms")
    for platform in platforms:
        try:
            nb_platform = nb.dcim.platforms.get(name=platform["name"])
            if nb_platform:
                nb_platform.delete()
        except Exception as e:
            log.error(f"deleting platform '{platform}' error '{e}'")


def delete_manufacturers():
    log.info("deleting manufacturers")
    for manufacturer in manufacturers:
        try:
            nb_manufacturer = nb.dcim.manufacturers.get(name=manufacturer["name"])
            if nb_manufacturer:
                nb_manufacturer.delete()
        except Exception as e:
            log.error(f"deleting manufacturer '{manufacturer}' error '{e}'")


def delete_tags():
    log.info("deleting tags")
    for tag in tags:
        try:
            nb_tag = nb.extras.tags.get(name=tag["name"])
            if nb_tag:
                nb_tag.delete()
        except Exception as e:
            log.error(f"deleting tag '{tag}' error '{e}'")


def delete_racks():
    log.info("deleting racks")
    for rack in racks:
        try:
            nb_rack = nb.dcim.racks.filter(name=rack["name"])
            if nb_rack:
                for i in nb_rack:
                    i.delete()
        except Exception as e:
            log.error(f"deleting racks '{rack}' error '{e}'")


def delete_regions():
    log.info("deleting regions")
    for region in regions:
        try:
            nb_region = nb.dcim.regions.get(name=region["name"])
            if nb_region:
                nb_region.delete()
        except Exception as e:
            log.error(f"deleting region '{region}' error '{e}'")


def delete_tenants():
    log.info("deleting tenants")
    for tenant in tenants:
        try:
            nb_tenant = nb.tenancy.tenants.get(name=tenant["name"])
            if nb_tenant:
                nb_tenant.delete()
        except Exception as e:
            log.error(f"deleting tenant '{tenant}' error '{e}'")


def delete_connections():
    log.info("deleting all connections")
    try:
        nb_connections = nb.dcim.cables.all()
        for i in nb_connections:
            i.delete()
    except Exception as e:
        log.error(f"deleting all connections error '{e}'")


def delete_sites():
    log.info("deleting sites")
    for site in sites:
        try:
            nb_site = nb.dcim.sites.get(name=site["name"])
            if nb_site:
                nb_site.delete()
        except Exception as e:
            log.error(f"deleting site '{site}' error '{e}'")


def delete_inventory_items_roles():
    log.info("deleting inventory items roles")
    for role in inventory_items_roles:
        try:
            nb_role = nb.dcim.inventory_item_roles.get(name=role["name"])
            nb_role.delete()
        except Exception as e:
            log.error(f"deleting inventory item role '{role}' error '{e}'")


def delete_circuits():
    log.info("deleting all circuits")
    try:
        nb_circuits = nb.circuits.circuits.all()
        for i in nb_circuits:
            i.delete()
    except Exception as e:
        log.error(f"deleting all circuits error '{e}'")


def delete_circuit_providers():
    log.info("deleting all circuits providers")
    try:
        nb_circuits_providers = nb.circuits.providers.all()
        for i in nb_circuits_providers:
            i.delete()
    except Exception as e:
        log.error(f"deleting all providers error '{e}'")


def delete_circuit_types():
    log.info("deleting all circuits types")
    try:
        nb_circuits_types = nb.circuits.circuit_types.all()
        for i in nb_circuits_types:
            i.delete()
    except Exception as e:
        log.error(f"deleting all providers error '{e}'")


def delete_config_templates():
    log.info("deleting all config templates")
    try:
        templates = nb.extras.config_templates.all()
        for i in templates:
            i.delete()
    except Exception as e:
        log.error(f"deleting all config templates error '{e}'")


def delete_circuit_provider_accounts():
    log.info("deleting all circuit provider accounts")
    try:
        accounts = nb.circuits.provider_accounts.all()
        for i in accounts:
            i.delete()
    except Exception as e:
        log.error(f"deleting all circuit provider accounts error '{e}'")


def delete_circuit_provider_networks():
    log.info("deleting all circuit provider networks")
    try:
        networks = nb.circuits.provider_networks.all()
        for i in networks:
            i.delete()
    except Exception as e:
        log.error(f"deleting all circuit provider networks error '{e}'")


def clean_up_netbox():
    # delete_netbox_secrets_secrets()
    # delete_netbox_secrets_roles()
    delete_connections()
    delete_circuits()
    delete_circuit_provider_accounts()
    delete_circuit_provider_networks()
    delete_circuit_providers()
    delete_circuit_types()
    delete_devices()
    delete_ip_addresses()
    delete_vrfs()
    delete_vlans()
    delete_device_roles()
    delete_device_types()
    delete_platforms()
    delete_manufacturers()
    delete_tags()
    delete_racks()
    delete_sites()
    delete_regions()
    delete_tenants()
    delete_inventory_items_roles()
    delete_config_templates()


def populate_netbox():
    create_regions()
    ceate_tenants()
    create_sites()
    create_racks()
    create_manufacturers()
    create_device_types()
    create_device_roles()
    create_platforms()
    create_vrfs()
    create_ip_addresses()
    create_tags()
    create_devices()
    create_vlans()
    create_interfaces()
    create_power_outlet_ports()
    create_power_ports()
    create_inventory_items_roles()
    create_inventory_items()
    create_console_server_ports()
    create_console_ports()
    associate_ip_adress_to_devices()
    create_connections()
    # create_netbox_secrets_roles()
    # create_netbox_secrets_secrets()
    create_circuit_providers()
    creat_circuit_provider_networks()
    if NB_VERSION >= 3.5:
        create_circuit_provider_accounts()
    create_circuit_types()
    create_circuits()
    create_config_templates()


if __name__ == "__main__":
    try:
        nb = pynetbox.api(url=NB_URL, token=NB_API_TOKEN)
        # request status to verify that Netbox is reachable,
        # raises ConnectionError if Netbox is not reachable
        _ = nb.status()
        globals()["nb"] = nb
        NB_VERSION = float(".".join(nb.version.split(".")[:2]))
        globals()["NB_VERSION"] = NB_VERSION
    except Exception as e:
        log.exception(
            f"netbox_data failed to instantiate pynetbox.api object, "
            f"Netbox url '{NB_URL}', token ends with '..{NB_API_TOKEN[-6:]}', error '{e}'"
        )
        raise SystemExit()
    todo = input(
        """Select what to do with Netbox:
1 - cleanup
2 - populate
3 - cleanup first, next populate
[1,2,3]: """
    )
    if todo == "1":
        clean_up_netbox()
    elif todo == "2":
        populate_netbox()
    elif todo == "3":
        clean_up_netbox()
        populate_netbox()
