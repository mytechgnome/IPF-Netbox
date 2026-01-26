'''
Script to import Devices from IP Fabric into NetBox.

Created by: Dan Kelcher
Date: January 20, 2025

NOTE Known Issues and Limitations:
- Devices that are members of Virtual Chassis (VC) setups are split into individual device entries based on VC member data from IP Fabric.
- Required fields such as Device Type, Device Role, and Site must exist in NetBox for successful import. Devices missing these fields are skipped, and a log of missing data is created.
- Stack member interfaces are shown under the individual stack member device names, not under the master device. This could be intentional, as the physical interfaces belong to the stack members. (see bug about interface naming below)

Bugs:
- Stack members are not getting interfaces imported correctly, the interfaces should be shown as <member_number>/0/1, but are showing as 1/0/X for all members.
'''

# region # Imports and setup
from dotenv import load_dotenv
import IPFloader
import IPFexporter
import NetBoxloader
import requests
import os
from pathlib import Path
import datetime
from difflib import get_close_matches

starttime = datetime.datetime.now()

# region ## Load IP Fabric configuration
ipfbaseurl, ipftoken, ipfheaders = IPFloader.load_ipf_config()
# endregion
# region ## Load NetBox configuration
netboxbaseurl, netboxtoken, netboxheaders = NetBoxloader.load_netbox_config()
# endregion
# region ## Define paths
try:
    currentdir = Path(__file__).parent # Get directory of current script
except:
    currentdir = os.getcwd() # Fallback to current working directory
# endregion
# region ## Create log directory
starttime_str = starttime.strftime("%Y-%m-%d_%H-%M-%S")
log_dir=os.path.join(currentdir, 'Logs', 'IPF_NetBox_ImportDevices', starttime_str)
print(f'Creating log directory at {log_dir}')
os.makedirs(log_dir, exist_ok=True)
# endregion
# region ## Load variables from .env
# region ## Check for .env
if os.path.isfile('.env'):
    pass
else:
    print('.env file not found. Create a .env file with the required settings.')
    import CreateEnvFile
    CreateEnvFile.create_env_file()
# endregion
# region ## Set variables from .env file
load_dotenv()
modellnamesensitivity = float(os.getenv('modellnamesensitivity', '0.8'))
# endregion

# region # Export Devices from IP Fabric
ipf_devices = IPFexporter.export_ipf_data('inventory/devices', ['hostname', 'sn', 'siteName', 'snHw', 'loginIpv4', 'loginIpv6', 'uptime', 'reload', 'memoryUtilization', 'vendor', 'family', 'platform', 'model', 'version', 'devType'])
print(f'Total devices fetched from IP Fabric: {len(ipf_devices)}')
# region # Export VC members from IP Fabric
ipf_vcmembers = IPFexporter.export_ipf_data('platforms/stack/members', ['master', 'sn', 'siteName', 'member', 'pn', 'memberSn', 'role', 'state', 'mac', 'ver', 'image', 'hwVer'])
print(f'Total virtual chassis members fetched from IP Fabric: {len(ipf_vcmembers)}')
# endregion

# region # Transform VC members from IP Fabric
# region ## Build Lookup Tables
# region ### Match Device Types to NetBox Device Types
# region #### Get Device Types from NetBox
netbox_device_types = []
url = f'{netboxbaseurl}dcim/device-types/'
r = requests.get(url,headers=netboxheaders,verify=False)
netbox_device_types = r.json()['results']
# endregion
# region #### Build Device Type Lookup Dictionary
device_type_lookup = {}
for device_type in netbox_device_types:
    device_type_lookup[device_type['part_number']] = device_type['id']
# region ### Match Device Roles to NetBox Device Roles
# region #### Get Device Roles from NetBox
netbox_device_roles = []
url = f'{netboxbaseurl}dcim/device-roles/'
r = requests.get(url,headers=netboxheaders,verify=False)
netbox_device_roles = r.json()['results']
# endregion
# region #### Build Device Role Lookup Dictionary
device_role_lookup = {}
for device_role in netbox_device_roles:
    device_role_lookup[device_role['name']] = device_role['id']
# endregion
# endregion
# region ### Match Site Names to Site IDs
# region #### Get Sites from NetBox 
netbox_sites = []
url = f'{netboxbaseurl}dcim/sites/'
r = requests.get(url,headers=netboxheaders,verify=False)
netbox_sites = r.json()['results']
# endregion
# region #### Build Site Lookup Dictionary
site_lookup = {}
for netbox_site in netbox_sites:
    site_lookup[netbox_site['name']] = netbox_site['id']
# endregion
# endregion
# region ### Match Platform Names to NetBox IDs
# region #### Get Platforms from NetBox
netbox_platforms = []
url = f'{netboxbaseurl}dcim/platforms/'
r = requests.get(url,headers=netboxheaders,verify=False)
netbox_platforms = r.json()['results']
# endregion
# region #### Build Platform Lookup Dictionary
platform_lookup = {}
for netbox_platform in netbox_platforms:
    platform_lookup[netbox_platform['name']] = netbox_platform['id']
# endregion
# endregion
# region ### Match Virtual Chassis Masters to NetBox VC IDs
# region #### Get Virtual Chassis from NetBox
netbox_vc = []
url = f'{netboxbaseurl}dcim/virtual-chassis/'
r = requests.get(url,headers=netboxheaders,verify=False)
netbox_vc = r.json()['results']
# endregion
# region #### Build VC Lookup Dictionary
vc_lookup = {}
for vc in netbox_vc:
    vc_lookup[vc['name']] = vc['id']
# endregion
# endregion
# endregion

# region ## Initialize counters and lists
transformcounter = 0
required_fields_type_missing_count = 0
required_fields_role_missing_count = 0
required_fields_site_missing_count = 0
transform_list = []
missing_types = []
missing_roles = []
missing_sites = []
stack_masters = []

# endregion
# region ## Append data to devices
for device in ipf_devices:
    device['ipv4'] = device['loginIpv4'] if device['loginIpv4'] else None
    device['ipv6'] = device['loginIpv6'] if device['loginIpv6'] else None
    device['member'] = None
    device['vc_role'] = None
    device['vc_state'] = None
    device['vc_ver'] = None
    device['vc_image'] = None
    device['vc_hwver'] = None
#endregion
# region ## Append data from lookup tables
    device['device_type_ID'] = device_type_lookup.get(device['model'], None)
    if not device['device_type_ID']: # Attempt fuzzy match if exact match not found
        device['device_type_ID'] = get_close_matches(device['model'], list(device_type_lookup.keys()), n=1, cutoff=modellnamesensitivity)
    device['device_role_ID'] = device_role_lookup.get(device['devType'], None)
    device['platform_ID'] = platform_lookup.get(device['family'], None)
    device['site_ID'] = site_lookup.get(device['siteName'], None)
    device['vc_ID'] = vc_lookup.get(device['hostname'], None)

# endregion
# region ## Append additional data from IP Fabric
    hostname = device['hostname']
# region ### Determine if device is a VC member in ipf_vcmembers
    stack_members = [member for member in ipf_vcmembers if member['master'] == hostname]
# region #### Add non-VC members as-is
    if not stack_members:
        transform_list.append(device)
# endregion
# region #### Transform VC members into individual device entries 
    new_device = device.copy()
    master_member = next((m for m in stack_members if int(m['member']) == 1), None)
# region ##### Add master member
    if master_member: # Device is a VC master
        new_device['member']   = 1
        new_device['vc_role']  = master_member['role']
        new_device['vc_state'] = master_member['state']
        new_device['vc_ver']   = master_member['ver']
        new_device['vc_image'] = master_member['image']
        new_device['vc_hwver'] = master_member['hwVer']
        transform_list.append(new_device)
# endregion
# region ##### Add other members
    for member in stack_members:
        if int(member['member']) != 1:
            member_device = device.copy()
            member_device['hostname'] = f"{device['hostname']}/{member['member']}"
            member_device['model']    = member['pn']
            member_device['sn']       = member['memberSn']
            member_device['member']   = member['member']
            member_device['vc_role']  = member['role']
            member_device['vc_state'] = member['state']
            member_device['vc_ver']   = member['ver']
            member_device['vc_image'] = member['image']
            member_device['vc_hwver'] = member['hwVer']
            transform_list.append(member_device)
print(f'Processed {len(transform_list)} devices.')
# endregion
# endregion
# endregion
# region ## Error checking and required field validation
for device in transform_list:
    if not device['device_type_ID']:
        transform_list.remove(device)
        required_fields_type_missing_count += 1
        missing_types.append(device['model'])
        print(f'Required Field Warning: Device Type for PN {device["model"]} not found in NetBox lookup.')
    if not device['device_role_ID']:
        transform_list.remove(device)
        required_fields_role_missing_count += 1
        missing_roles.append(device['devType'])
        print(f'Required Field Warning: Device Role for type {device["devType"]} not found in NetBox lookup.')
    if not device['site_ID']:
        transform_list.remove(device)
        required_fields_site_missing_count += 1
        missing_sites.append(device['siteName'])
        print(f'Required Field Warning: Site {device["siteName"]} not found in NetBox lookup.')
    transformcounter += 1
print('Device transformation process completed.')
error_count = required_fields_site_missing_count + required_fields_role_missing_count + required_fields_type_missing_count
if error_count > 0:
    print('Required Field Warnings detected during transformation:')
    print(f'Total number of errors in required fields: {required_fields_type_missing_count + required_fields_role_missing_count + required_fields_site_missing_count}')
    if required_fields_type_missing_count > 0:
        print(f'Total devices with missing Device Type: {required_fields_type_missing_count}')
        print(f'Missing Device Types: {set(missing_types)}')
    if required_fields_role_missing_count > 0:
        print(f'Total devices with missing Device Role: {required_fields_role_missing_count}')
        print(f'Missing Device Roles: {set(missing_roles)}')
    if required_fields_site_missing_count > 0:
        print(f'Total devices with missing Site: {required_fields_site_missing_count}')
        print(f'Missing Sites: {set(missing_sites)}')
    print('Devices with errors have been removed from the import list.')
    print(f'Total devices to be imported after error removal: {len(transform_list)}')
    transformerror = ''
    while transformerror.lower() not in ['y', 'n']:
        transformerror = input("Continue with import? y/n: ")
        if transformerror.lower() == 'y':
            print('Continuing with import despite transformation errors.')
        elif transformerror.lower() == 'n':
            print('Import process aborted due to transformation errors.')
            exit()
# endregion
# endregion

# region # Load devices into NetBox
url = f'{netboxbaseurl}dcim/devices/'
deviceSuccessCount = 0
deviceFailCount = 0
deviceimportcounter = 0
devicesfailed = {}
for device in transform_list:
    devicename = device['hostname']
    device_type = device['device_type_ID']
    device_role = device['device_role_ID']
    platform = device['platform_ID']
    sn = device['sn']
    site = device['site_ID']
    status = 'active'
    virtual_chassis = device['vc_ID'] if device['vc_ID'] else None
    vc_position = device['member'] if device ['member'] else None
    description = f'Imported from IP Fabric'
    comments = f'Role: {device["vc_role"]}, HW Ver: {device["vc_hwver"]}, Image: {device["vc_image"]}, Ver: {device["vc_ver"]}'
    payload = {
        'name': devicename,
        'device_type': device_type,
        'role': device_role,
        'platform': platform,
        'serial': sn,
        'site': site,
        'status': status,
        'virtual_chassis': virtual_chassis,
        'vc_position': vc_position,
        'description': description,
        'comments': comments
    }
    r = requests.post(url,headers=netboxheaders,json=payload,verify=False)
    if r.status_code == 201:
        if device['vc_role'] == 'active':
            device_ID = r.json()['id']
            stack_masters.append(f'{device["vc_ID"]},{device_ID}')
        deviceSuccessCount += 1
    else:
        deviceFailCount += 1
        devicesfailed[devicename] = r.text
    deviceimportcounter += 1
    print(f'Import progress: {deviceimportcounter}/{len(transform_list)} devices imported.')
#endregion
# region # Update VC masters with member IDs
for vc, master in stack_masters:
    url = f'{netboxbaseurl}dcim/virtual-chassis/{vc}/'
    payload = {
        'master': int(master)
    }
    r = requests.patch(url,headers=netboxheaders,json=payload,verify=False)
    if r.status_code == 200:
        print(f'Updated VC {vc} with master device ID {master}.')
    else:
        print(f'Failed to update VC {vc} with master device ID {master}. Response: {r.text}')


# region # Summary and logging
endtime = datetime.datetime.now()
duration = endtime - starttime
print(f'Device import process completed. Duration: {duration}')
print(f'Total devices processed: {len(transform_list)}')
print(f'Total devices successfully imported: {deviceSuccessCount}')
print(f'Total devices failed to import: {deviceFailCount}')
with open(os.path.join(log_dir, 'errors_importdevices.csv'), 'w') as f:
    f.write('Device Name,Error Message\n')
    for devicename, errormsg in devicesfailed.items():
        f.write(f'{devicename},"{errormsg}"\n')
with open(os.path.join(log_dir, 'errors_missingdata.csv'), 'w') as file:
    file.write('Error Type,Count,Details\n')
    if required_fields_type_missing_count > 0:
        file.write(f'Device Type Missing,{required_fields_type_missing_count},"{set(missing_types)}"\n')
    if required_fields_role_missing_count > 0:
        file.write(f'Device Role Missing,{required_fields_role_missing_count},"{set(missing_roles)}"\n')
    if required_fields_site_missing_count > 0:
        file.write(f'Site Missing,{required_fields_site_missing_count},"{set(missing_sites)}"\n')
# endregion