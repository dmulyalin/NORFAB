import pprint

from norfab.core.nfapi import NorFab

if __name__ == "__main__":
    nf = NorFab(inventory="inventory.yaml")
    nf.start()

    client = nf.make_client()

    res = client.run_job(
        service="nornir",
        task="cli",
        kwargs={"commands": ["show clock", "show hostname"], "FC": "ceos-spine"},
    )

    pprint.pprint(res)

    nf.destroy()
