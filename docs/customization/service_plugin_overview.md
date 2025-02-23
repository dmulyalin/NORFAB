---
tags:
  - plugins
---

# Norfab Custom Service Plugins

Norfab custom service plugins provide a flexible and extensible way to enhance the functionality of Norfab platform. By creating and integrating custom plugins, you can tailor Norfab to meet your specific network automation and management needs. This documentation provides an overview of how to create, configure, and use custom service plugins in Norfab.

## Overview

Custom service plugins used to extend NorFab's capabilities by adding new features, tasks, and integrations. These plugins can be developed to interact with various network devices, data sources, and external systems, providing a seamless and integrated automation experience.

To create custom service plugin means to create custom worker class and register it with NorFab to run. NorFab support loading custom service workers using one of these two methods:

1. Load custom service worker from Python module using [entrypoints](https://packaging.python.org/en/latest/specifications/entry-points/).
2. Load custom service worker from NorFab base directory, base directory is a directory where `inventory.yaml` file resides.

## Key Features

- **Extensibility**: Easily extend the functionality of Norfab by creating custom service plugins that integrate with your existing tools and systems.
- **Flexibility**: Develop plugins to perform a wide range of tasks, from network device management to data processing and analysis.
- **Modularity**: Organize your custom plugins into modular components, making it easy to manage and maintain your codebase.
- **Reusability**: Reuse custom plugins across different projects and environments, ensuring consistency and reducing development effort.
