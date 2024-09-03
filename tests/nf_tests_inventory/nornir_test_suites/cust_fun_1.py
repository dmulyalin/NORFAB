def run(result):
    ret = []
    if "Clock source: NTP" not in result.result:
        ret.append({"exception": "NTP not synced", "result": "FAIL", "success": False})
    return ret
