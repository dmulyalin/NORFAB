# NORFAB Protocol

Status: experimental
Editor: d.mulyalin@gmail.com
Contributors: 

The NORFAB Protocol (NFP) defines a reliable service-oriented request-reply dialog between a set of client applications, a broker and a set of worker applications representing service managing a set of resources. 

NFP covers presence, heartbeating, and service-resource-oriented request-reply processing. NFP originated from the MDP pattern defined in Chapter 4 of the ZeroMQ Guide and combined with TSP pattern (developed in same chapter) approach for persistent messaging across a network of arbitrarily connected clients and workers as a design for disk-based reliable messaging. NORFAB allows clients and workers to work without being connected to the network at the same time, and defines handshaking for safe storage of requests, and retrieval of replies.

## License

Copyright (c) 2024 Denis Mulyalin.

This Specification is free software; you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation; either version 3 of the License, or (at your option) any later version.

This Specification is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program; if not, see http://www.gnu.org/licenses.

## Change Process

This Specification is a free and open standard (see “Definition of a Free and Open Standard") and is governed by the Digital Standards Organization’s Consensus-Oriented Specification System (COSS) (see “Consensus Oriented Specification System").

## Language

The key words “MUST”, “MUST NOT”, “REQUIRED”, “SHALL”, “SHALL NOT”, “SHOULD”, “SHOULD NOT”, “RECOMMENDED”, “MAY”, and “OPTIONAL” in this document are to be interpreted as described in RFC 2119 (see “Key words for use in RFCs to Indicate Requirement Levels").

## Goals

The NORFAB Protocol (NFP) defines a reliable service-resource-oriented request-reply dialog between a set of client applications, a broker and a set of worker applications. NFP covers presence, heartbeating, and service-oriented request-reply processing. 

NFP uses name-based service resolution, named based resource targeting and structured protocol commands.

The goals of NFP are to:

- Allow requests to be routed to workers on the basis of abstract service names.
- Allow broker and workers to detect disconnection of one another, through the use of heartbeating.
- ALlow task distribution by clients targeting `all` (broadcast), `any` (anycast) or `unicast` certain workers by names within given service.
- Allow the broker to recover from dead or disconnected workers by re-sending requests to other workers.
- Allow workers to manage `resource` entities, where entities can be dynamically distributed across all workers within the service.
- Allow workers to have access to inventory data hosted by broker

## Architecture



### Overall Topology

NFP connects a set of client applications, a single broker device and a pool of workers applications. Clients connect to the broker, as do workers. Clients and workers do not see each other, and both can come and go arbitrarily. The broker MAY open two sockets (ports), one front-end for clients, and one back-end for workers. However NFP is also designed to work over a single broker socket.

We define ‘client’ applications as those issuing requests, and ‘worker’ applications as those processing them. NFP makes these assumptions:

- Workers are idempotent, i.e. it is safe to execute the same request more than once.
- Workers will handle at most one request a time, and will issue exactly one reply for each successful request.
- The NORFAB broker mediates requests one a per service basis. The broker SHOULD serve clients on a fair basis and SHOULD deliver requests to workers on the basis of targeting specified by client - `any` worker, `all` workers or `unicast` worker identified by name.

NFP consists of four sub-protocols:

- NFP/Client, which covers how the NFP broker communicates with client applications.
- NFP/Worker, which covers how the NFP broker communicates with workers applications.
- NFP/Worker-PUB, which covers how broker subscribes to events published by workers.
- NFP/Broker-PUB, which covers how broker publishes collected worker events to clients.

The broker SHOULD be an intermediary (a device) application that mediates Client-Workers communication. The broker SHOULD integrate Management Interface (MMI) service directly into it together with simple disk based Inventory service for workers.

### ROUTER Addressing

The broker MUST use a ROUTER socket to accept requests from clients, and connections from workers. The broker MAY use a separate socket for each sub-protocol, or MAY use a single socket for both sub-protocols.

From the ØMQ Reference Manual:

When receiving messages a ROUTER socket shall prepend a message part containing the identity of the originating peer to the message before passing it to the application. When sending messages a ROUTER socket shall remove the first part of the message and use it to determine the identity of the peer the message shall be routed to.

This extra frame is not shown in the sub-protocol commands explained below.

### NFP messages

#### OPEN

A OPEN command consists of 4 frames, formatted on the wire as follows:

```
OPEN command
---------------------------------------------------------------
Frame 0: Empty frame
Frame 1: “NFPC01” or “NFPW01” or “NFPB01” (six bytes, representing NFP/Client or NFP/Worker or NFP/Broker v0.1)
Frame 2: 0x00 (one byte, representing OPEN)
Frame 3: Open body (opaque binary)
```

Worker and client use OPEN message to introduce itself to broker to negotiate connection parameters. Broker sends OPEN message back to client or worker to confirm the connection.

#### READY

A READY command consists of a multipart message of 4 frames, formatted on the wire as follows:

```
READY command
---------------------------------------------------------------
Frame 0: Empty frame
Frame 1: “NFPW01” (six bytes, representing NFP/Worker v0.1)
Frame 2: 0x01 (one byte, representing READY)
Frame 3: Service name (printable string)
```

Worker sends READY command to broker, broker accepts ready request and registers worker with a service.

#### KEEPALIVE

A KEEPALIVE command consists of 4 frames, formatted on the wire as follows:

```
KEEPALIVE command
---------------------------------------------------------------
Frame 0: Empty frame
Frame 1: “NFPB01” or “NFPW01” (six bytes, representing NFP/Broker or NFP/Worker v0.1)
Frame 2: 0x02 (one byte, representing KEEPALIVE)
Frame 3: Service name (printable string)
```

Broker sends KEEPALIVE messages to workers to indicate broker is still alive.

Workers send KEEPALIVE messages to broker to indicate worker is still alive.

#### DISCONNECT

A DISCONNECT command consists of 3 frames, formatted on the wire as follows:

```
DISCONNECT command
---------------------------------------------------------------
Frame 0: Empty frame
Frame 1: “NFPB01” or “NFPW01” (six bytes, representing NFP/Broker or NFP/Worker v0.1)
Frame 2: 0x03 (one byte, representing DISCONNECT)
Frame 3: Service name (printable string)
Frame 4: Disconnect body (opaque binary)
```

Broker sends DISCONNECT command to workers to signal the request to disconnect. 

Workers also can send DISCONNECT command to broker to signal the request to disconnect. 

#### POST

A POST command consists of 7 or more frames, formatted on the wire as follows:

```
POST command
---------------------------------------------------------------
Frame 0: Empty (zero bytes, invisible to REQ application)
Frame 1: “NFPC01” or "NFPB01" (six bytes, representing NFP/Client or NFP/Broker v0.1)
Frame 2: 0x04 (one byte, representing POST)
Frame 3: Service name (printable string)
Frame 4: Target (printable string) workers, `all` (default), `any` or comma separated `worker names`
Frame 5: Job UUID (printable string)
Frames 6: POST body (opaque binary)
```

Client sends POST message to broker to distribute job requests among workers. 

Broker relays POST message to individual workers to publish job request.

#### RESPONSE

A RESPONSE command consists of 7 or more frames, formatted on the wire as follows:

```
RESPONSE command
---------------------------------------------------------------
Frame 0: Empty (zero bytes, invisible to REQ application)
Frame 1: “NFPB01” or “NFPW01” (six bytes, representing NFP/Broker or NFP/Worker v0.1)
Frame 2: 0x05 (one byte, representing RESPONSE)
Frame 3: Service name (printable string)
Frame 4: Job UUID (printable string)
Frame 5: Status code, (explained below)
Frames 6: Response body (opaque binary)
```

Worker sends RESPONSE message to broker with requests status or job results. 

Broker relays RESPONSE message to client.

#### GET

A GET command consists of 7 or more frames, formatted on the wire as follows:

```
GET command
---------------------------------------------------------------
Frame 0: Empty (zero bytes, invisible to REQ application)
Frame 1: “NFPC01” or "NFPB01" (six bytes, representing NFP/Client or NFP/Broker v0.1)
Frame 2: 0x06 (one byte, representing GET)
Frame 3: Service name (printable string)
Frame 4: Target (printable string) workers, `all` (default), `any` or comma separated `worker names`
Frame 5: Job UUID (printable string)
Frames 6: GET request body (opaque binary)
```

Client sends GET message to broker to retrieve job results. 

Broker relays GET message to individual workers to request job request.

#### DELETE

A DELETE command consists of 7 or more frames, formatted on the wire as follows:

```
DELETE command
---------------------------------------------------------------
Frame 0: Empty (zero bytes, invisible to REQ application)
Frame 1: “NFPC01” or "NFPB01" (six bytes, representing NFP/Client or NFP/Broker v0.1)
Frame 2: 0x07 (one byte, representing POST)
Frame 3: Service name (printable string)
Frame 4: Target (printable string) workers, `all` (default), `any` or comma separated `worker names`
Frame 5: Job UUID (printable string)
Frames 6: DELETE body (opaque binary)
```

Client sends DELETE message to broker to distribute job delete requests to workers. 

Broker relays DELETE message to individual workers to cancel the job.

### Status Frames

Every RESPONSE message contains a status frame followed by zero or more content frames. The status frame contains a string formatted as three digits, optionally followed by a space and descriptive text. A client MUST NOT treat the text as significant in any way. Implementations MAY NOT use status codes that are not defined here:

200 - OK. The NORFAB worker executed the request successfully. 
202 - ACCEPTED. The NORFAB Broker accepted POST request to dispatch the job.
300 - PENDING. The client SHOULD retry the request at a later time.
400 - UNKNOWN. The client is using an invalid or unknown UUID and SHOULD NOT retry.
408 - REQUEST TIMEOUT. Client did not receive response from broker or worker.
417 - EXPECT FAILED. Client did not receive what it was expecting to receive.
500 - ERROR. The server cannot complete the request due to some internal error. The client SHOULD retry at some later time.

### NFP/Client

NFP/Client is a strictly synchronous dialog initiated by the client (where ‘C’ represents the client, and ‘B’ represents the broker):

```

C: OPEN
B: OPEN

Repeat:

    C: POST
    B: RESPONSE
    ...
	
    C: GET
    B: RESPONSE
    ...
```
	
Clients SHOULD use a REQ socket when implementing a synchronous request-reply pattern. The REQ socket will silently create frame 0 for outgoing requests, and remove it for replies before passing them to the calling application. 

Clients MAY use any suitable strategy for recovering from a non-responsive broker. One recommended strategy is:

- To use polling instead of blocking receives on the request socket.
- If there is no reply within some timeout, to close the request socket and open a new socket, and resend the request on that new socket.
- If there is no reply after several retries, to signal the transaction as failed.
- The service name is a 0MQ string that matches the service name specified by a worker in its READY command (see NFP/Worker below). The broker SHOULD queue client requests for which service no workers has been registered and SHOULD expire these requests after a reasonable and configurable time if no service's workers has been registered.

### NFP/Broker

NFP/Broker is a mediator that receives messages from clients and dispatches them out to workers. In return messages from workers routed to clients.

### NFP/Worker

NFP/Worker is a mix of a synchronous request-reply dialog, initiated by the service worker, and an asynchronous heartbeat dialog that operates independently in both directions. This is the synchronous dialog (where ‘W’ represents the service worker, and ‘B’ represents the broker):

```
W: OPEN
B: OPEN
W: READY

Repeat:

    B: POST
    W: RESPONSE
    ...
	
    B: GET
    W: RESPONSE
    ...	
```
	
The asynchronous heartbeat dialog operates on the same sockets and works thus:

```
Repeat:                 Repeat:

    W: HEARTBEAT            B: HEARTBEAT
    ...                     ...
	
W: DISCONNECT           B: DISCONNECT
```


NFP/Worker commands all start with an empty frame to allow consistent processing of client and worker frames in a broker, over a single socket. The empty frame has no other significance.

### NFP/Worker-PUB

TBD 

### NFP/Broker-PUB

TBD

#### Job Persistence

Workers SHOULD persistently store job requests and job execution results for a configurable amount of time allowing clients (client submitted job request or any other client) to request job execution results on demand.

Clients SHOULD persistently store job requests and MAY store job execution results locally for a configurable amount of time.

#### Opening and Closing a Connection

The worker is responsible for opening and closing a logical connection. One worker MUST connect to exactly one broker using a single ØMQ DEALER (XREQ) socket.

Since ØMQ automatically reconnects peers after a failure, every NFP command includes the protocol header to allow proper validation of all messages that a peer receives.

The worker opens the connection to the broker by creating a new socket, connecting it, and then sending a READY command to register to a service. One worker handles precisely one service, and many workers MAY handle the same service. The worker MUST NOT send a further READY.

There is no response to a READY. The worker SHOULD assume the registration succeeded until or unless it receives a DISCONNECT, or it detects a broker failure through heartbeating.

The worker MAY send DISCONNECT at any time, including before READY. When the broker receives DISCONNECT from a worker it MUST send no further commands to that worker.

The broker MAY send DISCONNECT at any time, by definition after it has received at least one command from the worker.

The broker MUST respond to any valid but unexpected command by sending DISCONNECT and then no further commands to that worker. The broker SHOULD respond to invalid messages by dropping them and treating that peer as invalid.

When the worker receives DISCONNECT it must send no further commands to the broker; it MUST close its socket, and reconnect to the broker on a new socket. This mechanism allows workers to re-register after a broker failure and recovery.

#### POST and RESPONSE Processing

The POST and the RESPONSE commands MUST contain precisely one client address frame. This frame MUST be followed by an empty (zero sized) frame.

The address of each directly connected client is prepended by the ROUTER socket to all request messages coming from clients. That ROUTER socket also expects a client address to be prepended to each reply message sent to a client.

#### Keepaliving

KEEPALIVE commands are valid at any time, after a READY command.

Any received command except DISCONNECT acts as a keepalive. Peers SHOULD NOT send KEEPALIVE commands while also sending other commands.

Both broker and worker MUST send heartbeats at regular and agreed-upon intervals. A peer MUST consider the other peer “disconnected” if no keepalive arrives within some multiple of that interval (usually 3-5).

If the worker detects that the broker has disconnected, it SHOULD restart a new conversation.

If the broker detects that the worked has disconnected, it SHOULD stop sending messages of any type to that worker.

### Broker Management Interface (BMMI)

Broker SHOULD implement Management interface as a service endpoint for clients to interact with.

Broker should use `mmi.service.broker` service endpoint to listen to client's requests. 

These MMI functions SHOULD be implemented:

- `show_broker` - to return broker status and statistics
- `show_workers` - to return worker status and statistics 
- `show_clients` - to return clients statistics
- `show_services` - to return services status and statistics 
- `restart` - restart broker
- `shutdown` - shutdown broker completely
- `disconnect` - to disconnect all workers

### Worker Management Interface (WMMI)

Worker SHOULD implement Management interface as a service endpoint for clients to interact with.

Worker should use `mmi.service.worker` service endpoint to listen to client's requests. 

These MMI functions SHOULD be implemented:

- `show_broker` - to return broker status and statistics
- `show_workers` - to return worker status and statistics 
- `show_clients` - to return clients statistics
- `restart` - restart worker
- `shutdown` - shutdown worker completely
- `disconnect` - to disconnect worker from broker and re-establish connection

### Broker Simple Inventory Datastore (SID)

Broker should implement Inventory Datastore to store and serve configuration to workers as well as arbitrary workers inventory data.

Broker should use `sid.service.broker` service endpoint to listen to worker's requests. 

Workers willing to make use of broker's inventory datastore should implement `NFP/Client` protocol defined above to request inventory data.

These SID functions SHOULD be implemented:

- `get_inventory` - to return inventory content for given worker


#### SID Implementation

TBD

### Broker File Sharing Service (FSS)

Broker implements service to serve files to clients and workers from local file system using ``nf://<filepath>`` URL for supported arguments.

Broker should use `fss.service.broker` service endpoint to listen to worker's requests. 

#### FSS Implementation

TBD

###  Reliability

The NORFAB pattern is designed to extend the basic ØMQ request-reply pattern with the ability to detect and recover from a specific set of failures:

- Worker applications which crash, run too slowly, or freeze.
- Worker applications that are disconnected from the network (temporarily or permanently).
- Client applications that are temporarily disconnected from the network.
- A queue broker that crashes and is restarted.
- A queue broker that suffers a permanent failure.
- Requests or replies that are lost due to any of these failures.
- The general approach is to retry and reconnect, using heartbeating when needed. 

### Scalability and Performance

NORFAB is designed to be scalable to large numbers (thousands) of workers and clients allowing to manage 10s of thousands resource entities, limited only by system resources on the broker. Partitioning of workers by service allows for multiple applications to share the same broker infrastructure. Workers manage a set of resources defined by system administrator. Same resource can be managed by single or multiple workers, system impose no restrictions on how resource entities distributed across workers.

Throughput performance for a single client application will be limited to tens of thousands, not millions, of request-reply transactions per second due to round-trip costs and the extra latency of a broker-based approach. The larger the request and reply messages, the more efficient NORFAB will become. 

System requirements for the broker are moderate: no more than one outstanding request per client will be queued, and message contents can be switched between clients and workers without copying or processing. A single broker thread can therefore switch several million messages per second.

## Security

### Worker Authentication

TBD

### Worker Authorization

TBD

### Client Authentication

TBD

### Client Authorization - Role Based Access Control (RBAC)

TBD

### Client Encryption

TBD

### Worker Encryption

TBD

### Accounting

TBD

## Known Weaknesses

- The heartbeat rate must be set to similar values in broker and worker, or false disconnections will occur. 
- The use of multiple frames for command formatting has a performance impact.
