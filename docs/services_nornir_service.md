---
tags:
  - nornir
---

# Nornir Service

Nornir Service is built using [Nornir](https://github.com/nornir-automation/nornir)
library - a well adopted open-source tool for automating network devices operations.
 
![Nornir Service Architecture](images/Nornir_Service.jpg) 

With each Nornir worker capable of handling multiple devices simultaneously, 
Nornir Service offers high scalability, allowing efficient management of 
large device fleets. By optimizing compute resources such as CPU, RAM, and 
storage, it delivers cost-effective performance.

Additionally, Nornir Service supports various interfaces and libraries for 
seamless integration. For instance, the `cli` task can interact with devices 
via the Command Line Interface (CLI) using popular libraries like Netmiko, 
Scrapli, and NAPALM, providing flexibility for diverse network environments.
