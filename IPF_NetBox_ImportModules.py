'''
Import modules into NetBox using IPFModuleMapping.yaml to define module bay mapping

Created by: Dan Kelcher
Date: January 20th, 2025
'''

# region # Imports and setup
import os
import re
import yaml
import requests
from IPFexporter import export_ipf_data
from IPFloader import load_ipf_config
from NetBoxloader import load_netbox_config
from NetBoxexporter import export_netbox_data
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from difflib import get_close_matches

starttime = datetime.now()

# region ## Load .env and variables
if not os.path.isfile('.env'):
    import CreateEnvFile; CreateEnvFile.create_env_file()
load_dotenv(override=True)
modulelnamesensitivity = float(os.getenv('modulelnamesensitivity', '0.8'))
replicate_components = os.getenv('replicate_components', 'true').lower() == 'true'
adopt_components     = os.getenv('adopt_components', 'true').lower() == 'true'
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
# region ## Define paths
try:
    currentdir = Path(__file__).parent
except Exception:
    currentdir = Path(os.getcwd())
# endregion
# region ## Create log directory
starttime_str = starttime.strftime("%Y-%m-%d_%H-%M-%S")
log_dir = currentdir / 'Logs' / 'IPF_NetBox_ImportModules' / starttime_str
log_dir.mkdir(parents=True, exist_ok=True)
# endregion
# region ## Load module mapping rules from YAML
yaml_path = currentdir / 'DataSources' / 'IPFModuleMapping.yaml'
with yaml_path.open('r', encoding='utf-8') as f:
    module_rules = yaml.safe_load(f)
# endregion
# endregion

# region # Export Modules from IP Fabric and related data for transformation
print("Exporting module and related data from IP Fabric and NetBox...")
ipf_modules        = export_ipf_data('inventory/pn', ['hostname','name','dscr','pid','sn','deviceSn','model'])
ipf_vcmembers      = export_ipf_data('platforms/stack/members', ['master','member','sn'])
netbox_moduletypes = export_netbox_data('dcim/module-types')
netbox_devices     = export_netbox_data('dcim/devices')
netbox_module_bays = export_netbox_data('dcim/module-bays')
print(f'Total modules fetched from IP Fabric: {len(ipf_modules)}')
print(f'Total module bays fetched from NetBox: {len(netbox_module_bays)}')
# endregion

# region # Transform Modules and prepare for import
print("Transforming module data and preparing for import...")
# region ## Define helper functions for transformation and import
prefix_map   = module_rules.get('globals', {}).get('prefix_map') or {}
transforms   = module_rules.get('globals', {}).get('transforms') or []
PID_ALIAS    = module_rules.get('globals', {}).get('pid_aliases') or {}
DSCR_TO_PID  = module_rules.get('globals', {}).get('dscr_to_pid') or {}

category_defs     = module_rules.get('categories', {})
category_patterns = {c:[re.compile(p, re.IGNORECASE) for p in (d.get('ipf_patterns') or [])] for c,d in category_defs.items()}
category_keywords = {c:set(d.get('keywords') or []) for c,d in category_defs.items()}

FUZZY_CUTOFF = {'sfp':0.90,'power':0.80,'fan':0.80,'supervisor':0.85,'network':0.80,'other':0.75}

def apply_transforms(s):
    out = s or ''
    for t in transforms:
        rx = t.get('regex'); rp = t.get('replace')
        if rx is not None and rp is not None:
            out = re.sub(rx, rp, out, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', out).strip()

def expand_prefix(pfx):
    return prefix_map.get(pfx, pfx)

def normalize_with_yaml(raw_name, category):
    s = apply_transforms(raw_name)
    out = {'normalized': s, 'groups': {}, 'canon_prefix': ''}
    for rgx in category_patterns.get(category, []):
        m = rgx.search(s)
        if m:
            out['groups'] = m.groupdict(); break
    if category == 'sfp':
        m_if = re.match(r'^(?P<pfx>[A-Za-z]+)(?P<path>\d+(?:/\d+)+)$', s)
        if m_if:
            out['canon_prefix'] = expand_prefix(m_if.group('pfx'))
            out['groups']['path'] = m_if.group('path')
    return out

def build_candidates(category, norm):
    syns = (category_defs.get(category, {}).get('synonyms') or [])
    g    = norm.get('groups') or {}
    canon= norm.get('canon_prefix') or ''
    if 'pos' in g and re.fullmatch(r'[A-Za-z]+', g['pos'] or ''):
        g['pos'] = (g['pos'] or '').upper()
    tokens = {'POS': g.get('pos',''), 'SLOT': g.get('slot',''), 'PATH': g.get('path',''), 'CANON_PREFIX': canon}
    cands = []
    for tmpl in syns:
        try: cands.append(tmpl.format(**tokens))
        except: pass
    if category == 'sfp' and canon and g.get('path'):
        cands.append(f"{canon}{g['path']}")
    if not cands and norm.get('normalized'): cands.append(norm['normalized'])
    return [c.strip() for c in dict.fromkeys(cands) if c.strip()]

def classify_module(mod):
    name     = mod.get('name') or ''
    combined = f"{name} {(mod.get('pid') or '')} {(mod.get('dscr') or '')}".lower()
    # regex first
    for cat, pats in category_patterns.items():
        for rgx in pats:
            if rgx.search(name): return cat
    # keywords second
    for cat, kws in category_keywords.items():
        if any(k in combined for k in kws): return cat
    return 'other'
# endregion
# region ## Filter out invalid or unmapped modules based on rules and heuristics
valid_modules = []
for i in ipf_modules:
    try:
        if i['sn']   == i['deviceSn']:            continue
        if i['pid']  == i['dscr']:               continue
        if i['pid']  == i['model']:              continue
        if 'Fabric Extender Module' in (i['dscr'] or ''):  continue
        if 'stack' in (i['dscr'] or '').lower(): continue
        valid_modules.append(i)
    except Exception:
        pass
print(f'Total valid modules after filtering: {len(valid_modules)}')
# endregion
# region ## Enrich module data with VC member info where applicable
print("Enriching module data...")
vc_switch_regex     = re.compile(r"^Switch\s*-?\s*(\d+)\b", re.IGNORECASE)
vc_member_from_port = re.compile(r"^(?:Te|Gi|Hu|Twe|Eth|Ethernet|TenGigabitEthernet|GigabitEthernet|HundredGigE|TwentyFiveGigE)(\d+)/", re.IGNORECASE)

for m in valid_modules:
    name = m.get('name') or ''
    m_sw = vc_switch_regex.match(name)
    m_if = vc_member_from_port.match(name)
    memberid = m_sw.group(1) if m_sw else (m_if.group(1) if m_if else None)
    m['vcmembername'] = f"{m['hostname']}/{memberid}" if (memberid and int(memberid)>1) else None
# endregion

# region ## Build lookup tables for matching module types, devices, and module bays
devices_by_name = { (d.get('name') or '').lower(): d.get('id') for d in netbox_devices if d.get('name') }

moduletypes_by_part, moduletypes_by_model = {}, {}
for mt in netbox_moduletypes:
    pn  = (mt.get('part_number') or '').lower()
    mdl = (mt.get('model')       or '').lower()
    if pn:  moduletypes_by_part[pn] = mt
    if mdl: moduletypes_by_model[mdl] = mt

module_bays_by_device = {}
for mb in netbox_module_bays:
    did = mb.get('device', {}).get('id')
    if not did: continue
    module_bays_by_device.setdefault(did, {'by_name': {}, 'by_pos': {}})
    nm  = (mb.get('name') or '').strip()
    pos = mb.get('position')
    if nm:
        module_bays_by_device[did]['by_name'][nm.lower()] = mb
    if pos is not None:
        module_bays_by_device[did]['by_pos'][str(pos)] = mb
# endregion
# region ## Build lookup for VC member names to device IDs
def normalize_pid(pid):
    p = (pid or '').strip().lower()
    if not p or p in ('unspecified','not'): return ''
    return PID_ALIAS.get(p, p)  # keep variants exact unless you add aliases

def derive_pid_from_dscr(dscr):
    d = (dscr or '').strip()
    if not d: return ''
    for key, pid in DSCR_TO_PID.items():
        if key.lower() in d.lower(): return (pid or '').strip()
    return ''

def match_module_type(module):
    # 1) exact by normalized PID
    npid = normalize_pid(module.get('pid',''))
    if npid and npid in moduletypes_by_part: return moduletypes_by_part[npid]['id']
    # 2) description fallback
    if not npid:
        npid = derive_pid_from_dscr(module.get('dscr'))
        if npid and npid.lower() in moduletypes_by_part: return moduletypes_by_part[npid.lower()]['id']
    # 3) exact by model/name
    mdl = (module.get('name') or '').lower()
    if mdl and mdl in moduletypes_by_model: return moduletypes_by_model[mdl]['id']
    return None

def find_module_bay_id(device_id, category, raw_name):
    device_mbs = module_bays_by_device.get(device_id, {})
    by_name    = device_mbs.get('by_name', {})
    by_pos     = device_mbs.get('by_pos', {})
    norm       = normalize_with_yaml(raw_name, category)
    cands      = build_candidates(category, norm)

    # 1) exact
    for c in cands:
        hit = by_name.get(c.lower())
        if hit: return hit['id']

    # 2) ends-with numeric segment (match '/X' or position)
    target   = next((c for c in cands if re.search(r'(\d+)', c)), '')
    nums     = re.findall(r'(\d+)', target)
    last_seg = nums[-1] if nums else None
    if last_seg:
        for nm, mb in by_name.items():
            if nm.endswith(f'/{last_seg}'):
                return mb['id']
        pos_hit = by_pos.get(str(last_seg))
        if pos_hit:
            return pos_hit['id']

    # 3) fuzzy (as a last resort)
    cutoff = FUZZY_CUTOFF.get(category, modulelnamesensitivity)
    names  = list(by_name.keys())
    for c in cands[:10]:
        m = get_close_matches(c.lower(), names, n=1, cutoff=cutoff)
        if m:
            mb = by_name[m[0]]
            return mb['id']
    return None
# endregion

# region ## Classify modules into categories for processing and error handling
print("Classifying modules into categories for processing...")
module_buckets = {k: [] for k in category_defs.keys()}
module_buckets['other'] = []
for module in valid_modules:
    cat = classify_module(module)
    module['category'] = cat
    module_buckets[cat].append(module)

error_rows = {k: ['hostname,name,pid,sn,dscr,module_type_id,device_id,module_bay_id,category,reason'] for k in module_buckets.keys()}
print("Module classification complete. Categories and counts:")
for cat, mods in module_buckets.items():
    print(f"  {cat}: {len(mods)} modules")
print(f'TOTAL: {len(valid_modules)} modules classified into {len(module_buckets)} categories')
print(f'Module error count: {sum(len(rows)-1 for rows in error_rows.values())}')
# endregion
# endregion

# region # Load data into NetBox
# region ## Define main import function that processes modules, applies transformations, and prepares payloads for NetBox API
def module_import(source_modules, bucket_name):
    modules_to_create = []
    for module in source_modules:
        reasons = []
        module_type_id = match_module_type(module)
        if not module_type_id: reasons.append('no_module_type')
        # device
        device_id = None
        if module.get('vcmembername'):
            device_id = devices_by_name.get((module.get('vcmembername') or '').lower())
            module['hostname'] = module['vcmembername']
        if not device_id:
            device_id = devices_by_name.get((module.get('hostname') or '').lower())
        if not device_id: reasons.append('no_device')
        # bay
        module_bay_id = None
        if device_id:
            module_bay_id = find_module_bay_id(device_id, module.get('category') or 'other', module.get('name') or '')
        if not module_bay_id: reasons.append('no_module_bay')

        data = {
            'hostname': module.get('hostname'),
            'name': module.get('name'),
            'pid': module.get('pid'),
            'sn': module.get('sn'),
            'dscr': module.get('dscr'),
            'module_type_id': module_type_id,
            'device_id': device_id,
            'module_bay_id': module_bay_id,
            'category': module.get('category'),
        }
        if module_type_id and device_id and module_bay_id:
            modules_to_create.append(data)
        else:
            error_rows[bucket_name].append(
                f"{data['hostname']},{data['name']},{data['pid']},{data['sn']},{data['dscr']},{data['module_type_id']},{data['device_id']},{data['module_bay_id']},{data['category']},{'|'.join(reasons)}"
            )
    return modules_to_create

# region ## Process each category bucket and prepare for import
print("Processing modules and preparing for import...")
full_modules = []
for bucket in module_buckets.keys():
    if bucket == 'sfp': # Skip SFPs, as modules could add SFP bays
        continue
    mods_to_create = module_import(module_buckets[bucket], bucket)
    full_modules.extend([(bucket, m) for m in mods_to_create])
    with (log_dir / f'{bucket}_modules_with_errors.csv').open('w', encoding='utf-8') as f:
        f.write('\n'.join(error_rows[bucket]))
print(f'Total modules prepared for import (excluding SFPs): {len(full_modules)}')
print(f'Total SFP modules: {len(module_buckets.get("sfp", []))}')
print(f'Total modules with errors (logged separately): {sum(len(rows)-1 for rows in error_rows.values())}')
# endregion
# region ## Define function to create modules in NetBox
def create_modules_in_netbox(bucket_name, modules_to_create):
    print(f"Creating {len(modules_to_create)} '{bucket_name}' modules in NetBox...")
    importCounter = 0
    taskduration = []
    url_base = f"{netboxbaseurl}dcim/modules/?replicate_components={str(replicate_components).lower()}&adopt_components={str(adopt_components).lower()}"
    for module in modules_to_create:
        taskstart = datetime.now()
        payload = {
            'device':      module['device_id'],
            'module_bay':  module['module_bay_id'],
            'module_type': module['module_type_id'],
            'status':      'active',
            'serial':      module['sn'],
            'description': module['dscr'],
            'comments':    'Imported from IP Fabric.'
        }
        r = requests.post(url_base, headers=netboxheaders, json=payload, verify=False)
        if r.status_code != 201:
            with (log_dir / f'error_{bucket_name}_modules_import.csv').open('a', encoding='utf-8') as f:
                f.write(f"{module['hostname']},{module['name']},{module['pid']},{module['sn']},{module['dscr']},{module['module_type_id']},{module['device_id']},{module['module_bay_id']},{bucket_name}:{r.text}\n")
        taskend = datetime.now()
        taskduration.append((taskend - taskstart).total_seconds())
        importCounter += 1
        remaining = sum(taskduration) / len(taskduration) * (len(modules_to_create) - importCounter)
        print(f'Import progress: [{"█" * int(importCounter/len(modules_to_create)*100):100}] {importCounter/len(modules_to_create)*100:.2f}% Complete - ({importCounter}/{len(modules_to_create)}) {bucket_name} modules imported. Remaining: {remaining:.2f}s', end="\r")
# endregion

# region ## Create modules in NetBox, skipping SFPs for now
print("Creating modules in NetBox (excluding SFPs)...")
for bucket in module_buckets.keys():
    taskstart = datetime.now()
    if bucket == 'sfp': 
        continue
    bucket_modules = [m for b,m in full_modules if b == bucket]
    create_modules_in_netbox(bucket, bucket_modules)
print("Module creation complete.")
# endregion
# endregion

# region # Post-import tasks and cleanup
# region ## Update VC member module bays to have correct member number in name/label/position
print("Updating VC member module bays to have correct member number in name/label/position...")
vc_members = []
for d in netbox_devices:
    nm = d.get('name') or ''
    m  = re.search(r'/([0-9]+)$', nm)
    if m:
        vc_members.append((d.get('id'), int(m.group(1))))
# endregion

# region ### Define helper function to rewrite member number in bay name/label/position based on regex patterns
def _rewrite_member_string(s: str, member_number: int) -> str:
    if not s:
        return s

    # Interface-like: Te|Gi|Hu|Twe|Eth|Ethernet|TenGigabitEthernet|...
    m_if = re.match(
        r'^(?P<pfx>Te|Gi|Hu|Twe|Eth|Ethernet|TenGigabitEthernet|GigabitEthernet|HundredGigE|TwentyFiveGigE)'
        r'(?P<member>\d+)(?P<rest>/.*)$', s, flags=re.IGNORECASE
    )
    if m_if:
        return f"{m_if.group('pfx')}{member_number}{m_if.group('rest')}"

    # StackPort
    m_sp = re.match(r'^StackPort(?P<member>\d+)(?P<rest>/.*)$', s, flags=re.IGNORECASE)
    if m_sp:
        return f"StackPort{member_number}{m_sp.group('rest')}"

    # POSITION strings that include '{module}':
    # e.g. 'TwentyFiveGigE1/{module}/1' → replace the leading member only
    m_pos = re.match(
        r'^(?P<pfx>Te|Gi|Hu|Twe|Eth|Ethernet|TenGigabitEthernet|GigabitEthernet|HundredGigE|TwentyFiveGigE)'
        r'(?P<member>\d+)(?P<rest>/\{module\}.*)$', s, flags=re.IGNORECASE
    )
    if m_pos:
        return f"{m_pos.group('pfx')}{member_number}{m_pos.group('rest')}"

    # Otherwise, return unchanged (PSU/FAN/SUP bays or any non-interface naming)
    return s
# endregion

# region ### Main function to update VC member bay names/labels/positions based on member number
def update_vc_bays(device_id: int, member_number: int):
    bays = export_netbox_data('dcim/module-bays', netboxlimit=netboxlimit, filters=[f'device_id={device_id}'])
    updates = 0
    skips   = 0
    errors  = []

    for mb in bays:
        name  = mb.get('name') or ''
        label = mb.get('label') or ''
        pos   = mb.get('position') or ''

        # Only touch interface-like or StackPort bay names
        name_is_if = re.match(
            r'^(Te|Gi|Hu|Twe|Eth|Ethernet|TenGigabitEthernet|GigabitEthernet|HundredGigE|TwentyFiveGigE)\d+/',
            name, flags=re.IGNORECASE
        )
        name_is_sp = name.startswith('StackPort')

        if not (name_is_if or name_is_sp):
            # Leave PSU/FAN/SUP/etc. alone
            skips += 1
            continue

        new_name  = _rewrite_member_string(name,  member_number)
        new_label = _rewrite_member_string(label, member_number)
        new_pos   = _rewrite_member_string(pos,   member_number)

        # Build patch only for changed fields
        payload = {}
        if new_name and new_name != name:
            payload['name']    = new_name
            payload['display'] = new_name   # keep display aligned

        # Update label if it looks interface-like and changed
        if new_label != label:
            payload['label'] = new_label

        # Update position if it contains a member and/or {module} path that changed
        if new_pos != pos:
            payload['position'] = new_pos

        if not payload:
            skips += 1
            continue

        url = f"{netboxbaseurl}dcim/module-bays/{mb['id']}/"
        r = requests.patch(url, headers=netboxheaders, json=payload, verify=False)
        if r.status_code == 200:
            updates += 1
        else:
            errors.append(f"{device_id}:{mb['id']} => {r.status_code} {r.text} | payload={payload}")

    # Optional: log a summary
    with (log_dir / f'vc_bay_updates_device_{device_id}.log').open('w', encoding='utf-8') as f:
        f.write(f"member={member_number}, updates={updates}, skips={skips}\n")
        for e in errors:
            f.write(e + "\n")

    return updates, skips, errors
# endregion

# region ### Apply VC member bay updates
print(f'Updating VC member module bays for {len(vc_members)} devices...')
taskduration = []
vc_update_count = 0
for did, member in vc_members:
    taskstart = datetime.now()
    if member == 1: continue
    update_vc_bays(did, member)
    taskend = datetime.now()
    taskduration.append((taskend - taskstart).total_seconds())
    vc_update_count += 1
    remaining = sum(taskduration) / len(taskduration) * (len(vc_members) - vc_update_count)
    print(f'VC bay update progress: [{"█" * int(vc_update_count/len(vc_members)*100):100}] {vc_update_count/len(vc_members)*100:.2f}% Complete - ({vc_update_count}/{len(vc_members)}) devices processed. Remaining: {remaining:.2f}s', end="\r")
print("\nVC member bay updates complete.")
# endregion
# endregion


# region ## Process SFP modules
print("Processing SFP modules separately to handle potential new bays created by module imports...")
sfp_modules_to_create = module_import(module_buckets.get('sfp', []), 'sfp')
with (log_dir / 'sfp_modules_with_errors.csv').open('w', encoding='utf-8') as f:
    f.write('\n'.join(error_rows['sfp']))
create_modules_in_netbox('sfp', sfp_modules_to_create)
# endregion

# region ### Update VC member interface names to have correct member number in name/label/position
def update_vc_interfaces(device_id, member_number):
    interfaces = export_netbox_data('dcim/interfaces', netboxlimit=netboxlimit, filters=[f'device_id={device_id}'])
    for intf in interfaces:
        name = intf.get('name') or ''
        m_if = re.match(r'^(?P<pfx>Te|Gi|Hu|Twe|Eth|Ethernet|TenGigabitEthernet|GigabitEthernet|HundredGigE|TwentyFiveGigE)(?P<member>\d+)(?P<rest>/.*)$', name)
        m_sp = re.match(r'^StackPort(?P<member>\d+)(?P<rest>/.*)$', name)
        target = None
        if m_if:
            target = f"{m_if.group('pfx')}{member_number}{m_if.group('rest')}"
        elif m_sp:
            target = f"StackPort{member_number}{m_sp.group('rest')}"
        else:
            continue
        if target and target != name:
            url     = f"{netboxbaseurl}dcim/interfaces/{intf['id']}/"
            payload = {'name': target, 'label': target, 'position': target}
            requests.patch(url, headers=netboxheaders, json=payload, verify=False)
# endregion
# region ### Apply VC member interface updates
print(f'Updating VC member interfaces for {len(vc_members)} devices...')
taskduration = []
vc_update_count = 0
for did, member in vc_members:
    if member == 1: continue
    update_vc_interfaces(did, member)
    taskend = datetime.now()
    taskduration.append((taskend - taskstart).total_seconds())
    vc_update_count += 1
    remaining = sum(taskduration) / len(taskduration) * (len(vc_members) - vc_update_count)
    print(f'VC interface update progress: [{"█" * int(vc_update_count/len(vc_members)*100):100}] {vc_update_count/len(vc_members)*100:.2f}% Complete - ({vc_update_count}/{len(vc_members)}) devices processed. Remaining: {remaining:.2f}s', end="\r")
print("\nVC member interface updates complete.")
# endregion
# endregion
# endregion
# region # Summary
endtime = datetime.now()
duration = endtime - starttime
print(f'Module import process completed. Start time: {starttime}, End time: {endtime}, Duration: {duration}')
# endregion