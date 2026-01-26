'''
Script to import VPN tunnels from IP Fabric into NetBox.

Created by: Dan Kelcher
Date: January 14, 2025
'''

# region # Imports and setup
import IPFloader 
import NetBoxloader
import requests

# region ## Load IP Fabric configuration
ipfbaseurl, ipftoken, ipfheaders = IPFloader.load_ipf_config()
# endregion
# region ## Load NetBox configuration
netboxbaseurl, netboxtoken, netboxheaders = NetBoxloader.load_netbox_config()
# endregion
# endregion

