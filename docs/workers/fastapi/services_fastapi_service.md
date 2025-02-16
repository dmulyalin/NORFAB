---
tags:
  - FastAPI
---

# FastAPI REST API Service

The FastAPI Service created to serve a set of REST API endpoints to interact with NorFab to start, run, list jobs and to retrieve jobs result.

NorFab FastAPI Service build using [FastAPI](https://fastapi.tiangolo.com/) library, as the name implies, a well adopted open-source library for building RESTful APIs.

![FastAPI Service Architecture](../../images/FastAPI_Service.jpg)

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

### Authorization


## Conclusion

The FastAPI Service in Norfab provides a powerful and efficient RESTful APIs for network automation and management. With its high performance, automatic documentation, and robust feature set, FastAPI enables API integration that can handle a wide range of network operations. By using NorFab FastAPI REST API service, you can enhance your network automation capabilities and streamline your network management processes.
