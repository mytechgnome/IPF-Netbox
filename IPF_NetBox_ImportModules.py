'''
Script to import Modules from IP Fabric into NetBox.
Created by: Dan Kelcher
Date: January 20, 2025
'''

# region # Imports and setup
import yaml
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
# endregion

# region ## Load IP Fabric configuration
ipfbaseurl, ipftoken, ipfheaders, ipflimit = IPFloader.load_ipf_config()
# endregion

# region ## Load NetBox configuration
netboxbaseurl, netboxtoken, netboxheaders, netboxlimit = NetBoxloader.load_netbox_config()
# endregion

# region ## Define paths
try:
    currentdir = Path(__file__).parent  # Get directory of current script
except:
    currentdir = os.getcwd()  # Fallback to current working directory
# endregion

# region ## Create log directory
starttime_str = starttime.strftime("%Y-%m-%d_%H-%M-%S")
log_dir = os.path.join(currentdir, 'Logs', 'IPF_NetBox_ImportModules', starttime_str)
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

# region ## Check for IPFModuleMapping.yaml file and load rules
yaml_path = os.path.join(currentdir, 'DataSources', 'IPFModuleMapping.yaml')
if not os.path.isfile(yaml_path):
    print('IPFModuleMapping.yaml file not found in DataSources directory. Please add the YAML with module mapping rules.')
with open(yaml_path, 'r',encoding='utf-8') as f:
    module_rules = yaml.safe_load(f)
# Validate essentials
if 'categories' not in module_rules or 'globals' not in module_rules:
    print('IPFModuleMapping.yaml is missing required top-level keys: "globals" and/or "categories".')
# endregion

# region ## Export modules from IP Fabric
ipf_modules = IPFexporter.export_ipf_data('inventory/pn', ['hostname', 'name', 'dscr', 'pid', 'sn', 'deviceSn', 'model'])
print(f'Total modules fetched from IP Fabric: {len(ipf_modules)}')
# endregion

# region ## Collect data for module data translation
# region ### Get Module Type Library from NetBox to build a lookup table
netbox_moduletypes = []
netbox_moduletypes = export_netbox_data('dcim/module-types')
print(f'Total module types in NetBox: {len(netbox_moduletypes)}')
# endregion

# region ### Get the Device IDs from NetBox to build a lookup table
netbox_devices = []
netbox_devices = export_netbox_data('dcim/devices')
print(f'Total devices in NetBox: {len(netbox_devices)}')
# endregion

# region ### Get the Module Bays from NetBox to build a lookup table
netbox_module_bays = []
netbox_module_bays = export_netbox_data('dcim/module-bays')
print(f'Total module bays in NetBox: {len(netbox_module_bays)}')
# endregion

# region ### Get VC member data from IPF
ipf_vcmembers = IPFexporter.export_ipf_data('platforms/stack/members', ['master', 'member', 'sn'])
print(f'Total VC members fetched from IP Fabric: {len(ipf_vcmembers)}')
# endregion

# region ## Transform data
# region ### Filter out modules that are not really modules
valid_modules = []
for i in ipf_modules:
    try:
        if i['sn'] == i['deviceSn']:
            continue  # skip base device entries
        if i['pid'] == i['dscr']:
            continue  # skip entries where PID equals description
        if i['pid'] == i['model']:
            continue  # skip entries where PID equals model
        if 'Fabric Extender Module' in i['dscr']:
            continue  # skip Fabric Extender Modules
        valid_modules.append(i)
        if 'stack' in i['dscr'].lower():
            continue  # skip modules with "stack" in description (stack cables are included in modules from IPF)
    except:
        pass
print(f'Total valid modules to import: {len(valid_modules)}')
# endregion

# region ### Identify and mark modules that are part of Virtual Chassis
vc_switch_regex = re.compile(r"^Switch\s?\(?(\d+)\)?", re.IGNORECASE)  # matches Switch N or Switch (N)
vc_interface_regex = re.compile(r"^\w{2,}(\d+)\/", re.IGNORECASE)      # matches TeN/..., GiN/..., etc.

vc_updates = 0
for module in valid_modules:
    module['vcmembername'] = None
    m_sw = vc_switch_regex.match(module['name'])
    if m_sw:
        memberid = m_sw.group(1)
        if int(memberid) > 1:
            module['vcmembername'] = f'{module["hostname"]}/{memberid}'
            vc_updates += 1
    else:
        m_if = vc_interface_regex.match(module['name'])
        if m_if:
            memberid = m_if.group(1)
            if int(memberid) > 1:
                module['vcmembername'] = f'{module["hostname"]}/{memberid}'
                vc_updates += 1
print(f'Total modules updated for VC membership: {vc_updates}')
# endregion

# region ### Define sorting criteria (from YAML)
# Compile per-category keyword sets & pattern regexes
category_keywords = {}
category_patterns = {}

for cat_name, cat_def in module_rules.get('categories', {}).items():
    # keywords
    kws = set((cat_def.get('keywords') or []))
    category_keywords[cat_name] = kws

    # ipf_patterns (regex strings)
    pats = cat_def.get('ipf_patterns') or []
    category_patterns[cat_name] = [re.compile(p, re.IGNORECASE) for p in pats]

# Create module buckets
module_buckets = {k: [] for k in category_keywords.keys()}
module_buckets["other"] = []
# endregion

# region ### Classification via YAML (patterns -> keywords -> other)
def classify_module(module: dict) -> str:
    name = (module.get('name') or '')
    pid  = (module.get('pid')  or '')
    dscr = (module.get('dscr') or '')
    combined = f"{name} {pid} {dscr}".lower()

    # 1) Regex pattern match per category (YAML-driven)
    for cat_name, compiled_list in category_patterns.items():
        for rgx in compiled_list:
            if rgx.search(name):
                return cat_name

    # 2) Keyword match per category (YAML-driven)
    for cat_name, kws in category_keywords.items():
        if any(k in combined for k in kws):
            return cat_name

    # 3) Default
    return "other"
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
Blank:
 1000BaseLX SFP
 1000BaseSX SFP
Unspecified:
 1000BaseLH
 1000BaseSX
 1000BaseT
'''

# region ### YAML-driven helpers (normalization & candidate generation)
def _apply_global_transforms(s: str) -> str:
    """Apply globals.transforms from YAML to the raw IPF name."""
    s2 = s or ''
    transforms = (module_rules.get('globals', {}).get('transforms') or [])
    for t in transforms:
        # Expect dict entries: {'regex': '...', 'replace': '...'}
        rx = t.get('regex'); rp = t.get('replace')
        if rx is not None and rp is not None:
            s2 = re.sub(rx, rp, s2, flags=re.IGNORECASE)
    # collapse spaces
    s2 = re.sub(r'\s+', ' ', s2).strip()
    return s2

def _expand_prefix(pfx: str) -> str:
    """Map interface prefix abbreviations using globals.prefix_map."""
    pmap = module_rules.get('globals', {}).get('prefix_map') or {}
    return pmap.get(pfx, pfx)

def _normalize_with_yaml(raw_name: str, category: str) -> dict:
    """
    Normalize name per YAML rules; return dict with useful fields:
      'normalized'  -> string normalized name
      'groups'      -> dict of named regex groups (pos/slot/path/etc.) from the first matching pattern
      'canon_prefix'-> expanded interface prefix (if applicable)
    """
    s = _apply_global_transforms(raw_name)
    out = {'normalized': s, 'groups': {}, 'canon_prefix': ''}

    # Try category-specific patterns to capture groups
    patterns = category_patterns.get(category, [])
    for rgx in patterns:
        m = rgx.search(s)
        if m:
            out['groups'] = m.groupdict()
            break

    # Expand interface prefix for SFP category where applicable
    if category == 'sfp':
        m_if = re.match(r'^(?P<pfx>[A-Za-z]+)(?P<path>\d+(?:/\d+)+)$', s)
        if m_if:
            canon = _expand_prefix(m_if.group('pfx'))
            out['canon_prefix'] = canon
            out['groups']['path'] = m_if.group('path')

    return out

def _build_candidates(category: str, norm: dict) -> list:
    """
    Build candidate NetBox bay names per YAML synonyms.
    Tokens supported: {POS}, {SLOT}, {PATH}, {CANON_PREFIX}
    """
    syns = (module_rules.get('categories', {}).get(category, {}).get('synonyms') or [])
    g = norm.get('groups') or {}
    canon_prefix = norm.get('canon_prefix') or ''
    # Normalize letter case for POS if present
    if 'pos' in g:
        # letter case upper; keep numerics as-is
        if re.fullmatch(r'[A-Za-z]+', g['pos'] or ''):
            g['pos'] = (g['pos'] or '').upper()

    tokens = {
        'POS': g.get('pos', ''),
        'SLOT': g.get('slot', ''),
        'PATH': g.get('path', ''),
        'CANON_PREFIX': canon_prefix,
    }
    cands = []
    for tmpl in syns:
        try:
            cands.append(tmpl.format(**tokens))
        except Exception:
            # ignore bad template
            pass

    # For SFP, also add fully-formed long prefix path if detected
    if category == 'sfp' and canon_prefix and g.get('path'):
        cands.append(f'{canon_prefix}{g["path"]}')

    # If synonyms yielded nothing, fall back to normalized raw name
    if not cands and norm.get('normalized'):
        cands.append(norm['normalized'])

    # Deduplicate and return
    return [c.strip() for c in dict.fromkeys(cands) if c.strip()]
# endregion

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
            module['hostname'] = module['vcmembername']  # use VC member name
        if not device_matches:
            device_matches = [dev for dev in netbox_devices if dev['name'] and module['hostname'] and dev['name'].lower() == module['hostname'].lower()]
        if device_matches:
            device_id = device_matches[0]['id']
        # endregion

        # region #### Find Module Bay ID in NetBox (YAML-driven)
        module_bay_id = None
        if device_id:
            device_mbs = [mb for mb in netbox_module_bays if mb.get('device', {}).get('id') == device_id]

            raw_name = (module.get('name') or '').strip()
            category = module.get('category') or 'other'

            # Ignore FEX for now (already filtered earlier), proceed for others
            norm = _normalize_with_yaml(raw_name, category)
            candidates = _build_candidates(category, norm)

            # 1) Exact match on any candidate
            for cand in candidates:
                exact_mb = next((mb for mb in device_mbs if (mb.get('name') or '').strip() == cand), None)
                if exact_mb:
                    module_bay_id = exact_mb['id']
                    break

            # 2) Ends-with match using last numeric segment (e.g., trailing "/8")
            if not module_bay_id and candidates:
                # choose first candidate that has numbers
                target = next((c for c in candidates if re.search(r'(\d+)', c)), '')
                nums = re.findall(r'(\d+)', target)
                last_seg = nums[-1] if nums else None
                if last_seg:
                    ends_with = [
                        mb for mb in device_mbs
                        if (mb.get('name') or '').strip().endswith(f'/{last_seg}')
                    ]
                    if len(ends_with) == 1:
                        module_bay_id = ends_with[0]['id']
                    else:
                        # 2b) position field equals last_seg
                        pos_match = [mb for mb in device_mbs if str(mb.get('position')) == str(last_seg)]
                        if len(pos_match) == 1:
                            module_bay_id = pos_match[0]['id']

            # 3) Conservative fuzzy fallback against all candidates
            if not module_bay_id and candidates:
                names = [(mb.get('name') or '').strip() for mb in device_mbs if mb.get('name')]
                for cand in candidates[:10]:  # bound the fuzz
                    m = get_close_matches(cand, names, n=1, cutoff=modulelnamesensitivity)
                    if m:
                        chosen = next((mb for mb in device_mbs if (mb.get('name') or '').strip() == m[0]), None)
                        if chosen:
                            module_bay_id = chosen['id']
                            break
        # endregion

        # region #### Prepare module data for creation in NetBox
        data = {
            "hostname": module['hostname'],  # use VC member name if applicable, otherwise regular hostname
            "name": module['name'],
            "pid": module['pid'],
            "sn": module['sn'],
            "dscr": module['dscr'],
            "module_type_id": module_type_id,  # required
            "device_id": device_id,            # required
            "module_bay_id": module_bay_id,    # required
            "category": module['category']
        }
        if module_type_id and device_id and module_bay_id:  # all required fields present
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
    print(f'Total {i} modules with errors: {len(eval(f"errors_{i}_modules"))-1}')  # Subtract 1 for header
    total_modules_to_create += len(eval(f"{i}_modules_to_create"))
    total_modules_with_errors += len(eval(f"errors_{i}_modules")) - 1  # Subtract 1 for header
    file = os.path.join(log_dir, i + '_modules_with_errors.csv')
    with open(file, 'w') as f:
        f.write('\n'.join(eval(f"errors_{i}_modules")))
print(f'Total modules to create across all types: {total_modules_to_create}')
print(f'Total modules with errors across all types: {total_modules_with_errors}')
# endregion
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
    taskduration = []
    importCounter = 0
    for module in modules_to_create:
        taskstart = datetime.datetime.now()
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
        r = requests.post(url, headers=netboxheaders, json=payload, verify=False)
        if r.status_code != 201:
            error_text = f'{module["hostname"]},{module["name"]},{module["pid"]},{module["sn"]},{module["dscr"]},{module["module_type_id"]},{module["device_id"]},{module["module_bay_id"]},{i}'
            with open(os.path.join(log_dir, f'error_{i}_modules_import.csv'), 'a') as f:
                f.write(error_text + '\n')
        importCounter += 1
        taskend = datetime.datetime.now()
        taskduration.append((taskend - taskstart).total_seconds())
        remaining = sum(taskduration) / len(taskduration) * (len(modules_to_create) - importCounter)
        print(f'Import progress: [{"█" * int(importCounter/len(modules_to_create)*100):100}]{importCounter/len(modules_to_create)*100:.2f}% Complete - ({importCounter}/{len(modules_to_create)}) {i} modules imported. Remaining: {remaining:.2f}s', end="\r")
    print(f'\n{i} module import process completed.')
# endregion
print('All module types import process completed.')


# region # Update module bay and interface names for VC member modules in NetBox based on IPF data
print('Starting VC member module interface name update process...')
interfaceErrors = []
moduleErrors = []
interfaceUpdateCount = 0
moduleUpdateCount = 0
interfaceFailCount = 0
moduleFailCount = 0
vc_members = []
for i in netbox_devices:
    if i['name'] and re.search(r'/\d+$', i['name']):
        vc_members.append((i['id'], re.search(r'/(\d+)$', i['name']).group(1)))
# region ## Define function to update interface and module names
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
# region ## Adjust interface and module names for VC members
vc_updates = 0
taskduration = []
print(f'Updating interface and module names for Virtual Chassis members.')
for member in vc_members:
    taskstart = datetime.datetime.now()
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
    taskend = datetime.datetime.now()
    taskduration.append((taskend - taskstart).total_seconds())
    remaining = sum(taskduration) / len(taskduration) * (len(vc_members) - vc_updates)
    print(f'Import progress: [{"█" * int(vc_updates/len(vc_members)*100):100}]{vc_updates/len(vc_members)*100:.2f}% Complete - ({vc_updates}/{len(vc_members)}) Virtual Chassis members updated. Remaining: {remaining:.2f}s', end="\r")
print(f'\nVirtual Chassis member interface and module name update process completed.')
print(f'Total interfaces updated: {interfaceUpdateCount}, failed: {interfaceFailCount}')
print(f'Total modules updated: {moduleUpdateCount}, failed: {moduleFailCount}')
# endregion
# endregion





# region # Summary
endtime = datetime.datetime.now()
print('Module import complete.')
print(f'Start time: {starttime}')
print(f'End time: {endtime}')
duration = endtime - starttime
print(f'Duration: {duration}')
# endregion
