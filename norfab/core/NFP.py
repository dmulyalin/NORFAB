"""NORFAB Protocol definitions"""
# This is the version of NFP/Client we implement
CLIENT = b"NFPC01"

# This is the version of NFP/Worker we implement
WORKER = b"NFPW01"

# This is the version of NFP/Broker we implement
BROKER = b"NFPB01"

# NORFAB Protocol commands, as strings
OPEN = b"0x00"
READY = b"0x01"
KEEPALIVE = b"0x02"
DISCONNECT = b"0x03"
POST = b"0x04"
RESPONSE = b"0x05"
GET = b"0x06"
DELETE = b"0x07"
EVENT = b"0x08"

commands = [
    b"OPEN",
    b"READY",
    b"KEEPALIVE",
    b"DISCONNECT",
    b"POST",
    b"RESPONSE",
    b"GET",
    b"DELETE",
]

client_commands = [OPEN, DISCONNECT, POST, GET, DELETE]

worker_commands = [OPEN, READY, KEEPALIVE, DISCONNECT, RESPONSE]

broker_commands = [OPEN, KEEPALIVE, DISCONNECT, POST, RESPONSE, GET, DELETE]
