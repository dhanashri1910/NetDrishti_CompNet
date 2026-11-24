import ipaddress


def valid_ip(s):
    try:
        ipaddress.IPv4Address(str(s).strip())
        return str(s).strip().count(".") == 3
    except ValueError:
        return False


def valid_mask(s):
    try:
        ipaddress.IPv4Network("0.0.0.0/" + str(s).strip())
        return "." in str(s)
    except ValueError:
        return False


def mask_to_prefix(mask):
    return ipaddress.IPv4Network("0.0.0.0/" + mask).prefixlen


def calc(ip, mask=None, prefix=None):
    if not valid_ip(ip):
        raise ValueError("Invalid IPv4 address.")
    if mask:
        if not valid_mask(mask):
            raise ValueError("Invalid subnet mask (must be contiguous, e.g. 255.255.255.0).")
        net = ipaddress.IPv4Network(f"{ip}/{mask}", strict=False)
    elif prefix not in (None, ""):
        try:
            net = ipaddress.IPv4Network(f"{ip}/{int(prefix)}", strict=False)
        except ValueError:
            raise ValueError("Invalid CIDR prefix (0-32).")
    else:
        raise ValueError("Provide a subnet mask or CIDR prefix.")
    n = net.num_addresses
    if net.prefixlen == 32:
        first = last = net.network_address; usable = 1
    elif net.prefixlen == 31:
        first, last, usable = net.network_address, net.broadcast_address, 2
    else:
        first, last, usable = net.network_address + 1, net.broadcast_address - 1, n - 2
    return {"ip": ip, "network": str(net.network_address), "broadcast": str(net.broadcast_address),
            "mask": str(net.netmask), "wildcard": str(net.hostmask), "prefix": net.prefixlen, "cidr": str(net),
            "first_usable": str(first), "last_usable": str(last), "total_addresses": n, "usable_hosts": usable,
            "ip_class": "Private" if ipaddress.IPv4Address(ip).is_private else "Public"}
