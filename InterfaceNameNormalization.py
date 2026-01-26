
'''
Script to normalize interface names

Created by: Dan Kelcher
Date: January 13, 2025
'''

import re

# region # Interface normalization mappings
# Canonical (normalized) long-form target for comparison
# Keys: normalized short/variant; Values: canonical long form
# Add more mappings as needed
PREFIX_MAP = {
    # Ethernet speeds
    "fa": "FastEthernet",
    "fastethernet": "FastEthernet",

    "gi": "GigabitEthernet",
    "gigabitethernet": "GigabitEthernet",

    "te": "TenGigabitEthernet",
    "tengigabitethernet": "TenGigabitEthernet",

    # 25/40/100G common Cisco abbreviations
    "twe": "TwentyFiveGigE",            # short form commonly seen on IOS-XE
    "twentyfivegige": "TwentyFiveGigE",

    "fo": "FortyGigabitEthernet",
    "fortygigabitethernet": "FortyGigabitEthernet",
    "fortygige": "FortyGigabitEthernet",  # sometimes appears like this

    "hu": "HundredGigE",
    "hundredgige": "HundredGigE",
    "hundredgigabitethernet": "HundredGigE",  # long variant some platforms use

    # Generic Ethernet (NX-OS / Arista)
    "et": "Ethernet",
    "eth": "Ethernet",
    "ethernet": "Ethernet",

    # Port-channels
    "po": "Port-channel",
    "port-channel": "Port-channel",
    "portchannel": "Port-channel",

    # VLAN SVI
    "vl": "Vlan",
    "vlan": "Vlan",

    # Loopback
    "lo": "Loopback",
    "loopback": "Loopback",

    # Tunnel
    "tu": "Tunnel",
    "tunnel": "Tunnel",

    # Serial
    "se": "Serial",
    "serial": "Serial",

    # AppGigabitEthernet (ISR/ASR)
    "ap": "AppGigabitEthernet",
    "appgigabitethernet": "AppGigabitEthernet",

    # BDI (IOS-XE)
    "bd": "BDI",
    "bdi": "BDI",

    # Null
    "nu": "Null",
    "null": "Null",

    # Management Ethernet (platform dependent)
    "mgmteth": "MgmtEth",
    "mgmt": "MgmtEth",
    "mg": "MgmtEth",

    # Wireless-Radio / cellular interfaces (optional; extend as needed)
    "cellular": "Cellular",
    "dot11radio": "Dot11Radio",
    "wlan-gigabitethernet": "Wlan-GigabitEthernet",  # rare, example placeholder
}
# endregion

# region # Suffix pattern
# Some platforms (e.g., NX-OS) show dotted breakout units like Ethernet1/1/1
# and subinterfaces like GigabitEthernet1/0/1.123; Support flexible number formats.
SUFFIX_PATTERN = re.compile(r"\s*(\d[\d/.\-:]*)\s*$")
# endregion


# region # Extract prefix and numeric part, returns (prefix, suffix_or_empty)
def _split_iface(name: str):
    if not name:
        return "", ""

    s = name.strip()
    # Remove spaces between prefix and numbers (e.g., 'Gi 1/0/1' -> 'Gi1/0/1')
    s = re.sub(r"\s+(?=\d)", "", s)

    # Match leading letters/hyphens (prefix) followed by the rest
    m = re.match(r"^\s*([A-Za-z][A-Za-z\-]*)(.*)$", s)
    if not m:
        return "", s

    prefix_raw, rest = m.group(1), m.group(2)

    # Extract numeric suffix (if any)
    m2 = SUFFIX_PATTERN.search(rest)
    suffix = m2.group(1) if m2 else rest.strip()

    return prefix_raw, suffix
# endregion

# region # Normalize prefix
def normalize_prefix(prefix: str) -> str:
    key = prefix.lower().replace("_", "").strip()
    return PREFIX_MAP.get(key, prefix)  # default: preserve original if unknown
# endregion

# region # Normalize interface name
def normalize_iface(name: str) -> str:
    """
    Normalize any Cisco-like interface name to a canonical long form for comparison.
    Examples:
      'Gi1/0/1' -> 'GigabitEthernet1/0/1'
      'GigabitEthernet 1/0/1' -> 'GigabitEthernet1/0/1'
      'Te0/0/0' -> 'TenGigabitEthernet0/0/0'
      'Hu1/0/1' -> 'HundredGigE1/0/1'
      'Po10' -> 'Port-channel10'
      'Vl100' -> 'Vlan100'
      'Lo0' -> 'Loopback0'
      'Tunnel1' -> 'Tunnel1'
      'Eth1/1' -> 'Ethernet1/1'
      'Twe1/1/1' -> 'TwentyFiveGigE1/1/1'
    """
    prefix, suffix = _split_iface(name)
    if not prefix and not suffix:
        return name.strip()

    normalized_prefix = normalize_prefix(prefix)
    # Remove spaces from suffix as well (e.g., ' 1/0/1' -> '1/0/1')
    suffix = suffix.replace(" ", "")

    return f"{normalized_prefix}{suffix}"
# endregion
# region # Interface matching to confirm equivalence
def interfaces_match(a: str, b: str) -> bool:
    """Return True if interface names refer to the same port after normalization."""
    return normalize_iface(a) == normalize_iface(b)
# endregion

# region # Test code
if __name__ == "__main__":
    testInt = "Et1/0/1"
    print(f'Original Interface: {testInt}')
    print(f'Normalized Interface: {normalize_iface(testInt)}')
# endregion