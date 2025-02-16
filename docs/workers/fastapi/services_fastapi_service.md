---
tags:
  - FastAPI
---

# FastAPI REST API Service

The FastAPI Service created to serve a set of REST API endpoints to interact with NorFab to start, run, list and retrieve jobs result.

NorFab FastAPI Service build using [FastAPI](https://fastapi.tiangolo.com/) library, as the name implies, a well adopted open-source library for building RESTful APIs.

![FastAPI Service Architecture](../../images/FastAPI_Service.jpg)

FastAPI Service acts as a thin wrapper for NorFab Python API, accepting northbound REST API requests and translating them into NorFab client API calls, returning job execution results in response.

## Overview

The FastAPI Service in Norfab provides a robust and efficient way to REST API into NorFab environment for network automation and management tasks. FastAPI is known for its high performance, ease of use, and automatic generation of interactive API documentation. By leveraging FastAPI, Norfab enables developers to utilize scalable and maintainable APIs that can handle a wide range of network automation operations.

## NorFab FastAPI Service Key Features

- **High Performance**: FastAPI is built on top of Starlette for the web parts and Pydantic for the data parts, ensuring high performance and fast response times.

- **Automatic Documentation**: NorFab FastAPI service comes with automatically generated interactive API documentation using Swagger UI and ReDoc, making it easy to explore and test the API endpoints.

- **Data Validation**: FastAPI uses Pydantic for data validation, ensuring that the input and output data is correctly formatted and adheres to the specified schema.


- **Security**: NorFab FastAPI service includes Bearer token API authentication, ensuring that the APIs are secure and protected.

## Use Cases

- **Network Device Management**: Use the NorFab FastAPI Service for managing network devices, including configuration changes, state retrieval, firmware updates etc.

- **Inventory Management**: Use REST API to automate the process of updating and maintaining network inventory, ensuring that the inventory data is always accurate and up-to-date.

- **Configuration Compliance**: Utilize REST API to automate configuration compliance checks and audits, ensuring that network devices adhere to predefined standards and policies.

- **Automation Workflows**: Use the NorFab FastAPI Service APIs to orchestrate complex automation workflows, integrating with other services and tools to streamline network operations.

## Getting Started

To get started with the FastAPI Service, you need to define the necessary parameters in your NorFab inventory. Refer to the [FastAPI Inventory](services_fastapi_service_inventory.md) section for detailed instructions on setting up your inventory and running FastAPI REST API Service with NorFab.

### Authentication

FastAPI NorFab service supports bearer token authentication using authorization header:

```
headers = {"Authorization": "Bearer f343ff34r3fg4g5g34gf34g34g3g34g4"}
```

Where token is an arbitrary string with no constraints imposed on length or complexity of the token. By default FastAPI Service does not have any bearer tokens stored, instead, every user willing to access REST API need to have token explicitly recorded in FastAPI Service database using nfcli auth commands.

To create token run this command from nfcli shell:

```
nf#fastapi auth create-token username foo token 4565t4yjn56h534gh35h543h5h45h4h4 expire 3600
{
    "fastapi-worker-1": true
}
nf#
```

`expire` argument is optional and indicates token expiration time in seconds, if no `expire` argument provided token does not expire. Multiple tokens can be stored for any given user.

Refer to [auth tasks documentation](services_fastapi_service_task_auth.md) for further details on how to work with FastAPI tokens.

### API Documentation

Once FastAPI worker started it serves REST API documentation under  `http://<IP Address or FQDN>/docs` url for [Swagger UI](https://github.com/swagger-api/swagger-ui) documentation and `http://<IP Address or FQDN>/redoc` for [ReDoc UI](https://github.com/Rebilly/ReDoc) documentation. Either of these UIs can be used to try and execute API requests and to familiarize yourself with API endpoints, requests payload and expected responses.

## HTTPS Support

NorFab FastAPI Service does not support HTTPS natively. To support HTTPS need to use reverse proxy (Nginx, Caddy etc.) or application loadbalancer that will perform TLS termination. Refer to [FastAPI documentation](https://fastapi.tiangolo.com/deployment/concepts/#example-tools-for-https) for further details on how to serve FastAPI applications via HTTPS.

## Conclusion

The FastAPI Service in Norfab provides a powerful and efficient RESTful APIs for network automation and management. With its high performance, automatic documentation, and robust feature set, FastAPI enables API integration that can handle a wide range of network operations. By using NorFab FastAPI REST API service, you can enhance your network automation capabilities and streamline your network management processes.

