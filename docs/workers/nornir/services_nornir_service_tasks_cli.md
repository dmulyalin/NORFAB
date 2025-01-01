---
tags:
  - nornir
---

# Nornir Service CLI Task

Nornir service `cli` task designed to retrieve show commands output 
from devices using SSH and Telnet. Nornir `cli` uses Netmiko, Scrapli 
and NAPALM libraries to communicate with devices.

- **Netmiko**: A multi-vendor library that simplifies SSH connections to network devices.
- **Scrapli**: A fast and flexible library for interacting with network devices.
- **NAPALM**: A library that provides a unified API to interact with different network device operating systems.

## Nornir CLI Sample Usage

Below is an example of how to use the Nornir CLI task to retrieve command outputs from devices.

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
        
        Demo
		
		![Nornir Cli Demo](../../images/nornir_cli_demo.gif)
    
        In this example:

        - `nfcli` command starts the NorFab Interactive Shell.
        - `nornir` command switches to the Nornir sub-shell.
        - `cli` command switches to the CLI task sub-shell.
        - `commands` command retrieves the output of "show clock" and 
            "show hostname" from the devices  that contain `ceos-spine` 
            in their hostname as we use `FC` - "Filter Contains" Nornir 
            hosts targeting filter.
		
		`inventory.yaml` should be located in same folder where we 
		start nfcli, unless `nfcli -i path_to_inventory.yaml` flag 
		used. Refer to [Getting Started](../../norfab_getting_started.md) 
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
		
		Refer to [Getting Started](../../norfab_getting_started.md) section on 
		how to construct  `inventory.yaml` file.

## Use Different Connection Plugins

Several device connection plugins supported such as ``netmiko``, ``napalm`` and ``scrapli``,
any of them can be invoked to retrieve show commands output, provided Nornir inventory contains
plugin's configuration.

## Outputting Text Tables

## Sourcing Commands From File

## Using Jinja2 Templates

## Using Dry Run

## Formatting Output Results

## Running Show Commands Multiple Times

## Using Netmiko Promptless Mode

## Parsing Commands Output

## Filtering Commands Output

## Sending New Line Character

## NORFAB Nornir CLI Shell Reference

NorFab shell supports these commands for Nornir `cli` task:

```
nf#man tree nornir.cli
root
└── nornir:    Nornir service
    └── cli:    Send CLI commands to devices
        ├── timeout:    Job timeout
        ├── workers:    Filter worker to target, default 'all'
        ├── add_details:    Add task details to results
        ├── run_num_workers:    RetryRunner number of threads for tasks execution
        ├── run_num_connectors:    RetryRunner number of threads for device connections
        ├── run_connect_retry:    RetryRunner number of connection attempts
        ├── run_task_retry:    RetryRunner number of attempts to run task
        ├── run_reconnect_on_fail:    RetryRunner perform reconnect to host on task failure
        ├── run_connect_check:    RetryRunner test TCP connection before opening actual connection
        ├── run_connect_timeout:    RetryRunner timeout in seconds to wait for test TCP connection to establish
        ├── run_creds_retry:    RetryRunner list of connection credentials and parameters to retry
        ├── tf:    File group name to save task results to on worker file system
        ├── tf_skip_failed:    Save results to file for failed tasks
        ├── diff:    File group name to run the diff for
        ├── diff_last:    File version number to diff, default is 1 (last)
        ├── progress:    Emit execution progress
        ├── table:    Table format (brief, terse, extend) or parameters or True
        ├── headers:    Table headers
        ├── headers_exclude:    Table headers to exclude
        ├── sortby:    Table header column to sort by
        ├── reverse:    Table reverse the sort by order
        ├── FO:    Filter hosts using Filter Object
        ├── FB:    Filter hosts by name using Glob Patterns
        ├── FH:    Filter hosts by hostname
        ├── FC:    Filter hosts containment of pattern in name
        ├── FR:    Filter hosts by name using Regular Expressions
        ├── FG:    Filter hosts by group
        ├── FP:    Filter hosts by hostname using IP Prefix
        ├── FL:    Filter hosts by names list
        ├── FM:    Filter hosts by platform
        ├── FX:    Filter hosts excluding them by name
        ├── FN:    Negate the match
        ├── hosts:    Filter hosts to target
        ├── *commands:    List of commands to collect form devices, default 'PydanticUndefined'
        ├── plugin:    Connection plugin parameters
        │   ├── netmiko:    Use Netmiko plugin to configure devices
        │   │   ├── enable:    Attempt to enter enable-mode
        │   │   ├── use_timing:    switch to send command timing method
        │   │   ├── expect_string:    Regular expression pattern to use for determining end of output
        │   │   ├── read_timeout:    Maximum time to wait looking for pattern
        │   │   ├── auto_find_prompt:    Use find_prompt() to override base prompt
        │   │   ├── strip_prompt:    Remove the trailing router prompt from the output
        │   │   ├── strip_command:    Remove the echo of the command from the output
        │   │   ├── normalize:    Ensure the proper enter is sent at end of command
        │   │   ├── use_textfsm:    Process command output through TextFSM template
        │   │   ├── textfsm_template:    Name of template to parse output with
        │   │   ├── use_ttp:    Process command output through TTP template
        │   │   ├── ttp_template:    Name of template to parse output with
        │   │   ├── use_genie:    Process command output through PyATS/Genie parser
        │   │   ├── cmd_verify:    Verify command echo before proceeding
        │   │   ├── interval:    Interval between sending commands
        │   │   ├── use_ps:    Use send command promptless method
        │   │   ├── use_ps_timeout:    Promptless mode absolute timeout
        │   │   ├── new_line_char:    Character to replace with new line before sending to device, default is _br_
        │   │   ├── repeat:    Number of times to repeat the commands
        │   │   ├── stop_pattern:    Stop commands repeat if output matches provided glob pattern
        │   │   ├── repeat_interval:    Time in seconds to wait between repeating commands
        │   │   └── return_last:    Returns requested last number of commands outputs
        │   ├── scrapli:    Use Scrapli plugin to configure devices
        │   │   ├── failed_when_contains:    String or list of strings indicating failure if found in response
        │   │   ├── timeout_ops:    Timeout ops value for this operation
        │   │   ├── interval:    Interval between sending commands
        │   │   ├── split_lines:    Split multiline string to individual commands
        │   │   ├── new_line_char:    Character to replace with new line before sending to device, default is _br_
        │   │   ├── repeat:    Number of times to repeat the commands
        │   │   ├── stop_pattern:    Stop commands repeat if output matches provided glob pattern
        │   │   ├── repeat_interval:    Time in seconds to wait between repeating commands
        │   │   └── return_last:    Returns requested last number of commands outputs
        │   └── napalm:    Use NAPALM plugin to configure devices
        │       ├── interval:    Interval between sending commands
        │       ├── split_lines:    Split multiline string to individual commands
        │       └── new_line_char:    Character to replace with new line before sending to device, default is _br_
        ├── cli_dry_run:    Dry run the commands
        ├── enable:    Enter exec mode
        ├── run_ttp:    TTP Template to run
        └── job_data:    Path to YAML file with job data
nf#
```

``*`` - mandatory/required command argument

## Python API Reference

::: norfab.workers.nornir_worker.NornirWorker.cli