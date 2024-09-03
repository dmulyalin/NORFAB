def run(result):
    """Function to test when task is a list"""
    ret = []
    for item in result:
        if item.name == "show clock":
            if "Clock source: NTP" not in item.result:
                ret.append(
                    {
                        "exception": "NTP not synced cust fun 3",
                        "result": "FAIL",
                        "success": False,
                        "name": "test_cust_fun_3 Test NTP",
                    }
                )
        elif item.name == "show ip int brief":
            if "10.10.10.10" not in item.result:
                ret.append(
                    {
                        "exception": "10. IP not configured",
                        "result": "FAIL",
                        "success": False,
                        "name": "test_cust_fun_3 Test IP config",
                    }
                )

    return ret
