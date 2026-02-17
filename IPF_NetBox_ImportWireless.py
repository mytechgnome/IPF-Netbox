'''
Script to import Wireless SSIDs from IP Fabric into NetBox.

Created by: Dan Kelcher
Date: January 14, 2025

TO-DO:
 - Add logging to file
 - Add summary of successes/failures
'''

# region # Imports and setup
from IPFloader import load_ipf_config
from NetBoxloader import load_netbox_config
from IPFexporter import export_ipf_data
import requests
from datetime import datetime

starttime = datetime.now()

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

# region # Export Wireless SSIDs from IP Fabric
ipf_ssids = export_ipf_data('wireless/ssid-summary', ['ssid', 'radioCount', 'apCount', 'clientCount', 'wlcCount'])
print(f'Total SSIDs fetched from IP Fabric: {len(ipf_ssids)}')
# endregion

# region # Transform SSIDs from IP Fabric
''' No transformation needed for SSIDs '''
# endregion

# region # Load SSIDs into NetBox
url = f'{netboxbaseurl}wireless/wireless-lans/'
ssidSuccessCount = 0
ssidFailCount = 0
for ssid in ipf_ssids:
    ssid_name = ssid['ssid']
    payload = {
        'name': ssid_name,
        'ssid': ssid_name,
        'description': f'Imported from IP Fabric - Radio Count: {ssid["radioCount"]}, AP Count: {ssid["apCount"]}, Client Count: {ssid["clientCount"]}, WLC Count: {ssid["wlcCount"]}'
    }
    r = requests.post(url,headers=netboxheaders,json=payload,verify=False)
    if r.status_code == 201:
        ssidSuccessCount += 1
    else:
        print(f'Failed to import SSID {ssid_name} into NetBox. Status Code: {r.status_code}, Response: {r.text}')
        ssidFailCount += 1
# endregion
# region # Summary and logging
print('SSID import process completed.')
print(f'Total SSIDs processed: {len(ipf_ssids)}')
print(f'Total SSIDs successfully imported: {ssidSuccessCount}')
print(f'Total SSIDs failed to import: {ssidFailCount}')
endtime = datetime.now()
duration = endtime - starttime
print(f'SSID import process completed. Start time: {starttime}, End time: {endtime}, Duration: {duration}')
# endregion