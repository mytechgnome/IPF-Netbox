'''
Import device types using NetBox DeviceTypeLibrary from a YAML file.

Created by: Dan Kelcher
Date: February 23, 2026
'''

# region # Imports and setup
from NetBoxHelper import *
import argparse
import re

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

# region # Exort data from NetBox
# region ## Get existing locations from NetBox
# endregion
locations = get_netbox_data('dcim/locations',filters={'_branch='+schemaID} if schemaID else None)
# region ## Get existing devices from NetBox
devices = get_netbox_data('dcim/devices',filters={'_branch='+schemaID} if schemaID else None)
# endregion
# endregion

# region # Transform data
# region ## Parse locations from NetBox devices data
'''
This section uses pattern matching on the hostname. Adjust the patterns as needed to extract location information based on your hostname conventions.
Format rules are based on this structure:
    First 1-3 characters are the site (already imported from IP Fabric)
    A dash is used as a separator
    The next 1-3 characters are the building
    A dash is used as a separator
    The next 3-6 characters are the room (a child location of the building)
    A dash is used as a separator
    The remaining characters are the device name/number

 Devices that don't match this pattern will be skipped. 
 '''

location_regex = r'^[A-Za-z0-9]{1,3}-([A-Za-z0-9]{1,3})-([A-Za-z0-9]{3,6})-'

sites = {}
for d in devices:
# region ### Extract site information
    site = d.get('site') or {}
    siteID = d['site']['id'] if d['site'] else None
    siteName = d['site']['name'] if d['site'] else None
    if siteName not in sites:
        sites[siteName] = {'id': siteID, 'buildings': {}}
# endregion
# region ### Extract building and room information using regex pattern matching
    match = re.match(location_regex, d['name'])
    if match:
        building = match.group(1)
        room = match.group(2)
        d['building'] = building
        d['room'] = room
        if building not in sites[siteName]['buildings']:
            sites[siteName]['buildings'][building] = []
        if room and room not in sites[siteName]['buildings'][building]:
            sites[siteName]['buildings'][building].append(room)
        print(f"Parsed location for device {d['name']}: Site={siteName} (ID: {siteID}), Building={d['building']}, Room={d['room']}")
    else:
        print(f"Device {d['name']} in site {siteName} (ID: {siteID}) does not match the expected location pattern and will be skipped.")
# endregion
print(f"Parsed locations for {len(sites)} sites.")
print(f"Parsed locations for {sum(len(s['buildings']) for s in sites.values())} buildings.")
print(f"Parsed locations for {sum(len(b) for s in sites.values() for b in s['buildings'].values())} rooms.")

# endregion
# region ## Filter unique locations
# endregion
# region ## Compare with existing locations in NetBox and create list of new locations to add
# endregion

# region # Load data into NetBox
# region ## Add new locations to NetBox
# endregion
# region ## Add location to devices in NetBox
# endregion
# endregion