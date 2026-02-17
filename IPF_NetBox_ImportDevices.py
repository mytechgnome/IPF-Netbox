'''
Script to import Devices from IP Fabric into NetBox.

Created by: Dan Kelcher
Date: January 20, 2025

NOTE Known Issues and Limitations:
- Devices that are members of Virtual Chassis (VC) setups are split into individual device entries based on VC member data from IP Fabric.
- Required fields such as Device Type, Device Role, and Site must exist in NetBox for successful import. Devices missing these fields are skipped, and a log of missing data is created.

Bugs:
- Stack members are not getting interfaces imported correctly, the interfaces should be shown as <member_number>/0/1, but are showing as 1/0/X for all members.
'''

# region # Imports and setup
from dotenv import load_dotenv
from IPFloader import load_ipf_config
import IPFexporter
from NetBoxloader import load_netbox_config
from NetBoxexporter import export_netbox_data
import requests
import os
from pathlib import Path
from datetime import datetime
import re
from difflib import get_close_matches

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
load_dotenv(override=True)
modellnamesensitivity = float(os.getenv('modellnamesensitivity', '0.8'))
# endregion

# region # Export data from IP Fabric
# region ## Export Devices from IP Fabric
ipf_devices = IPFexporter.export_ipf_data('inventory/devices', ['hostname', 'sn', 'siteName', 'snHw', 'loginIpv4', 'loginIpv6', 'uptime', 'reload', 'memoryUtilization', 'vendor', 'family', 'platform', 'model', 'version', 'devType'])
print(f'Total devices fetched from IP Fabric: {len(ipf_devices)}')
# endregion
# region ## Export VC members from IP Fabric
# region ### Export Stack members from IP Fabric
ipf_stackmembers = IPFexporter.export_ipf_data('platforms/stack/members', ['master', 'sn', 'siteName', 'member', 'pn', 'memberSn', 'role', 'state', 'mac', 'ver', 'image', 'hwVer'])
print(f'Total virtual chassis members fetched from IP Fabric: {len(ipf_stackmembers)}')
# endregion
# region ### Export VSS members from IP Fabric
ipf_vssmembers = IPFexporter.export_ipf_data('platforms/vss/chassis', ['hostname', 'chassisSn', 'siteName', 'chassisId', 'sn', 'state'])
print(f'Total VSS members fetched from IP Fabric: {len(ipf_vssmembers)}')
# endregion
# endregion
# endregion

# region # Transform VC members from IP Fabric
# region ## Build Lookup Tables
# region ### Get Part Numbers from IP Fabric
ipf_pns = IPFexporter.export_ipf_data('inventory/pn', ['pid', 'sn'])
# endregion
# region ### Match Device Types to NetBox Device Types
# region #### Get Device Types from NetBox
netbox_device_types = export_netbox_data('dcim/device-types')
# endregion
# region #### Build Device Type Lookup Dictionary
device_type_lookup = {}
for device_type in netbox_device_types:
    device_type_lookup[device_type['part_number']] = device_type['id']
# region ### Match Device Roles to NetBox Device Roles
# region #### Get Device Roles from NetBox
netbox_device_roles = export_netbox_data('dcim/device-roles')
# endregion
# region #### Build Device Role Lookup Dictionary
device_role_lookup = {}
for device_role in netbox_device_roles:
    device_role_lookup[device_role['name']] = device_role['id']
# endregion
# endregion
# region ### Match Site Names to Site IDs
# region #### Get Sites from NetBox 
netbox_sites = export_netbox_data('dcim/sites')
# endregion
# region #### Build Site Lookup Dictionary
site_lookup = {}
for netbox_site in netbox_sites:
    site_lookup[netbox_site['name']] = netbox_site['id']
# endregion
# endregion
# region ### Match Platform Names to NetBox IDs
# region #### Get Platforms from NetBox
netbox_platforms = export_netbox_data('dcim/platforms')
# endregion
# region #### Build Platform Lookup Dictionary
platform_lookup = {}
for netbox_platform in netbox_platforms:
    platform_lookup[netbox_platform['name']] = netbox_platform['id']
# endregion
# endregion
# region ### Match Virtual Chassis Masters to NetBox VC IDs
# region #### Get Virtual Chassis from NetBox
netbox_vc = export_netbox_data('dcim/virtual-chassis')
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
    device['ipv4']           = device['loginIpv4'] if device['loginIpv4'] else None
    device['ipv6']           = device['loginIpv6'] if device['loginIpv6'] else None
    device['master']         = None
    device['member']         = None
    device['vc_role']        = None
    device['vc_state']       = None
    device['vc_type']        = None
    device['vc_ver']         = None
    device['vc_image']       = None
    device['vc_hwver']       = None
    device['device_type_ID'] = None
    device['device_role_ID'] = None
    device['platform_ID']    = None
    device['site_ID']        = None
    device['vc_ID']          = None
#endregion
# region ## Append data from lookup tables
    device['device_type_ID'] = device_type_lookup.get(device['model'], None)
    if not device['device_type_ID']: # Attempt fuzzy match if exact match not found
        fuzzy_match = get_close_matches(device['model'], list(device_type_lookup.keys()), n=1, cutoff=modellnamesensitivity)
        if fuzzy_match:
            device['device_type_ID'] = device_type_lookup.get(fuzzy_match[0], None)
    device['device_role_ID'] = device_role_lookup.get(device['devType'], None)
    device['platform_ID'] = platform_lookup.get(device['family'], None)
    device['site_ID'] = site_lookup.get(device['siteName'], None)
    device['vc_ID'] = vc_lookup.get(device['hostname'], None)
    transform_list.append(device)
# endregion
# region ## Append additional data from IP Fabric
# region ### Add data to VSS members
new_devices = []
for device in ipf_vssmembers:
    vc_device = None
# region #### Find master device in Transform List
    for i in transform_list:
        if i['hostname'] == device['hostname']:
            vc_device = i
            break
# region #### Append VSS info if SN matches chassisSn - this is the master member
    if i['snHw'] == device['chassisSn']:
        vc_device['master'] = device['hostname']
        vc_device['member'] = device['chassisId']
        vc_device['vc_role'] = device['state']
        vc_device['vc_type'] = 'vss'
# endregion
# region #### Create new device entry for non-master members
    elif vc_device != None:
        for p in ipf_pns:
            if p['sn'] == device['sn']:
                if p['pid'] != "":
                    pn = p['pid']
                    break
        new_device = vc_device.copy()
        new_device['member']   = device['chassisId']
        new_device['model']    = pn
        new_device['sn']       = device['sn']
        new_device['vc_role']  = device['state']
        new_device['vc_type'] = 'vss'
        new_devices.append(new_device)
# endregion
# endregion
# region ### Add data to stack members
for device in ipf_stackmembers:
    vc_device = None
# region #### Find device in Transform List by hostname
    for i in transform_list:
        if i['snHw'] == device['sn']:
            vc_device = i
            break
# region #### Append data if SN matches memberSn - this is the master member
    if device['sn'] == device['memberSn']:
        vc_device['master']  = device['master']
        vc_device['member']  = device['member']
        vc_device['vc_role'] = device['role']
        vc_device['vc_type'] = 'stack'
 # endregion
# region #### Create new device entry for non-master members
    elif vc_device:
        new_device = vc_device.copy()
        new_device['member']   = device['member']
        new_device['model']    = device['pn']
        new_device['sn']       = device['memberSn']
        new_device['vc_role']  = device['role']
        vc_device['vc_type'] = 'stack'
        new_devices.append(new_device)
# endregion
# region #### Add new VC member devices to transform list
print(f'Adding {len(new_devices)} virtual chassis member devices to transform list.')
transform_list.extend(new_devices)
# endregion
# region #### Append member number to hostname for VC members
for i in transform_list:
    if i['member'] == '1' or i['member'] == None:
        pass
    else:
        i['hostname'] = f"{i['hostname']}/{i['member']}"
# endregion
# endregion
print(f'Processed {len(transform_list)} devices.')
# endregion
# region ## Check if devices already exist in NetBox
existing_devices = export_netbox_data('dcim/devices')
existing_device_names = [d['name'] for d in existing_devices]
for device in transform_list:
    device['new'] = None
    device['nb_id'] = None
    if device['hostname'] not in existing_device_names:
        device['new'] = True
    else:
        device['new'] = False
        device['nb_id'] = next((d['id'] for d in existing_devices if d['name'] == device['hostname']), None)
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
# region ## Initialize counters and lists
deviceSuccessCount = 0
deviceUpdateCount = 0
deviceFailCount = 0
deviceimportcounter = 0
interfaceUpdateCount = 0
interfaceFailCount = 0
moduleUpdateCount = 0
moduleFailCount = 0
interfaceErrors = []
moduleErrors = []
devicesfailed = []
vc_masters = []
vc_members = []
taskduration = []
# endregion
# region ## Import devices
url = f'{netboxbaseurl}dcim/devices/'
for device in transform_list:
    taskstart = datetime.now()
    devicename       = device['hostname']
    device_type      = device['device_type_ID']
    device_role      = device['device_role_ID']
    platform         = device['platform_ID']
    sn               = device['sn']
    site             = device['site_ID']
    status           = 'active'
    virtual_chassis  = device['vc_ID'] if device['vc_ID'] else None
    vc_position      = device['member']
    description      = f'Imported from IP Fabric'
    comments         = f'Updated on {starttime.strftime("%Y-%m-%d %H:%M:%S")}'
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
    if device['new'] == False:
        url = f'{netboxbaseurl}dcim/devices/{device["nb_id"]}/'
        r = requests.patch(url,headers=netboxheaders,json=payload,verify=False)
    else:
        r = requests.post(url,headers=netboxheaders,json=payload,verify=False)
    if r.status_code == 200 or r.status_code == 201:
        device_ID = r.json()['id']
        if device['nb_id'] != device_ID:
            device['nb_id'] = device_ID
        if device['vc_role'] == 'active':
            vc_masters.append([device["vc_ID"],device_ID])
        if device['member']:
            vc_members.append([device_ID, device['member']])
    if r.status_code == 201:
        deviceSuccessCount += 1
    elif r.status_code == 200:
        deviceUpdateCount += 1
    else:
        deviceFailCount += 1
        error_text = f'{devicename}, {r.text}, {payload}, {device}'
        devicesfailed.append(error_text)
    deviceimportcounter += 1
    taskend = datetime.now()
    taskduration.append((taskend - taskstart).total_seconds())
    remaining = sum(taskduration) / len(taskduration) * (len(transform_list) - deviceimportcounter)
    print(f'Import progress: [{"█" * int(deviceimportcounter/len(transform_list)*100):100}]{deviceimportcounter/len(transform_list)*100:.2f}% Complete - ({deviceimportcounter}/{len(transform_list)}) devices imported. Remaining: {remaining:.2f}s', end="\r")
print(f'\nDevice import process completed. Total Success: {deviceSuccessCount}, Updated: {deviceUpdateCount}, Failed: {deviceFailCount}')
# endregion
# endregion
# region ## Update VC masters with member IDs
print(f'Updating Virtual Chassis masters with member IDs.')
for i in vc_masters:
    vc = int(i[0])
    master = int(i[1])
    url = f'{netboxbaseurl}dcim/virtual-chassis/{vc}/'
    payload = {
        'master': master
    }
    r = requests.patch(url,headers=netboxheaders,json=payload,verify=False)
    if r.status_code != 200:
        print(f'Failed to update VC {vc} with master device ID {master}. Response: {r.text}')
    print(f'Update progress: {vc_masters.index(i)/len(vc_masters)*100:.2f}% Complete - ({vc_masters.index(i)}/{len(vc_masters)}) VC masters updated.', end="\r")
print(f'\nVirtual Chassis master update process completed.')
# endregion

# region ## Update interface naming for VC members
# region ### Define function to update interface and module names
def update_vc_members(update_type, device_id, member_number):
    Errors = []
    UpdateCount = 0
    FailCount = 0
    objects = export_netbox_data(f'dcim/{update_type}', netboxlimit=netboxlimit, filters=[f'device_id={device_id}'])
    for object in objects:
        name = object['name']
        current_name = re.match(r"^(\w*)(\d+)([\/\{\w+\}]{1,})$", name)
        if current_name:
            if int(current_name.group(2)) == member_number:
                continue  # already matches member number, skip update
            prefix = current_name.group(1)
            suffix = current_name.group(3)
            new_name = f'{prefix}{member_number}{suffix}'
            url = f'{netboxbaseurl}dcim/{update_type}/{object["id"]}/'
            payload = {
                'name': new_name,
                'display': new_name
            }
            if update_type == 'module-bays':
                payload['position'] = new_name
            r = requests.patch(url,headers=netboxheaders,json=payload,verify=False)
            if r.status_code != 200:
                Errors.append(f'{device_id}: {r.text}, {payload}, {object}')
                FailCount += 1
            else:
                UpdateCount += 1
            if r.status_code != 200:
                Errors.append(f'{device_id}: {r.text}, {payload}, {object}')
                FailCount += 1
            else:
                UpdateCount += 1
    return UpdateCount, FailCount, Errors
# endregion
# region ### Adjust interface and module names for VC members
vc_updates = 0
taskduration = []
print(f'Updating interface and module names for Virtual Chassis members.')
for member in vc_members:
    taskstart = datetime.now()
    device_id = int(member[0])
    member_number = int(member[1])
    if member_number == 1:  # Skip master member
        vc_updates += 1
        continue
    update_count, fail_count, errors = update_vc_members('interfaces', device_id, member_number)
    interfaceUpdateCount += update_count
    interfaceFailCount += fail_count
    interfaceErrors.extend(errors)
    update_count, fail_count, errors = update_vc_members('module-bays', device_id, member_number)
    moduleUpdateCount += update_count
    moduleFailCount += fail_count
    moduleErrors.extend(errors)
    vc_updates += 1
    taskend = datetime.now()
    taskduration.append((taskend - taskstart).total_seconds())
    remaining = sum(taskduration) / len(taskduration) * (len(vc_members) - vc_updates)
    print(f'Import progress: [{"█" * int(vc_updates/len(vc_members)*100):100}]{vc_updates/len(vc_members)*100:.2f}% Complete - ({vc_updates}/{len(vc_members)}) Virtual Chassis members updated. Remaining: {remaining:.2f}s', end="\r")
print(f'\nVirtual Chassis member interface and module name update process completed.')
print(f'Total interfaces updated: {interfaceUpdateCount}, failed: {interfaceFailCount}')
print(f'Total modules updated: {moduleUpdateCount}, failed: {moduleFailCount}')
# endregion
# endregion
# endregion
'''
Need to test linecard and uplink module updates as well. They should work as the line cards and uplinks are part of the device's module bays, while VC members are unique devices in NetBox.
'''

# region ## Change status for devices no longer in IP Fabric
'''
To be implemented - identify devices in NetBox that are no longer present in IP Fabric and change their status to 'decommissioned'.
Maybe this should be a separate script?
'''
# endregion
# endregion
# region # Summary and logging
endtime = datetime.now()
duration = endtime - starttime
print(f'Device import process completed. Start time: {starttime}, End time: {endtime}, Duration: {duration}')
print(f'Total devices processed: {len(transform_list)}')
print(f'Total devices successfully imported: {deviceSuccessCount}')
print(f'Total devices successfully updated: {deviceUpdateCount}')
print(f'Total devices failed to import: {deviceFailCount}')
with open(os.path.join(log_dir, 'errors_importdevices.csv'), 'w') as f:
    f.write('Device Name,Error Message,Payload,Device Details\n')
    for error_text in devicesfailed:
        f.write(f'{error_text}\n')
with open(os.path.join(log_dir, 'errors_missingdata.csv'), 'w') as file:
    file.write('Error Type,Count,Details\n')
    if required_fields_type_missing_count > 0:
        file.write(f'Device Type Missing,{required_fields_type_missing_count},"{set(missing_types)}"\n')
    if required_fields_role_missing_count > 0:
        file.write(f'Device Role Missing,{required_fields_role_missing_count},"{set(missing_roles)}"\n')
    if required_fields_site_missing_count > 0:
        file.write(f'Site Missing,{required_fields_site_missing_count},"{set(missing_sites)}"\n')
with open(os.path.join(log_dir, 'errors_interfaceupdates.csv'), 'w') as f:
    f.write('Device ID,Error Message,Payload,Object Details\n')
    for error_text in interfaceErrors:
        f.write(f'{error_text}\n')
with open(os.path.join(log_dir, 'errors_moduleupdates.csv'), 'w') as f:
    f.write('Device ID,Error Message,Payload,Object Details\n')
    for error_text in moduleErrors:
        f.write(f'{error_text}\n')
# endregion