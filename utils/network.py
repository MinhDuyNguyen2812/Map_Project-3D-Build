"""
Network utility: checks for an active internet connection.
Tries multiple hosts in case one is blocked by a firewall.
"""

import socket
import urllib.request


def has_internet_connection(timeout: int = 4) -> bool:
    """
    Returns True if an internet connection is available.
    Tries multiple methods to avoid firewall false negatives.
    """
    # Method 1: TCP connect to multiple DNS servers
    test_hosts = [
        ("8.8.8.8",   53),   # Google DNS
        ("1.1.1.1",   53),   # Cloudflare DNS
        ("208.67.222.222", 53),  # OpenDNS
    ]
    for host, port in test_hosts:
        try:
            socket.setdefaulttimeout(timeout)
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((host, port))
            s.close()
            return True
        except OSError:
            continue

    # Method 2: HTTP request as fallback
    try:
        urllib.request.urlopen("https://www.google.com", timeout=timeout)
        return True
    except Exception:
        pass

    return False