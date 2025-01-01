import pprint

from norfab.core.nfapi import NorFab

if __name__ == "__main__":
    nf = NorFab(inventory="inventory.yaml")
    nf.start()

    client = nf.make_client()

    res = client.run_job(
        service="nornir",
        task="task",
        kwargs={
            "plugin": "nf://nornir_tasks/echo.py",
            "argument": {"foo": "bar"},
            "FC": "ceos-spine",
        },
    )

    pprint.pprint(res)

    nf.destroy()
