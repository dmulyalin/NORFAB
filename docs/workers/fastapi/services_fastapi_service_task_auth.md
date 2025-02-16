---
tags:
  - FastAPI
---

# FastAPI Auth Tasks

FastAPI service supports bearer token REST API authentication. To handle tokens lifecycle a number of FastAPI Service methods created allowing to store, delete, list and check API tokens.

## Auth Tasks Sample Usage

To store authentication token in FastAPI service database:

```
nf#fastapi auth create-token username foobar token f343ff34r3fg4g5g34gf34g34g3g34g4 expire 3600
{
    "fastapi-worker-1": true
}
nf#
```

`expire` argument is optional and indicates token expiration time in seconds, if no `expire` argument provided token does not expire. Multiple tokens can be stored for any given user.

To list stored tokens for specific user:

```
nf#fastapi auth list-tokens username foobar
 worker            username  token                             age             creation                    expires
 fastapi-worker-1  foobar    f343ff34r3fg4g5g34gf34g34g3g34g4  0:01:29.688340  2025-02-16 20:08:51.914919  2025-02-16 21:08:51.914919
 fastapi-worker-1  foobar    888945f96b824bf1b4358de790c452b6  8:08:51.548662  2025-02-16 12:01:30.054597  None
 fastapi-worker-1  foobar    04d685d203274a089c1a7df1395ed7e1  7:58:23.498734  2025-02-16 12:11:58.104525  None
 fastapi-worker-1  foobar    dfea48a8e412451cb2918fd526ab6c99  7:58:22.485560  2025-02-16 12:11:59.117699  None
nf#
```

To list all stored tokens:

```
nf#fastapi auth list-tokens
 worker            username  token                             age             creation                    expires
 fastapi-worker-1  pytest    11111111111111111111111111111111  1:26:18.492274  2025-02-16 18:44:18.124019  None
 fastapi-worker-1  foobar    f343ff34r3fg4g5g34gf34g34g3g34g4  0:01:44.701374  2025-02-16 20:08:51.914919  2025-02-16 21:08:51.914919
 fastapi-worker-1  foobar    888945f96b824bf1b4358de790c452b6  8:09:06.561696  2025-02-16 12:01:30.054597  None
 fastapi-worker-1  foobar    04d685d203274a089c1a7df1395ed7e1  7:58:38.511768  2025-02-16 12:11:58.104525  None
 fastapi-worker-1  foobar    dfea48a8e412451cb2918fd526ab6c99  7:58:37.498594  2025-02-16 12:11:59.117699  None
 fastapi-worker-1  foo       4565t4yjn56h534gh35h543h5h45h4h4  0:00:27.641482  2025-02-16 20:10:08.974811  2025-02-16 21:10:08.974812
nf#
```

To delete specific token:

```
nf#fastapi auth delete-token token 888945f96b824bf1b4358de790c452b6
{
    "fastapi-worker-1": true
}
nf#
```

To delete all tokens for given user:

```
nf#fastapi auth delete-token username foo
{
    "fastapi-worker-1": true
}
nf#
```

To check if token is valid:

```
nf#fastapi auth check-token token 888945f96b824bf1b4358de790c452b6
{
    "fastapi-worker-1": false
}
nf#fastapi auth check-token token f343ff34r3fg4g5g34gf34g34g3g34g4
{
    "fastapi-worker-1": true
}
nf#
```

## NORFAB FastAPI Service Auth Tasks Command Shell Reference

NorFab shell supports these command options for FastAPI `auth` tasks:

```
nf#man tree fastapi.auth
root
└── fastapi:    FastAPI service
    └── auth:    Manage auth tokens
        ├── create-token:    Create authentication token
        │   ├── timeout:    Job timeout
        │   ├── workers:    Filter worker to target, default 'all'
        │   ├── token:    Token string to store, autogenerate if not given
        │   ├── *username:    Name of the user to store token for
        │   └── expire:    Seconds before token expire
        ├── list-tokens:    Retrieve authentication tokens
        │   ├── timeout:    Job timeout
        │   ├── workers:    Filter worker to target, default 'all'
        │   └── username:    Name of the user to list tokens for
        ├── delete-token:    Delete existing authentication token
        │   ├── timeout:    Job timeout
        │   ├── workers:    Filter worker to target, default 'all'
        │   ├── username:    Name of the user to delete tokens for
        │   └── token:    Token string to delete
        └── check-token:    Check if given token valid
            ├── timeout:    Job timeout
            ├── workers:    Filter worker to target, default 'all'
            └── *token:    Token string to check
nf#
```

## Python API Reference

### bearer_token_store

::: norfab.workers.fastapi_worker.FastAPIWorker.bearer_token_store

### bearer_token_delete

::: norfab.workers.fastapi_worker.FastAPIWorker.bearer_token_delete

### bearer_token_list

::: norfab.workers.fastapi_worker.FastAPIWorker.bearer_token_list

### bearer_token_check

::: norfab.workers.fastapi_worker.FastAPIWorker.bearer_token_check