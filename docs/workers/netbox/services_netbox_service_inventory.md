# Netbox Worker Inventory

Sample Netbox Worker Inventory

``` yaml
service: netbox
broker_endpoint: "tcp://127.0.0.1:5555"
cache_use: True # or False, refresh, force
cache_ttl: 31557600
netbox_connect_timeout: 10
netbox_read_timeout: 300
instances:
  prod:
    default: True
    url: "http://192.168.4.130:8000/"
    token: "0123456789abcdef0123456789abcdef01234567"
    ssl_verify: False
  dev:
    url: "http://192.168.4.131:8000/"
    token: "0123456789abcdef0123456789abcdef01234567"
    ssl_verify: False
  preprod:
    url: "http://192.168.4.132:8000/"
    token: "0123456789abcdef0123456789abcdef01234567"
    ssl_verify: False
```