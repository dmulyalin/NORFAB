## 0.3.0

### FEATURES

1. Added "show version" support for nfcli client to display versions of locally installed libraries, fixes. #4
2. Added "show broker version" support for nfcli client to  retrieve broker report of the version of libraries broker is running on, fixes. #4
3. Added support "show broker inventory" command to display broker inventory
4. Simple inventory added support to produce a serialized dictionary output
5. Broker added "show_broker_inventory" and "show_broker_version" MMI endpoints
6. Added support for simple inventory service to render inventory using Jinja2, renderer passed on `env` variable that contains operating system environment variables, allowing to source any env data into NorFab inventory for both broker and workers. #5

## 0.2.4

### BUGS

1. Fixed nfcli `--workers-list` handling
2. Fixed `job_data` url handling for nornir cli/cfg/test tasks
3. Fixed nfapi handling of empty worker name

### FEATURES

1. Added a set of confirmed commit shell commands to nornir cfg netmiko plugin

---

## 0.2.3

### FEATURES

1. Added nfcli `--workers-list` option to specify a list of workers to start

### CHANGES

1. Fixed handling of jinja2 import for the worker to make it optional 

---

## 0.2.1

### CHANGES

1. Improved libs imports handling to account for distributed deployment
2. Improved logging handling
3. Fixed nfcli issue with starting components onf NorFab #2
4. Changed CTRL+C handling to trigger graceful NorFab exit

### FEATURES

1. Added `broker -> shared_secret` parameter in `inventory.yaml` to configure clients and workers broker shared secret key
2. Added and tested docker files

---

## 0.2.0

### CHANGES

1. refactored `get_circuits` to use `threadpoolexecutor` to fetch circuits path from netbox
2. adding `job_data` json load to nornir cli, cfg and test tasks

### BUGS

1. Fixing netbox `get_devices` dry run test
2. Fixed netbox `get_circuits` devices site retrieval handling

## FEATURES

1. Added cache to Netbox `get_circuits` and `get_devices` tasks
2. Added new `agent` worker to stsart working on use cases to interface with LLMs

---

## 0.1.1

### BUGS

1. FIxed Netbox CLI Shell handling of NFCLIENT

### CHANGES

1. Updated and tested dependencies for Netmiko 4.5.0
2. Updated and tested dependencies for Nornir 3.5.0
3. Updated and tested dependencies for Nornir-Salt 0.22.1

---

## 0.1.0

### Changes

1. Changes to Nornir service module files structure
2. PICLE dependency updated: 0.7.* -> 0.8.*
3. Made Nornir Service `progress` argument set to `True` by default to emit and display events for all Nornir Jobs
4. Nornir tests changed `table` argument to be set to `True` by default
5. Improved `nfapi` broker start logic to wait until broker fully initialized before proceeding to start workers

### Features

1. Added support for Nornir parse task to source TTP template from file with autocompletion
2. Added Nornir File Copy task to copy files to devices using SCP
3. Added support for logs to  be collected into single file from all NorFab local processes
4. Added to NorFab worker `job_list` and `job_details` methods
5. Added `show jobs summary` and `show jobs details` commands to NorFab shell and to Nornir shell
6. Added `--create-env` argument to nfcli utility to create NorFab folders and files to make it easier to get started using norfab

### BUGS

1. Fixed Nornir Service Watchdog to clean up dead connections from hosts data

---

## 0.0.0

Initial Release

### Notable Features

1. NorFAB Broker, Client and Worker base classes
2. Nornir Service
3. Network Service
4. Simple Inventory Datastore Service
5. File service
6. ZeroMQ encryption