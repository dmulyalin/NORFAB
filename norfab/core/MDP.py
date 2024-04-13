"""Majordomo Protocol definitions"""
#  This is the version of MDP/Client we implement
C_CLIENT = b"MDPC01"

#  This is the version of MDP/Worker we implement
W_WORKER = b"MDPW01"

#  MDP/Server commands, as strings
W_READY = b"WORKER READY"
W_REQUEST = b"WORKER REQUEST"
W_REPLY = b"WORKER REPLY"
W_HEARTBEAT = b"WORKER HEARTBEAT"
W_DISCONNECT = b"WORKER DISCONNECT"
W_INVENTORY_REQUEST = b"WORKER INVENTORY REQUEST"  # worker inventory request
W_INVENTORY_REPLY = b"WORKER INVENTORY REPLY"  # broker inventory reply to worker

commands = [
    None,
    b"READY",
    b"REQUEST",
    b"REPLY",
    b"HEARTBEAT",
    b"DISCONNECT",
    b"INVENTORY",
]


# Note, Python3 type "bytes" are essentially what Python2 "str" were,
# but now we have to explicitly mark them as such.  Type "bytes" are
# what PyZMQ expects by default.  Any user code that uses this and
# related modules may need to be updated.  Here are some guidelines:
#
# String literals that make their way into messages or used as socket
# identifiers need to become bytes:
#
#   'foo' -> b'foo'
#
# Multipart messages, originally formed as lists of strings (smsg)
# need to be washed into strings of bytes (bmsg) like:
#
#   bmsg = [one.encode('utf-8') for one in smsg]
#
# A multipart message received can be reversed
#
#   smsg = [one.decode() for one in bmsg]
