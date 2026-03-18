'''
Script to import VPN tunnels from IP Fabric into NetBox.

Created by: Dan Kelcher
Date: January 14, 2025
'''

# region # Imports and setup
from IPFloader import load_ipf_config
from NetBoxloader import load_netbox_config
from IPFexporter import export_ipf_data
from NetBoxHelper import *
import argparse
from datetime import datetime

# region ## Process arguments for branch selection
ap = argparse.ArgumentParser(description="Import Sites from IP Fabric into NetBox")
ap.add_argument("--branch", help="Create a NetBox branch for this import")
args = ap.parse_args()
if args.branch:
    branchurl = f'?_branch={args.branch}'
    schemaID = args.branch
else:
    branchurl = ''
    schemaID = None
# endregion

# region ## Load IP Fabric configuration
connected = False
while connected == False:
    try:
        ipfbaseurl, ipftoken, ipfheaders, ipflimit = load_ipf_config()
        connected = True
    except Exception as e:
        print(f"Error loading IP Fabric configuration: {e}")
        print("Please ensure the .env file is configured correctly and try again.")
        input("Press Enter to retry...")

# endregion
# region ## Load NetBox configuration
connected = False
while connected == False:
    try:
        netboxbaseurl, netboxtoken, netboxheaders, netboxlimit = load_netbox_config()
        connected = True
    except Exception as e:
        print(f"Error loading NetBox configuration: {e}")
        print("Please ensure the .env file is configured correctly and try again.")
        input("Press Enter to retry...")
# endregion
# endregion

# region # Export VPN tunnels from IP Fabric
ipf_vpns = export_ipf_data('security/ipsec/tunnels', ['hostname', 'profileName', 'encapsulation'])
# endregion

# region # Transform data
'''
Mapping
    IP Fabric -> NetBox
        profileName -> name
        encapsulation -> encapsulation (IP Fabric 'tunnel' = NetBox 'ipsec-tunnel')
    
Static values:
    Status: active
'''
netbox_vpns = []
for vpn in ipf_vpns:
    netbox_vpns.append({
        'name': f'{vpn["hostname"]}_{vpn["profileName"]}',
        'encapsulation': 'ipsec-tunnel' if vpn['encapsulation'] == 'tunnel' else 'ipsec-transport',
        'status': 'active'
    })
# endregion

# region # Load VPN tunnels into NetBox
counter = 0
success_count = 0
taskduration = []
for vpn in netbox_vpns:
    taskstart = datetime.now()
    result = post_netbox_data('vpn/tunnels', vpn, schemaID)
    if result:
        success_count += 1
    counter += 1
    taskend = datetime.now()
    taskduration.append((taskend - taskstart).total_seconds())
    remaining = sum(taskduration) / len(taskduration) * (len(netbox_vpns) - counter)
    print(f'Import progress: [{"█" * int(counter/len(netbox_vpns)*100):100}]{counter/len(netbox_vpns)*100:.2f}% Complete - ({counter}/{len(netbox_vpns)}) VPNs imported. Remaining: {remaining:.2f}s    ', end="\r")
print(f'\nVPN import process completed. Total Success: {success_count}, Failed: {counter - success_count}')
# endregion