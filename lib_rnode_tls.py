from Crypto.PublicKey import ECC
from eth_hash.auto import keccak


def _get_node_id_raw_key(key):
    data = key.pointQ.x.to_bytes(32) + key.pointQ.y.to_bytes(32)
    return keccak(data)[12:].hex()


def generate_key_pem_node_id():
    key = ECC.generate(curve='P-256')
    key_pem = key.export_key(format='PEM')
    node_id = _get_node_id_raw_key(key)
    return key_pem, node_id


def generate_key_pem():
    return generate_key_pem_node_id()[0]


def get_node_id(key_pem):
    return _get_node_id_raw_key(ECC.import_key(key_pem))
