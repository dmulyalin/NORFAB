# FasAPI Worker Inventory

Content of `inventory.yaml` need to be updated to include FastAPI worker details:

``` yaml title="inventory.yaml"
broker: 
  endpoint: "tcp://127.0.0.1:5555" 
  shared_key: "5z1:yW}]n?UXhGmz+5CeHN1>:S9k!eCh6JyIhJqO"

workers:
  fastapi-worker-1: 
    - fastapi/fastapi-worker-1.yaml

topology: 
  workers: 
    - fastapi-worker-1
```

Sample FasAPI worker inventory definition

``` yaml title="fastapi/fastapi-worker-1.yaml"
service: fastapi
auth_bearer:
  token_ttl: None

# below parameters passed onto app = FastAPI(**fastapi_inventory) 
# https://fastapi.tiangolo.com/reference/fastapi/#fastapi.FastAPI
fastapi:
  title: FastAPI
  docs_url: "/docs"
  redoc_url: "/redoc"
  # ..etc

# below parameters passed onto config = uvicorn.Config(app, **uvicorn_inventory)
# https://www.uvicorn.org/#config-and-server-instances
uvicorn:
  host: 0.0.0.0
  port: 8000
  # ..etc
```