---
tags:
  - nornir
---

# Overview

The purpose of Nornir service `cli` task designed to retrieve show commands 
output from devices using SSH and Telnet. Nornir `cli` uses Netmiko, Scrapli 
and NAPALM libraries to communicate with devices.

## Nornir CLI Sample Usage

Example of retrieving commands output from devices.

!!! example

    === "CLI"
    
        ```
        TBD
        ```
        
    === "CLI Demo"
    
    
    === "Python"
    
		This code is complete and can run as is
		
        ```
		import pprint
		
        from norfab.core.nfapi import NorFab
		
		nf = NorFab(inventory="inventory.yaml")
		nf.start()
		
		client = nf.make_client()
		
        res = nfclient.run_job(
            service="nornir",
            task="cli",
            kwargs={
				"commands": ["show clock", "show version"],
				"FC": "ceos-spine"				
			}
        )
		
		pprint.pprint(res)
		
		nf.destroy()
        ```

		Once executed, above code should produce this output:
		
		```
		TBD
		```
		
		Refer to [Getting Started](norfab_getting_started.md) section on 
		how to construct  `inventory.yaml` file.

## Using Different Connection Plugins

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