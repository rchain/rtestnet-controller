import nacl.signing
from nacl.encoding import HexEncoder


def generate_key_pair_hex():
    sk = nacl.signing.SigningKey.generate()
    pk = sk.verify_key
    sk_hex = sk.encode(encoder=HexEncoder).decode('ascii')
    pk_hex = pk.encode(encoder=HexEncoder).decode('ascii')
    return sk_hex, pk_hex


def generate_key_hex():
    return generate_key_pair_hex()[0]


def get_public_key_hex(sk_hex):
    sk = nacl.signing.SigningKey(sk_hex, encoder=HexEncoder)
    pk = sk.verify_key
    return pk.encode(encoder=HexEncoder).decode('ascii')
