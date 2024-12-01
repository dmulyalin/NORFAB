## Install NorFab

Install NorFab from PyPI

```
pip install norfab
```

NorFab core runs equally well on both Windows and Linux. Some 
services might work only on one or the other, in that case that
will be noted in service deployment details.

## Extras

Several extra installations supported tailoring certain services
dependencies depending on what you want to run on a given node.

To install everything can use ``full`` extras:

```
pip install norfab[full]
```

### NORFAB CLI Dependencies

To install NorFab Interactive CLI dependencies

```
pip install norfab[nfcli]
```

### Nornir Service Dependencies

To install Nornir service dependencies

```
pip install norfab[nornir_service]
```

### Netbox Service Dependencies

To install Netbox service dependencies

```
pip install norfab[netbox_service]
```

## Operating Systems Support

| Component      | Windows      | Linux        | MacOS        |
| -------------- | ------------ | ------------ | ------------ |
| NorFab Core    | :check_mark: | :check_mark: | :check_mark: |
| Nornir Service | :check_mark: | :check_mark: | :check_mark: |
| Netbox Service | :check_mark: | :check_mark: | :check_mark: |