'''
Script to import Wireless SSIDs from IP Fabric into NetBox.

Created by: Dan Kelcher
Date: January 14, 2025

TO-DO:
 - Add logging to file
 - Add summary of successes/failures
'''

# region # Imports and setup
import IPFloader
import IPFexporter
import NetBoxloader
import requests
import datetime

starttime = datetime.datetime.now()

# region ## Load IP Fabric configuration
ipfbaseurl, ipftoken, ipfheaders, ipflimit = IPFloader.load_ipf_config()
# endregion
# region ## Load NetBox configuration
netboxbaseurl, netboxtoken, netboxheaders, netboxlimit = NetBoxloader.load_netbox_config()
# endregion
# endregion

# region # Export Wireless SSIDs from IP Fabric
ipf_ssids = IPFexporter.export_ipf_data('wireless/ssid-summary', ['ssid', 'radioCount', 'apCount', 'clientCount', 'wlcCount'])
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
        print(f'Successfully imported SSID {ssid_name} into NetBox.')
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
endtime = datetime.datetime.now()
duration = endtime - starttime
print(f'SSID import process completed. Start time: {starttime}, End time: {endtime}, Duration: {duration}')
# endregion