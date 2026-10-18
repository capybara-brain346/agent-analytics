import hashlib
import ipaddress


def normalize_ip(ip: str) -> str:
    address = ipaddress.ip_address(ip.strip())
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        return str(ipaddress.ip_network(f"{address}/64", strict=False).network_address) + "/64"
    return str(address)


def client_key(user_agent: str | None, ip: str | None) -> str | None:
    if not user_agent or not user_agent.strip() or not ip or not ip.strip():
        return None
    try:
        normalized = normalize_ip(ip)
    except ValueError:
        return None
    digest = hashlib.sha256(f"{user_agent}\n{normalized}".encode()).hexdigest()
    return digest[:32]
