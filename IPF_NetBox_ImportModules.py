'''
Script to import Modules from IP Fabric into NetBox.

Created by: Dan Kelcher
Date: January 20, 2025
'''

# region # Imports and setup
import json
import re
from dotenv import load_dotenv
import IPFloader
import IPFexporter
from NetBoxexporter import export_netbox_data
import NetBoxloader
import requests
import os
from pathlib import Path
import datetime
from difflib import get_close_matches

starttime = datetime.datetime.now()

# region ## Load IP Fabric configuration
ipfbaseurl, ipftoken, ipfheaders, ipflimit = IPFloader.load_ipf_config()
# endregion
# region ## Load NetBox configuration
netboxbaseurl, netboxtoken, netboxheaders, netboxlimit = NetBoxloader.load_netbox_config()
# endregion
# region ## Define paths
try:
    currentdir = Path(__file__).parent # Get directory of current script
except:
    currentdir = os.getcwd() # Fallback to current working directory
# endregion
# region ## Create log directory
starttime_str = starttime.strftime("%Y-%m-%d_%H-%M-%S")
log_dir=os.path.join(currentdir, 'Logs', 'IPF_NetBox_ImportModules', starttime_str)
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
modulelnamesensitivity = float(os.getenv('modulelnamesensitivity', '0.8'))
# endregion
# endregion

# region # Export modules from IP Fabric
ipf_modules = IPFexporter.export_ipf_data('inventory/pn', ['hostname', 'name', 'dscr', 'pid', 'sn'])
print(f'Total modules fetched from IP Fabric: {len(ipf_modules)}')
# endregion

# region # Collect data for module data translation
# region ## Get Module Type Library from NetBox to build a lookup table
netbox_moduletypes = []
netbox_moduletypes = export_netbox_data('dcim/module-types')
print(f'Total module types in NetBox: {len(netbox_moduletypes)}')
# endregion
# region ## Get the Device IDs from NetBox to build a lookup table
netbox_devices = []
netbox_devices = export_netbox_data('dcim/devices')
print(f'Total devices in NetBox: {len(netbox_devices)}')
# endregion
# region ## Get the Module Bays from NetBox to build a lookup table
netbox_module_bays = []
netbox_module_bays = export_netbox_data('dcim/module-bays')
print(f'Total module bays in NetBox: {len(netbox_module_bays)}')
# endregion
# region ## Get VC member data from IPF
ipf_vcmembers = IPFexporter.export_ipf_data('platforms/stack/members', ['master', 'member', 'sn'])
print(f'Total VC members fetched from IP Fabric: {len(ipf_vcmembers)}')
# endregion
# region # Transform data
# region ## Filter out modules that are not really modules
valid_modules = []
for i in ipf_modules:
    try:
         if i['name'] not in i['pid'] and i['dscr'] not in i['pid'] and 'ap' not in i['name'].lower() and 'stack' not in i['pid'].lower():
            print(f'{i['name']},{i['pid']}')
            valid_modules.append(i)
    except:
        pass
print(f'Total valid modules to import: {len(valid_modules)}')
# endregion
# region ## Identify and mark modules that are part of Virtual Chassis
vc_switch_regex = re.compile(r"^Switch\s?(\d+)", re.IGNORECASE) # matches for power supplies, fans, etc.
vc_interface_regex = re.compile(r"^\w{2,}(\d+)\/", re.IGNORECASE) # matches for interfaces
vc_updates = 0
for module in valid_modules:
    module['vcmembername'] = None
    if vc_switch_regex.match(module['name']):
        memberid = vc_switch_regex.match(module['name']).group(1)
        if int(memberid) > 1:
            module['vcmembername'] = f'{module["hostname"]}/{memberid}'
            vc_updates += 1
    elif vc_interface_regex.match(module['name']):
        memberid = vc_interface_regex.match(module['name']).group(1)
        if int(memberid) > 1:
            module['vcmembername'] = f'{module["hostname"]}/{memberid}'
            vc_updates += 1
print(f'Total modules updated for VC membership: {vc_updates}')
# endregion
# region ## Split out module types
# region ### Classify modules into buckets
module_buckets = {
    'sfp': [],
    'disk': [],
    'fan': [],
    'network': [],
    'power': [],
    'supervisor': [],
    'other': []
}
# endregion
# region ### Define sorting criteria
SFP_regex = re.compile(r"^\w{2,}\/\d", re.IGNORECASE)
module_keywords = [ 
    # precedence matters: first match wins
    # Category MUST match keys in module_buckets
    # Category, {Keywords}
    # ("module_type", {"keyword1", "keyword2"})
    ("sfp", {"sfp", "gbic", "glc"}),          
    ("disk", {"disk", "ssd"}),
    ("fan", {"fan"}),
    ("network", {"uplink", "fabric"}),
    ("power", {"power"}),
    ("supervisor", {"supervisor"}),
]
# endregion
# region ### Classify function
def classify_module(module: dict) -> str:
    name = (module.get('name') or '')
    pid  = (module.get('pid') or '')
    dscr = (module.get('dscr') or '')
# region #### Special cases first - SFPs by regex
    if SFP_regex.match(name):
        return "sfp"
# endregion
# region #### Keyword matching
    combined = f"{name} {pid} {dscr}".lower()
    for category, keywords in module_keywords:
        if any(k in combined for k in keywords):
            return category
# endregion
# region #### Default to 'other'
    return "other"
# endregion
# endregion

# region ### Sort modules into buckets
for module in valid_modules:
    try:
        cat = classify_module(module)
    except:
        cat = "other"  # handle unexpected types gracefully
    module['category'] = cat
    module_buckets[cat].append(module)
# endregion
# region ### Create separate lists for each module type
for i in module_buckets.keys():
    exec(f"{i}_modules = module_buckets['{i}']")
# endregion
# region ### Print counts for each module type
print(f'There are {len(module_buckets.keys())} module types identified.')
print('Module type counts:')
for bucket, modules in module_buckets.items():
    print(f'Total {bucket.upper()} modules identified: {len(modules)}')
# endregion
# endregion
'''
NOTE
Need to determine how to handle modules with no PID, or with "unspecified" PID.
Particularly for SFPs, many may not have a PID listed in IP Fabric. Perhaps create a generic SFP module type in NetBox to use for these cases?
'''

# region ## Append module type ID and Device ID from NetBox to module data from IP Fabric
# region ### Define function to match and prepare module data for import
def module_import(source_modules):
    error_modules = ['hostname, name, pid, sn, dscr, module_type_id, device_id, module_bay_id, category']
    modules_to_create = []
    for module in source_modules:
        module_type_id = None
    # region #### Find best matching module type in NetBox
        pid_matches = [mt for mt in netbox_moduletypes if mt['part_number'] and module['pid'] and mt['part_number'].lower() == module['pid'].lower()]
        if pid_matches:
            module_type_id = pid_matches[0]['id']
        else:
            name_matches = [mt for mt in netbox_moduletypes if mt['model'] and module['name'] and mt['model'].lower() == module['name'].lower()]
            if name_matches:
                module_type_id = name_matches[0]['id']
            else:
                possible_names = [mt['display'] for mt in netbox_moduletypes if mt['display']]
                close_matches = get_close_matches(module['name'], possible_names, n=1, cutoff=modulelnamesensitivity)
                if close_matches:
                    best_match_name = close_matches[0]
                    best_match = next((mt for mt in netbox_moduletypes if mt['display'] == best_match_name), None)
                    if best_match:
                        module_type_id = best_match['id']
    # endregion
    # region #### Find Device ID in NetBox
        device_id = None
        device_matches = None
        if module['vcmembername']:
            device_matches = [dev for dev in netbox_devices if dev['name'] and module['vcmembername'] and dev['name'].lower() == module['vcmembername'].lower()]
            module['hostname'] = module['vcmembername'] # use VC member name
        if not device_matches:
            device_matches = [dev for dev in netbox_devices if dev['name'] and module['hostname'] and dev['name'].lower() == module['hostname'].lower()]     
        if device_matches:
            device_id = device_matches[0]['id']
        
    # endregion
    # region #### Find Module Bay ID in NetBox
        module_bay_id = None
        if device_id:
            device_mbs = [mb for mb in netbox_module_bays if mb.get('device', {}).get('id') == device_id]
            target_name = (module.get('name') or '').strip()
    # region ##### Match by module bay name if possible, using close matches from name, cat, dscr, or pid

    # region ###### Exact name match first (most bays use stable names like 'GigabitEthernet1/7', 'Te1/1/8', 'Slot 6', etc.)
            exact_mb = next((mb for mb in device_mbs if (mb.get('name') or '').strip() == target_name), None)
            if exact_mb:
                module_bay_id = exact_mb['id']
    # endregion
    # region ###### If no exact match, try matching by the last numeric segment (path suffix) or by explicit 'position'
            if not module_bay_id and target_name:        
                nums = re.findall(r'(\d+)', target_name) # Extract all numbers from the target name and use the last as a strong hint
                last_seg = nums[-1] if nums else None
                if last_seg:
                    ends_with = [
                        mb for mb in device_mbs
                        if (mb.get('name') or '').strip().endswith(f'/{last_seg}')
                    ]
                    # Candidates whose position equals last_seg (many bays store 'position' that mirrors the final index)
                    pos_match = [mb for mb in device_mbs if str(mb.get('position')) == str(last_seg)]
                    # Prefer a unique deterministic match
                    if len(ends_with) == 1:
                        module_bay_id = ends_with[0]['id']
                    elif len(pos_match) == 1:
                        module_bay_id = pos_match[0]['id']
    # endregion
    # region ###### Optional fuzzy fallback controlled by your env sensitivity (only used if both deterministic methods fail)
            if not module_bay_id and target_name:
                candidates = [(mb.get('name') or '').strip() for mb in device_mbs if mb.get('name')]
                matches = get_close_matches(target_name, candidates, n=1, cutoff=modulelnamesensitivity)
                if matches:
                    chosen = next((mb for mb in device_mbs if (mb.get('name') or '').strip() == matches[0]), None)
                    if chosen:
                        module_bay_id = chosen['id']
    # endregion
    # endregion
    # region #### Prepare module data for creation in NetBox
        data = {
            "hostname": module['hostname'], # use VC member name if applicable, otherwise regular hostname
            "name": module['name'],
            "pid": module['pid'],
            "sn": module['sn'],
            "dscr": module['dscr'],
            "module_type_id": module_type_id, # required
            "device_id": device_id, # required
            "module_bay_id": module_bay_id, # required
            "category": module['category']
        }
        if module_type_id and device_id and module_bay_id: # all required fields present
            modules_to_create.append(data)
        else:
            error_text = f'{data["hostname"]},{data["name"]},{data["pid"]},{data["sn"]},{data["dscr"]},{data["module_type_id"]},{data["device_id"]},{data["module_bay_id"]},{data["category"]}'
            error_modules.append(error_text)
    return modules_to_create, error_modules
# endregion
# endregion
# region ## Process each module type bucket
total_modules_to_create = 0
total_modules_with_errors = 0
full_modules = []
for i in module_buckets.keys():
    print(f'Processing {len(module_buckets[i])} {i} modules...')
    command = f"{i}_modules_to_create, errors_{i}_modules = module_import({i}_modules)"
    exec(command)
    print(f'Total {i} modules to create: {len(eval(f"{i}_modules_to_create"))}')
    print(f'Total {i} modules with errors: {len(eval(f"errors_{i}_modules"))-1}') # Subtract 1 for header
    total_modules_to_create += len(eval(f"{i}_modules_to_create"))
    total_modules_with_errors += len(eval(f"errors_{i}_modules")) - 1 # Subtract 1 for header
    file = os.path.join(log_dir, i + '_modules_with_errors.csv')
    with open(file, 'w') as f:
        f.write('\n'.join(eval(f"errors_{i}_modules")))
print(f'Total modules to create across all types: {total_modules_to_create}')
print(f'Total modules with errors across all types: {total_modules_with_errors}')
# endregion


'''
NOTE Non-SPF modules imported first because modules may have SFPs installed in them.
'''

'''
NOTE
Need to test 'replicate_components and 'adopt_components' options when creating modules in NetBox.
It seems that if 'replicate_components' is enabled (default), and 'adopt_components' is disabled, then if a matching interface already exists when a module is added, it updates the existing interface.
Meaning that devices with SFP slots could have an SFP interface created, and then when the SFP module is added, the existing interface is updated rather than creating a duplicate.
Need to test if the interface configuration is preserved in this case (eg. description, enabled/disabled state, etc.)
'''

# region # Load modules into NetBox
for i in module_buckets.keys():
    modules_to_create = eval(f'{i}_modules_to_create')
    print(f'Creating {len(modules_to_create)} {i} modules in NetBox...')
    for module in modules_to_create:
        url = f'{netboxbaseurl}dcim/modules/'
        payload = {
            "device": module["device_id"],
            "module_bay": module["module_bay_id"],
            "module_type": module["module_type_id"],
            "status": "active",
            "serial": module["sn"],
            "description": module["dscr"],
            "comments": f'Imported from IP Fabric.'
        }
        r = requests.post(url,headers=netboxheaders,json=payload,verify=False)
        if r.status_code == 201:
            print(f'Successfully created module {module["name"]} on device {module["hostname"]}.')
        else:
            print(f'Failed to create module {module["name"]} on device {module["hostname"]}. Status code: {r.status_code}, Response: {r.text}')
            error_text = f'{module["hostname"]},{module["name"]},{module["pid"]},{module["sn"]},{module["dscr"]},{module["module_type_id"]},{module["device_id"]},{module["module_bay_id"]},{i}'
            with open(os.path.join(log_dir, f'error_{i}_modules_import.csv'), 'a') as f:
                f.write(error_text + '\n')
# endregion
# region # Summary
endtime = datetime.datetime.now()
print('Module import complete.')
print(f'Start time: {starttime}')
print(f'End time: {endtime}')
duration = endtime - starttime
print(f'Duration: {duration}')
# endregion