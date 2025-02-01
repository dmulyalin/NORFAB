"""
References:

- https://pyzmq.readthedocs.io/en/latest/api/zmq.auth.html
"""
import os
import shutil
from typing import Union

import zmq.auth
import logging

log = logging.getLogger(__name__)

# disable warning "RuntimeWarning: Proactor event loop does not implement add_reader family of methods required for zmq"
if os.name == "nt":
    import asyncio

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class NorFabClientAuthProvider:
    """
    Class to be called to validate client key and domain.

    When client connects to broker, broker will call this class to validate
    client key and domain, if client key never seen before broker will store
    the key but will not allow client to connect until key is explicitly
    authorized by user using 'nfcli --keys' command
    """

    def __init__(self, broker):
        self.broker = broker

    def callback(self, domain, key):
        log.debug(f"Broker received client key, domain: {domain}, key: {key}")

        return True


def generate_certificates(
    base_dir: Union[str, os.PathLike],
    override=False,
    cert_name=None,
    broker_keys_dir=None,
    inventory=None,
) -> None:
    """
    Generate private and public zmq certificates

    :param base_dir: OS path to directory where create public_keys and
        private_keys sub-directories to store generate keys
    :param override: if True, removes existing private and public keys
        and creates new private and public keys
    :param cert_name: name of the key filename
    """
    if zmq.zmq_version_info() < (4, 0):
        raise RuntimeError(
            f"Security is not supported in libzmq version < 4.0. libzmq version {zmq.zmq_version()}"
        )

    public_keys_dir = os.path.join(base_dir, "public_keys")
    secret_keys_dir = os.path.join(base_dir, "private_keys")

    # create directories for certificates, remove old content if necessary
    for d in [public_keys_dir, secret_keys_dir]:
        if override is True and os.path.exists(d):
            shutil.rmtree(d)
        if not os.path.exists(d):
            os.mkdir(d)

    # generate certs if they do not exist
    if not os.path.exists(
        os.path.join(secret_keys_dir, f"{cert_name}.key_secret")
    ) or not os.path.exists(  # private key does not exist
        os.path.join(public_keys_dir, f"{cert_name}.key")
    ):  # public key does not exist
        # create new public and private keys
        public_file, secret_file = zmq.auth.create_certificates(
            secret_keys_dir, cert_name
        )
        # move public key to public_keys directory
        shutil.move(public_file, os.path.join(public_keys_dir, "."))

    # check if need to use broker public key from inventory
    if cert_name == "broker" and inventory.broker.get("shared_key"):
        secret_file = os.path.join(secret_keys_dir, "broker.key_secret")
        public_file = os.path.join(public_keys_dir, "broker.key")
        public_key, _ = zmq.auth.load_certificate(secret_file)
        public_key = public_key.decode("utf-8")
        # replace public key in .key_secret file with broker inventory public key
        with open(secret_file, "r") as f:
            content = f.read()
            content = content.replace(public_key, inventory.broker["shared_key"])
        with open(secret_file, "w") as f:
            f.write(content)
        # replace public key in .key file with broker inventory public key
        with open(public_file, "r") as f:
            content = f.read()
            content = content.replace(public_key, inventory.broker["shared_key"])
        with open(public_file, "w") as f:
            f.write(content)

    # if broker_keys_dir given and exists, copy broker public key across,
    # this is used when all NORFAB components run locally and not distributed
    if broker_keys_dir is not None and os.path.exists(
        os.path.join(broker_keys_dir, "broker.key")
    ):
        # copy broker public key to client/worker public_keys directory
        shutil.copyfile(
            os.path.join(broker_keys_dir, "broker.key"),
            os.path.join(public_keys_dir, "broker.key"),
        )
