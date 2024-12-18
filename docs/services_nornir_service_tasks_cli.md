---
tags:
  - nornir
---

# Overview

Nornir service `cli` task designed to retrieve show commands output 
from devices using SSH and Telnet. Nornir `cli` uses Netmiko, Scrapli 
and NAPALM libraries to communicate with devices.

## Nornir CLI Sample Usage

Example of retrieving commands output from devices.

!!! example

    === "CLI"
    
        ```
		C:\nf>nfcli
		Welcome to NorFab Interactive Shell.
		nf#
		nf#nornir
		nf[nornir]#cli
		nf[nornir-cli]#
		nf[nornir-cli]#commands "show clock" "show hostname" FC ceos-spine
		ceos-spine-1:
			show clock:
				Sun Dec  1 10:49:58 2024
				Timezone: UTC
				Clock source: local
			show hostname:
				Hostname: ceos-spine-1
				FQDN:     ceos-spine-1
		ceos-spine-2:
			show clock:
				Sun Dec  1 10:49:58 2024
				Timezone: UTC
				Clock source: local
			show hostname:
				Hostname: ceos-spine-2
				FQDN:     ceos-spine-2
		nf[nornir-cli]#
        ```
        
        Small Demo
		
		![Nornir Cli Demo](images/nornir_cli_demo.gif)
    
		Above runs "show clock" and "show hostname" commands on all
		Nornir hosts that contain `ceos-spine` in their hostname as 
		we use 		`FC` - "Filter Contains" Nornir hosts targeting 
		filter.
		
		`inventory.yaml` should be located in same folder where we 
		start nfcli, unless `nfcli -i path_to_inventory.yaml` flag 
		used. Refer to [Getting Started](norfab_getting_started.md) 
		section on how to construct  `inventory.yaml` file
		
    === "Python"
    
		This code is complete and can run as is
		
        ```
        import pprint
        
        from norfab.core.nfapi import NorFab
        
        if __name__ == '__main__':
            nf = NorFab(inventory="inventory.yaml")
            nf.start()
            
            client = nf.make_client()
            
            res = client.run_job(
                service="nornir",
                task="cli",
                kwargs={
                    "commands": ["show clock", "show hostname"],
                    "FC": "ceos-spine"              
                }
            )
            
            pprint.pprint(res)
            
            nf.destroy()
        ```

		Once executed, above code should produce this output:
		
		```
        C:\nf>python nornir_cli.py
        {'nornir-worker-1': {'errors': [],
                             'failed': False,
                             'messages': [],
                             'result': {'ceos-spine-1': {'show clock': 'Sun Dec  1 '
                                                                       '11:10:53 2024\n'
                                                                       'Timezone: UTC\n'
                                                                       'Clock source: '
                                                                       'local',
                                                         'show hostname': 'Hostname: '
                                                                          'ceos-spine-1\n'
                                                                          'FQDN:     '
                                                                          'ceos-spine-1'},
                                        'ceos-spine-2': {'show clock': 'Sun Dec  1 '
                                                                       '11:10:53 2024\n'
                                                                       'Timezone: UTC\n'
                                                                       'Clock source: '
                                                                       'local',
                                                         'show hostname': 'Hostname: '
                                                                          'ceos-spine-2\n'
                                                                          'FQDN:     '
                                                                          'ceos-spine-2'}},
                             'task': 'nornir-worker-1:cli'}}
        C:\nf>					 
		```
		
		Refer to [Getting Started](norfab_getting_started.md) section on 
		how to construct  `inventory.yaml` file.

## Use Different Connection Plugins

## Outputting Text Tables

## Using Jinja2 Templates

## Using Dry Run

## Formatting Output Results

## Running Show Commands Multiple Times

## Using Netmiko Promptless Mode

## Parsing Commands Output

## Filtering Commands Output

## Sending New Line Character

## NORFAB Nornir CLI Shell Reference

NorFab shell supports these command options for Nornir `cli` task:

TBD

## Python API Reference

::: norfab.workers.nornir_worker.NornirWorker.cli