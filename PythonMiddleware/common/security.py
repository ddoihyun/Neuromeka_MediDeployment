import string

def hash_data(data):
    hash_value = fnv1a_24(data)
    base62_hash = to_base62(hash_value, 4)
    return base62_hash

# FNV-1a 24비트 해시 함수
def fnv1a_24(data: str) -> int:
    FNV_prime = 0x01000193
    offset_basis = 0x811C9DC5
    hash = offset_basis

    for byte in data.encode('utf-8'):
        hash ^= byte
        hash *= FNV_prime
        hash &= 0xFFFFFFFF  # Ensure we remain within 32-bit range

    return hash & 0xFFFFFF  # Return only the lower 24 bits

def to_base62(num: int, length: int) -> str:
    BASE62 = string.ascii_uppercase + string.ascii_lowercase + string.digits
    base62 = []
    while num:
        num, rem = divmod(num, 62)
        base62.append(BASE62[rem])
    while len(base62) < length:
        base62.append('0')
    return ''.join(reversed(base62))