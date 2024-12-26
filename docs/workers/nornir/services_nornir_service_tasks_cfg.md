---
tags:
  - nornir
---

# Nornir Service CFG Task

Nornir service `cfg` task designed to send configuration to devices 
using SSH and Telnet. Nornir `cfg` can use Netmiko, Scrapli and 
NAPALM libraries to configure with devices.

## Nornir CFG Sample Usage

Example of sending configuration commands to devices.

!!! example

    === "CLI"
    
        ```
		C:\nf>nfcli
		Welcome to NorFab Interactive Shell.
		nf#

        ```
        
        Demo
		
		![Nornir CFG Demo](../../images/nornir_cfg_demo.gif)
    
		Above runs "show clock" and "show hostname" commands on all
		Nornir hosts that contain `ceos-spine` in their hostname as 
		we use `FC` - "Filter Contains" Nornir hosts targeting 
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
                task="cfg",
                kwargs={
                    "config": ["ntp server 10.0.0.1", "ntp server 10.0.0.2"],
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
	
## Use Different Configuration Plugins

## Outputting Text Tables

## Sourcing Configuration From File

## Using Jinja2 Templates

## Using Dry Run

## Formatting Output Results

## Sending New Line Character	
		
## NORFAB Nornir CFG Shell Reference

NorFab shell supports these command options for Nornir `cfg` task:

TBD

## Python API Reference

::: norfab.workers.nornir_worker.NornirWorker.cfg