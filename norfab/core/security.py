import os
import shutil
from typing import Union

import zmq.auth

# disable warning "RuntimeWarning: Proactor event loop does not implement add_reader family of methods required for zmq"
if os.name == "nt":
    import asyncio

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def generate_certificates(
    base_dir: Union[str, os.PathLike],
    override=False,
    cert_name=None,
    broker_keys_dir=None,
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

    # if broker_keys_dir given and exists, copy broker public key across,
    # this is used when all NORFAB components run locally and not distributed
    if broker_keys_dir is not None and os.path.exists(
        os.path.join(broker_keys_dir, "broker.key")
    ):
        shutil.copyfile(
            os.path.join(broker_keys_dir, "broker.key"),
            os.path.join(public_keys_dir, "broker.key"),
        )
