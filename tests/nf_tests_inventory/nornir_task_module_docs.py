import pprint

from norfab.core.nfapi import NorFab

if __name__ == '__main__':
    nf = NorFab(inventory="inventory.yaml")
    nf.start()
    
    client = nf.make_client()
    
    res = client.run_job(
        service="nornir",
        task="task",
        kwargs={
            "plugin": "nornir_netmiko.tasks.netmiko_send_command",
			"command_string": "show hostname",
            "FC": "ceos-spine"    
        }
    )
    
    pprint.pprint(res)
    
    nf.destroy()