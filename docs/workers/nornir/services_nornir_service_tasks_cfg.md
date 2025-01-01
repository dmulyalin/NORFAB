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
		
		Refer to [Getting Started](../../norfab_getting_started.md) section on 
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

```
nf#man tree nornir.cfg
root
└── nornir:    Nornir service
    └── cfg:    Configure devices over CLI interface
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
        ├── cfg_dry_run:    Dry run cfg function
        ├── *config:    List of configuration commands to send to devices, default 'PydanticUndefined'
        ├── plugin:    Configuration plugin parameters
        │   ├── netmiko:    Use Netmiko plugin to configure devices
        │   │   ├── enable:    Attempt to enter enable-mode
        │   │   ├── exit_config_mode:    Determines whether or not to exit config mode after complete
        │   │   ├── strip_prompt:    Determines whether or not to strip the prompt
        │   │   ├── strip_command:    Determines whether or not to strip the command
        │   │   ├── read_timeout:    Absolute timer to send to read_channel_timing
        │   │   ├── config_mode_command:    The command to enter into config mode
        │   │   ├── cmd_verify:    Whether or not to verify command echo for each command in config_set
        │   │   ├── enter_config_mode:    Do you enter config mode before sending config commands
        │   │   ├── error_pattern:    Regular expression pattern to detect config errors in the output
        │   │   ├── terminator:    Regular expression pattern to use as an alternate terminator
        │   │   ├── bypass_commands:    Regular expression pattern indicating configuration commands, cmd_verify is automatically disabled
        │   │   ├── commit:    Commit configuration or not or dictionary with commit parameters
        │   │   ├── commit_final_delay:    Time to wait before doing final commit
        │   ├── scrapli:    Use Scrapli plugin to configure devices
        │   │   ├── dry_run:    Apply changes or not, also tests if possible to enter config mode
        │   │   ├── strip_prompt:    Strip prompt from returned output
        │   │   ├── failed_when_contains:    String or list of strings indicating failure if found in response
        │   │   ├── stop_on_failed:    Stop executing commands if command fails
        │   │   ├── privilege_level:    Name of configuration privilege level to acquire
        │   │   ├── eager:    Do not read until prompt is seen at each command sent to the channel
        │   │   └── timeout_ops:    Timeout ops value for this operation
        │   └── napalm:    Use NAPALM plugin to configure devices
        │       ├── replace:    Whether to replace or merge the configuration
        │       ├── dry_run:    Apply changes or not, also tests if possible to enter config mode
        │       └── revert_in:    Amount of time in seconds after which to revert the commit
        └── job_data:    Path to YAML file with job data
nf#
```

``*`` - mandatory/required command argument

## Python API Reference

::: norfab.workers.nornir_worker.NornirWorker.cfg