# FasAPI Worker Inventory

Sample FasAPI worker inventory definition

```
service: fastapi
auth_bearer:
  token_ttl: 0 # never expires

# below parameters passed onto app = FastAPI(**fastapi_inventory) 
# https://fastapi.tiangolo.com/reference/fastapi/#fastapi.FastAPI
fastapi:
  title: FastAPI
  docs_url: "/docs"
  redoc_url: "/redoc"
  ..etc

# below parameters passed onto config = uvicorn.Config(app, **uvicorn_inventory)
# https://www.uvicorn.org/#config-and-server-instances
uvicorn:
  host: 0.0.0.0
  port: 8000
  ..etc
```