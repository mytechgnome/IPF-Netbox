#!/usr/bin/env python3
"""
AddSFPmodules.py

Purpose
-------
Ensure every SFP(-family) slot defined in *device type* YAML has BOTH:
 (a) a module bay template, and
 (b) a device interface template
with the EXACT SAME NAME (string equality).

Also update *module type* YAMLs so that:
 - Line-card/uplink module types keep their pluggable interface templates
   and also get module bay templates whose name/position mirror the interface
   template (preserving "{module}" when present), and vice versa — bays get
   matching interfaces.
 - SFP transceiver module types keep a single interface named "{module}" and
   use the physical interface type (e.g., 1000base-t for copper SFP).
   (Optional: create a matching bay with --transceiver-bays.)

NEW: Combo port support (e.g., IE-4000):
 - Certain copper interfaces (e.g., 1000base-t) have a shared SFP cage on the
   same port index/name. NetBox permits a single interface per name, so we
   retain the copper interface and *also* create a module bay with the same name
   and an SFP form-factor label ("sfp"). We mark such bays with tags ["combo-port"].

YAML handling:
 • Parse with ruamel.yaml (round-trip).
 • On parse error, run a sanitizer that fixes common malformed block-style
   issues (multiple mappings on a single line; inline '-' after a key; tabs).
 • Always return a (changed, count, changes, err) tuple from process_yaml().

CLI:
 • --source (default: Repo)
 • --target (default: DeviceLibrary)
 • --extensions (default: yaml,yml)
 • --dry-run to preview changes only
 • --transceiver-bays to also create module bays for transceiver module types (off by default)
"""
import argparse
import shutil
import re
import sys
from pathlib import Path
from typing import Optional, Tuple, List, Dict
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

# -------- YAML setup --------
yaml = YAML()
yaml.preserve_quotes = True
yaml.indent(mapping=2, sequence=4, offset=2)  # good readability
yaml.compact(seq_seq=False, seq_map=False)
yaml.width = 4096
yaml.explicit_start = True

# -------- Combo-port hints --------
# These are conservative, based on devices observed in the IPF export. You can extend safely.
# Model key: exact string match on doc.get("model") or "part_number", else contains().
COMBO_PORT_MAP: Dict[str, Dict[str, List[int]]] = {
    # IE-4000-8GT8GP4G-E: first four uplinks are combo (RJ45 + SFP cage)
    # Ports named "GigabitEthernet1/<n>" where n in [1..4]
    "IE-4000-8GT8GP4G-E": {"GigabitEthernet1": [1, 2, 3, 4]},
    # IE-4000-4T4P4G-E: observed SFP at Gi1/1 in your IPF data; keep conservative mapping
    "IE-4000-4T4P4G-E": {"GigabitEthernet1": [1]},
    # IE-4000-4GS8GP4G-E: observed SFP at Gi1/7 and Gi1/8 in your IPF data
    "IE-4000-4GS8GP4G-E": {"GigabitEthernet1": [7, 8]},
}
COMBO_BAY_TAG = "combo-port"  # tag to mark bays created due to combo support

# -------- Pluggable detection --------
PLUGGABLE_KEYS = (
    "sfp", "sfpp", "sfp28", "sfp56",
    "qsfp", "qsfpp", "qsfp28", "qsfp56", "qsfpdd",
    "osfp"
)
def is_pluggable(if_type: Optional[str]) -> bool:
    return bool(if_type) and any(k in str(if_type).lower() for k in PLUGGABLE_KEYS)

def bay_label_from_type(if_type: Optional[str]) -> str:
    """
    Normalize to concise form-factor label for module bays.
    """
    s = str(if_type or "").lower()
    # Most specific first
    if "qsfpdd" in s: return "qsfp-dd"
    if "qsfp28" in s: return "qsfp28"
    if "qsfp56" in s: return "qsfp56"
    if "qsfpp"  in s: return "qsfp+"   # alias for qsfp+
    if "qsfp"   in s: return "qsfp"
    if "sfp56"  in s: return "sfp56"
    if "sfp28"  in s: return "sfp28"
    if "sfpp"   in s or "sfp+" in s: return "sfp+"
    if "sfp"    in s: return "sfp"
    if "osfp"   in s: return "osfp"
    # Fallback
    return (s or "sfp").strip()

# -------- Type mappings --------
# Device interfaces (SFP receptacles) should use the SFP-family type choices.
DEVICE_SFP_TYPE_BY_LABEL = {
    "sfp"   : "1000base-x-sfp",
    "sfp+"  : "10gbase-x-sfpp",
    "sfp28" : "25gbase-x-sfp28",
    "sfp56" : "50gbase-x-sfp28",  # NetBox enumerates 50G under 'sfp28'
    "qsfp"  : "40gbase-x-qsfpp",
    "qsfp+" : "40gbase-x-qsfpp",
    "qsfp28": "100gbase-x-qsfp28",
    "qsfp56": "200gbase-x-qsfp56",
    "qsfp-dd":"400gbase-x-qsfpdd",
    "osfp"  : "400gbase-x-osfp",
}
# Module interfaces (SFP transceivers) should use the *physical interface* type.
MODULE_PHYSICAL_TYPE_BY_LABEL = {
    "sfp"   : "1000base-x-sfp",  # will be overridden to 1000base-t via heuristics if copper
    "sfp+"  : "10gbase-x-sfpp",
    "sfp28" : "25gbase-x-sfp28",
    "sfp56" : "50gbase-x-sfp28",
    "qsfp"  : "40gbase-x-qsfpp",
    "qsfp+" : "40gbase-x-qsfpp",
    "qsfp28": "100gbase-x-qsfp28",
    "qsfp56": "200gbase-x-qsfp56",
    "qsfp-dd":"400gbase-x-qsfpdd",
    "osfp"  : "400gbase-x-osfp",
}
COPPER_HINTS = (
    "base-t", "rj45", "copper", "-t", "glc-t", "t=", "b-t"
)
IF_PREFIXES = (
    "Te", "Gi", "Hu", "Twe", "Eth", "Ethernet",
    "TenGigabitEthernet", "GigabitEthernet",
    "HundredGigE", "TwentyFiveGigE",
    "FortyGigE", "HundredGigabitEthernet"
)

def infer_interface_type_from_name(name: str) -> Optional[str]:
    """
    Infer NetBox interface type from a Cisco-style name prefix.
    Examples:
    TenGigabitEthernet... -> 10gbase-x-sfpp
    GigabitEthernet...    -> 1000base-x-sfp
    TwentyFiveGigE...     -> 25gbase-x-sfp28
    FortyGigE...          -> 40gbase-x-qsfpp
    HundredGigE...        -> 100gbase-x-qsfp28
    """
    n = (name or "").lower()
    if n.startswith("tengigabitethernet") or n.startswith("tenge"):
        return "10gbase-x-sfpp"
    if n.startswith("gigabitethernet") or n.startswith("gi"):
        return "1000base-x-sfp"
    if n.startswith("twentyfivegige") or n.startswith("25g"):
        return "25gbase-x-sfp28"
    if n.startswith("fortygige") or n.startswith("40g"):
        return "40gbase-x-qsfpp"
    if n.startswith("hundredgige") or n.startswith("hundredgigabitethernet") or n.startswith("100g"):
        return "100gbase-x-qsfp28"
    # QSFP56 / 200G etc. can be added here if needed
    return None

def looks_like_interface_name(name: str) -> bool:
    if not name: return False
    pfx = name.split('/')[0]
    for pref in IF_PREFIXES:
        if pfx.lower().startswith(pref.lower()):
            return True
    return False

def is_linecard_path(name: str) -> bool:
    return "{module}" in str(name or "")

def ensure_seq(doc: CommentedMap, key: str) -> CommentedSeq:
    seq = doc.get(key)
    if not isinstance(seq, list):
        seq = CommentedSeq()
        doc[key] = seq
    return seq

# -------- ModuleType classification --------
def module_type_kind(doc: CommentedMap) -> str:
    """
    Distinguish line-card style vs SFP transceiver module types.
    - 'linecard' : multiple pluggable interfaces OR names like 'Gi1/{module}/N' OR
      single pluggable interface that looks like a port name or has existing bays,
      OR zero interfaces but bays exist and look pluggable.
    - 'sfp-module' : exactly one pluggable interface and no existing bays, and the name does
      not look like an interface path (treated as a transceiver module)
    """
    if not isinstance(doc, dict): return "unknown"
    interfaces = doc.get("interfaces", [])
    if not isinstance(interfaces, list): return "unknown"
    plug_ifaces = [i for i in interfaces if isinstance(i, dict) and is_pluggable(i.get("type"))]
    if len(plug_ifaces) >= 2:
        return "linecard"
    if len(plug_ifaces) == 1:
        name = str(plug_ifaces[0].get("name", ""))
        has_extra = "{module}" in name and "/" in name.replace("{module}", "")
        has_bays = isinstance(doc.get("module-bays"), list) and any(isinstance(b, dict) for b in doc.get("module-bays", []))
        iface_style = looks_like_interface_name(name)
        if has_bays or "{module}" in name or has_extra or iface_style:
            return "linecard"
        return "sfp-module"
    # NEW: zero interfaces — decide based on bays
    bays = doc.get("module-bays", [])
    if isinstance(bays, list) and bays:
        for b in bays:
            if not isinstance(b, dict):
                continue
            bname = str(b.get("name", ""))
            blabel = str(b.get("label", "")).lower()
            # Treat as linecard if bay looks pluggable
            if "{module}" in bname or looks_like_interface_name(bname) or blabel in DEVICE_SFP_TYPE_BY_LABEL:
                return "linecard"
    return "unknown"

# -------- Heuristic: copper 1G SFP modules --------
def maybe_force_copper_1g(model: str, current_type: str) -> str:
    """
    If module 'model' looks copper, return '1000base-t'.
    Otherwise, return current_type unchanged.
    """
    s_model = str(model or "").lower()
    s_type  = str(current_type or "").lower()
    if "1000base" in s_type and "sfp" in s_type:
        for hint in COPPER_HINTS:
            if hint in s_model:
                return "1000base-t"
    return current_type

# -------- Combo port helpers --------
_combo_name_pat = re.compile(r"^(GigabitEthernet\d+)/(\d+)$")
def is_combo_port(model: str, name: str, if_type: Optional[str]) -> bool:
    """
    Return True if this interface name should also have an SFP module bay (combo port).
    We match on model and name pattern (e.g., 'GigabitEthernet1/<n>') and require
    the interface type to be copper (e.g., 1000base-t).
    """
    if_type_s = str(if_type or "").lower()
    if "base-t" not in if_type_s:
        return False  # only consider copper RJ45 as combo host
    m = _combo_name_pat.match(str(name or ""))
    if not m:
        return False
    base, idx_s = m.group(1), m.group(2)
    try:
        idx = int(idx_s)
    except Exception:
        return False
    model_s = str(model or "")
    # exact model match
    if model_s in COMBO_PORT_MAP and base in COMBO_PORT_MAP[model_s]:
        return idx in COMBO_PORT_MAP[model_s][base]
    # contains() fallback (e.g., if 'part_number' vs 'model' differs slightly)
    for mk, base_map in COMBO_PORT_MAP.items():
        if mk in model_s:
            if base in base_map and idx in base_map[base]:
                return True
    return False

# -------- YAML sanitizer for malformed block style --------
_KEY_TOKENS = ("name", "type", "label", "position", "description", "role", "model", "manufacturer", "part_number")
def sanitize_yaml_text(text: str) -> str:
    """
    Best-effort fixer for common block-style YAML mistakes:
    - Multiple key:value pairs on one line (e.g., 'name: X type: Y')
    - Inline sequence start right after a key (e.g., 'module-bays: -')
    - Tabs -> spaces
    Structural-only changes; does not rename values.
    """
    # 1) Replace tabs with 2 spaces (YAML forbids tabs)
    text = text.replace("\t", "  ")
    fixed_lines = []
    for raw in text.splitlines():
        line = raw.rstrip()
        # If key followed by inline dash (e.g., 'module-bays: -'), split to new line
        if re.match(r"^\s*[\w\-]+:\s*-", line):
            indent = re.match(r"^(\s*)", line).group(1)
            key = line.split(":")[0].strip()
            after = line.split(":", 1)[1].strip()
            if after.startswith("-"):
                suffix = after[1:].strip()
                line = f"{indent}{key}:"
                fixed_lines.append(line)
                dash_indent = indent + " "
                if suffix:
                    fixed_lines.append(f"{dash_indent}- {suffix}")
                else:
                    fixed_lines.append(f"{dash_indent}-")
                continue
        # If the line has multiple 'key:' tokens (e.g., 'name: X type: Y ...'), split
        token_hits = [t for t in _KEY_TOKENS if f"{t}:" in line]
        if len(token_hits) >= 2:
            indent = re.match(r"^(\s*)", line).group(1)
            dash = ""
            content = line.strip()
            if content.startswith("- "):
                dash = "- "
                content = content[2:]
            matches = list(re.finditer(r"([A-Za-z0-9_\-]+):", content))
            if matches:
                start = 0
                parts = []
                for i, m in enumerate(matches):
                    if i == 0:
                        continue
                    parts.append(content[start:m.start()].strip())
                    start = m.start()
                parts.append(content[start:].strip())
                first = parts[0]
                fixed_lines.append(f"{indent}{dash}{first}")
                for p in parts[1:]:
                    fixed_lines.append(f"{indent}{p}")
                continue
        fixed_lines.append(line)
    return "\n".join(fixed_lines) + ("\n" if text.endswith("\n") else "")

# -------- DeviceType transform --------
def transform_device_type(doc: CommentedMap) -> Tuple[bool, int, List[str]]:
    """
    DeviceType:
    - Keep existing pluggable interfaces.
    - Ensure a module bay exists per pluggable interface:
      bay.name == iface.name; bay.position == iface.name; bay.label == SFP form factor
    - Backfill interface for any existing SFP bay without a matching interface (same name).
    - Normalize mismatches; report all changes.
    - NEW: For combo copper ports (e.g., 1000base-t) that should also have an SFP cage,
      create/align a bay named exactly like the interface, with label 'sfp' and tag 'combo-port'.
    Skips non-SFP bays (PSU/FAN/etc.).
    """
    interfaces = doc.get("interfaces", [])
    module_bays = ensure_seq(doc, "module-bays")
    changes: List[str] = []
    changed = False
    count = 0

    # Quick lookup maps
    iface_by_name: Dict[str, CommentedMap] = {}
    if isinstance(interfaces, list):
        for i in interfaces:
            if isinstance(i, dict) and i.get("name"):
                iface_by_name[str(i["name"])] = i
    bay_by_name: Dict[str, CommentedMap] = {}
    for b in module_bays:
        if isinstance(b, dict) and b.get("name"):
            bay_by_name[str(b["name"])] = b

    model_text = str(doc.get("model") or doc.get("part_number") or "")

    # 1) From interfaces -> ensure bays
    for iname, iface in iface_by_name.items():
        itype = iface.get("type")
        if is_pluggable(itype):
            lbl = bay_label_from_type(itype)
            desired_iface_type = DEVICE_SFP_TYPE_BY_LABEL.get(lbl, itype)
            # Fix interface type if needed (receptacle type on device type)
            if desired_iface_type and itype != desired_iface_type:
                iface["type"] = desired_iface_type
                changes.append(f"Interface '{iname}': type '{itype}' -> '{desired_iface_type}'")
                changed = True
                count += 1
            # Ensure bay exists/matches
            bay = bay_by_name.get(iname)
            if not bay:
                bay = CommentedMap()
                bay["name"] = iname
                bay["position"] = iname
                bay["label"] = lbl
                if "description" in iface: bay["description"] = iface["description"]
                if "tags" in iface: bay["tags"] = iface["tags"]
                module_bays.append(bay)
                bay_by_name[iname] = bay
                changes.append(f"Module bay created: name='{iname}', position='{iname}', label='{lbl}'")
                changed = True
                count += 1
            else:
                # Align existing bay (for SFP slots)
                orig_pos = bay.get("position", "")
                orig_lbl = bay.get("label", "")
                need_fix = False
                if not is_linecard_path(bay.get("name")):
                    if orig_pos != iname:
                        bay["position"] = iname
                        changes.append(f"Bay '{iname}': position '{orig_pos}' -> '{iname}'")
                        need_fix = True
                    if lbl and orig_lbl != lbl:
                        bay["label"] = lbl
                        changes.append(f"Bay '{iname}': label '{orig_lbl}' -> '{lbl}'")
                        need_fix = True
                if need_fix:
                    changed = True
                    count += 1
            continue  # handled pluggable interface

        # NEW: combo copper port -> create an SFP bay with same name
        if is_combo_port(model_text, iname, itype):
            bay = bay_by_name.get(iname)
            if not bay:
                bay = CommentedMap()
                bay["name"] = iname
                bay["position"] = iname
                bay["label"] = "sfp"
                bay["tags"] = CommentedSeq([COMBO_BAY_TAG])
                bay["description"] = "Combo port: RJ45 or SFP"
                module_bays.append(bay)
                bay_by_name[iname] = bay
                changes.append(f"Module bay created (combo): name='{iname}', position='{iname}', label='sfp'")
                changed = True
                count += 1
            else:
                # If bay exists, ensure it's tagged/labelled as combo SFP
                orig_lbl = str(bay.get("label", ""))
                if orig_lbl.lower() != "sfp":
                    bay["label"] = "sfp"
                    changes.append(f"Bay '{iname}': label '{orig_lbl}' -> 'sfp' (combo)")
                    changed = True
                    count += 1
                tags = bay.get("tags")
                if not isinstance(tags, list):
                    tags = CommentedSeq()
                    bay["tags"] = tags
                if COMBO_BAY_TAG not in tags:
                    tags.append(COMBO_BAY_TAG)
                    changes.append(f"Bay '{iname}': tag +'{COMBO_BAY_TAG}' (combo)")
                    changed = True
                    count += 1

    # 2) From bays -> ensure matching interfaces (SFP-family)
    for bname, bay in bay_by_name.items():
        blabel = str(bay.get("label", "")).lower()
        if "{module}" in str(bay.get("position", "")) or "{module}" in str(bay.get("name", "")):
            continue  # line-card style bay; leave as-is
        # Combo bay does NOT require an extra interface (we already have copper one)
        bay_tags = bay.get("tags") or []
        if isinstance(bay_tags, list) and COMBO_BAY_TAG in [t for t in bay_tags]:
            continue
        if blabel not in DEVICE_SFP_TYPE_BY_LABEL:
            # When label isn't one of the canonical SFP family, infer from name if possible
            if not looks_like_interface_name(bname):
                continue
        desired_iface_type = DEVICE_SFP_TYPE_BY_LABEL.get(blabel, None)
        iface = iface_by_name.get(bname)
        if not iface:
            iface = CommentedMap()
            iface["name"] = bname
            if desired_iface_type:
                iface["type"] = desired_iface_type
            if "description" in bay: iface["description"] = bay["description"]
            if "tags" in bay: iface["tags"] = bay["tags"]
            interfaces.append(iface)
            iface_by_name[bname] = iface
            changes.append(f"Interface created: name='{bname}', type='{desired_iface_type or ''}'")
            changed = True
            count += 1
        else:
            itype = iface.get("type")
            if desired_iface_type and itype != desired_iface_type:
                iface["type"] = desired_iface_type
                changes.append(f"Interface '{bname}': type '{itype}' -> '{desired_iface_type}'")
                changed = True
                count += 1

    doc["interfaces"] = CommentedSeq(list(interfaces))
    return (changed, count, changes)

# -------- ModuleType transforms --------
def transform_module_type_linecard(doc: CommentedMap) -> Tuple[bool, int, List[str]]:
    """
    ModuleType (line-card / uplink style):
    - Ensure module bay templates exist for each pluggable interface template (or align existing).
      Bay label is normalized to the SFP form factor.
    - KEEP existing interfaces.
    - Also ensure interfaces exist for each SFP(-family) bay (not only those with '{module}' in the name).
    * interface.name = bay.name (keeps '{module}' when present)
    * interface.type inferred from name (e.g., TenGigabitEthernet -> 10gbase-x-sfpp),
      or from bay label mapping, else default to 10gbase-x-sfpp.
    """
    interfaces = doc.get("interfaces", [])
    module_bays = ensure_seq(doc, "module-bays")
    changes: List[str] = []
    changed = False
    created = 0

    if not isinstance(interfaces, list):
        interfaces = []
        doc["interfaces"] = interfaces

    # Track existing objects
    bay_map: Dict[str, CommentedMap] = {}
    for b in module_bays:
        if isinstance(b, dict) and b.get("name"):
            bay_map[str(b.get("name"))] = b
    iface_map: Dict[str, CommentedMap] = {}
    for i in interfaces:
        if isinstance(i, dict) and i.get("name"):
            iface_map[str(i.get("name"))] = i

    # 1) For each existing interface (pluggable), ensure a matching bay exists/aligned
    for name, iface in list(iface_map.items()):
        itype = iface.get("type")
        if not is_pluggable(itype):
            continue
        lbl = bay_label_from_type(itype)
        bay = bay_map.get(name)
        if not bay:
            bay = CommentedMap()
            bay["name"] = name
            bay["position"] = name
            bay["label"] = lbl
            if "description" in iface: bay["description"] = iface["description"]
            if "tags" in iface: bay["tags"] = iface["tags"]
            module_bays.append(bay)
            bay_map[name] = bay
            changes.append(f"Module bay created (linecard): name='{name}', position='{name}', label='{lbl}'")
            changed = True
            created += 1
        else:
            # Align position and label (normalize to SFP form factor)
            if bay.get("position") != name:
                bay["position"] = name
                changes.append(f"Module bay '{name}': position aligned to '{name}'")
                changed = True
            if bay.get("label") != lbl:
                bay["label"] = lbl
                changes.append(f"Module bay '{name}': label aligned to '{lbl}'")
                changed = True

    # 2) For each bay that looks SFP-family, ensure a matching interface exists
    for bname, bay in list(bay_map.items()):
        blabel = bay_label_from_type(bay.get("label"))
        looks_sfp = blabel in DEVICE_SFP_TYPE_BY_LABEL or looks_like_interface_name(bname)
        if not looks_sfp:
            continue
        if bname in iface_map:
            # Optionally align type if inferable
            iface = iface_map[bname]
            desired = infer_interface_type_from_name(bname) \
                or DEVICE_SFP_TYPE_BY_LABEL.get(blabel) \
                or iface.get("type")
            if desired and iface.get("type") != desired:
                old = iface.get("type")
                iface["type"] = desired
                changes.append(f"Module iface '{bname}': type '{old}' -> '{desired}'")
                changed = True
            continue
        # Create interface for bay
        itype = infer_interface_type_from_name(bname) \
            or DEVICE_SFP_TYPE_BY_LABEL.get(blabel) \
            or "10gbase-x-sfpp"
        iface = CommentedMap()
        iface["name"] = bname  # keep '{module}' if present
        iface["type"] = itype
        if "description" in bay: iface["description"] = bay["description"]
        if "tags" in bay: iface["tags"] = bay["tags"]
        interfaces.append(iface)
        iface_map[bname] = iface
        changes.append(f"Module iface created: name='{bname}', type='{itype}'")
        changed = True
        created += 1

    # Persist
    doc["interfaces"] = CommentedSeq(list(interfaces))
    return (changed, created, changes)

def transform_module_type_sfp_module(doc: CommentedMap, create_bay_for_transceiver: bool=False) -> Tuple[bool, int, List[str]]:
    """
    ModuleType (SFP transceiver):
    - Keep single pluggable interface.
    - Ensure interface['name'] == '{module}' (for adopt_components).
    - Ensure interface['type'] reflects *physical* interface type.
      (Copper 1G heuristics: model text suggests -> 1000base-t)
    - Optional: create a bay named '{module}' when create_bay_for_transceiver=True.
    """
    interfaces = doc.get("interfaces", [])
    module_bays = ensure_seq(doc, "module-bays") if create_bay_for_transceiver else doc.get("module-bays", [])
    if not isinstance(interfaces, list): return (False, 0, [])
    changes: List[str] = []
    changed = False
    updated = 0

    plug_ifaces = [i for i in interfaces if isinstance(i, dict) and is_pluggable(i.get("type"))]
    if not plug_ifaces:
        return (False, 0, changes)
    iface = plug_ifaces[0]
    name = str(iface.get("name", ""))
    itype = str(iface.get("type", "")).lower()
    label = bay_label_from_type(itype)
    desired_type = MODULE_PHYSICAL_TYPE_BY_LABEL.get(label, iface.get("type"))
    desired_type = maybe_force_copper_1g(str(doc.get("model", "")), desired_type)
    if name != "{module}":
        iface["name"] = "{module}"
        changes.append(f"Module iface name: '{name}' -> '{{module}}'")
        changed = True
        updated += 1
    if desired_type and iface.get("type") != desired_type:
        old = iface.get("type")
        iface["type"] = desired_type
        changes.append(f"Module iface type: '{old}' -> '{desired_type}'")
        changed = True
        updated += 1

    # Optional: create a bay for transceiver modules
    if create_bay_for_transceiver:
        # ensure bay with name/position '{module}', label == SFP form factor
        bay = None
        if isinstance(module_bays, list):
            for b in module_bays:
                if isinstance(b, dict) and b.get("name") == "{module}":
                    bay = b
                    break
        if bay is None and isinstance(module_bays, list):
            bay = CommentedMap()
            bay["name"] = "{module}"
            bay["position"] = "{module}"
            bay["label"] = label
            module_bays.append(bay)
            changes.append(f"Module bay created (sfp-module): name='{{module}}', position='{{module}}', label='{label}'")
            changed = True
            updated += 1
        if isinstance(module_bays, list):
            doc["module-bays"] = CommentedSeq(list(module_bays))
    return (changed, updated, changes)

# -------- per-file processing --------
def process_yaml(src_path: Path, dst_path: Path, kind: str, create_bay_for_transceiver: bool=False) -> Tuple[bool, int, List[str], str]:
    """
    Always returns: (changed: bool, count: int, changes: List[str], err: str)
    'err' is non-empty only if we couldn't parse/write the file after sanitization.
    """
    # 1) Read + parse, or sanitize and re-parse on failure
    try:
        text = src_path.read_text(encoding="utf-8")
        doc = yaml.load(text)
        if not isinstance(doc, dict):
            # Copy through unchanged
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            dst_path.write_text(text, encoding="utf-8")
            return (False, 0, [], "")
    except Exception as e:
        # Attempt sanitize, then parse again
        try:
            raw = src_path.read_text(encoding="utf-8")
            fixed = sanitize_yaml_text(raw)
            doc = yaml.load(fixed)
            # Write sanitized text to destination, even if no structural transform needed later
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            with dst_path.open("w", encoding="utf-8") as fh:
                fh.write(fixed)
            return (True, 0, [f"SANITIZED YAML: {src_path.name}"], "")
        except Exception:
            return (False, 0, [], f"YAML parse error in {src_path}")
    # 2) Apply transforms
    if kind == "device":
        changed, count, changes = transform_device_type(doc)
    elif kind == "module":
        mkind = module_type_kind(doc)
        if mkind == "linecard":
            changed, count, changes = transform_module_type_linecard(doc)
        elif mkind == "sfp-module":
            changed, count, changes = transform_module_type_sfp_module(doc, create_bay_for_transceiver=create_bay_for_transceiver)
        else:
            changed, count, changes = (False, 0, [])
    else:
        changed, count, changes = (False, 0, [])
    # 3) Write out
    try:
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        with dst_path.open("w", encoding="utf-8") as fh:
            yaml.dump(doc, fh)
    except Exception as e:
        return (False, 0, [], f"Write error {dst_path}: {e}")
    # 4) Always return a tuple
    return (changed, count, changes, "")

def copy_asset(src_path: Path, dst_path: Path) -> Optional[str]:
    try:
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dst_path)
        return None
    except Exception as e:
        return f"Copy error {src_path} -> {dst_path}: {e}"

# -------- CLI --------
def main():
    ap = argparse.ArgumentParser(
        description="Ensure device-type SFP bays/interfaces coexist; adapt SFP module types for adopt_components. Supports combo copper+SFP ports."
    )
    ap.add_argument("--source", default="Repo", help="Source folder (default: Repo)")
    ap.add_argument("--target", default="DeviceLibrary", help="Target folder (default: DeviceLibrary)")
    ap.add_argument("--extensions", default="yaml,yml", help="Comma-separated YAML extensions (default: yaml,yml)")
    ap.add_argument("--dry-run", action="store_true", help="Report only; no writes")
    ap.add_argument("--transceiver-bays", action="store_true",
        help="Also create module bays for transceiver module types (sfp-module). Default: off.")
    args = ap.parse_args()
    src_root = Path(args.source)
    dst_root = Path(args.target)
    yaml_exts = tuple("." + e.strip().lower() for e in args.extensions.split(",") if e.strip())

    total_files = 0
    yaml_changed = 0
    device_bays_created = 0
    module_bays_created = 0
    sfp_modules_adjusted = 0
    errors: List[str] = []
    report: List[str] = []

    for src in src_root.rglob("*"):
        if not src.is_file():
            continue
        total_files += 1
        rel = src.relative_to(src_root)
        dst = dst_root / rel
        parts = [p.lower() for p in rel.parts]
        in_device = "device-types" in parts or "devices" in parts
        in_module = "module-types" in parts or "modules" in parts
        if src.suffix.lower() in yaml_exts and (in_device or in_module):
            kind = "device" if in_device else "module"

            if args.dry_run:
                # DRY-RUN: parse & show planned changes
                try:
                    text = src.read_text(encoding="utf-8")
                    doc = yaml.load(text)
                except Exception:
                    try:
                        fixed = sanitize_yaml_text(src.read_text(encoding="utf-8"))
                        doc = yaml.load(fixed)
                        print(f"[DRY-RUN] {rel} — SANITIZED before transform")
                    except Exception as e:
                        errors.append(f"YAML parse error in {src}: {e}")
                        print(f"[DRY-RUN] {rel} — parse failed, skipping")
                        continue
                if kind == "device":
                    _, count, changes = transform_device_type(doc)
                    print(f"[DRY-RUN] {rel} (DeviceType) → changes: +{count}")
                    for c in changes: print(f" - {c}")
                else:
                    mkind = module_type_kind(doc)
                    if mkind == "linecard":
                        _, count, changes = transform_module_type_linecard(doc)
                        print(f"[DRY-RUN] {rel} (ModuleType line-card) → created +{count}")
                        for c in changes: print(f" - {c}")
                    elif mkind == "sfp-module":
                        _, count, changes = transform_module_type_sfp_module(doc, create_bay_for_transceiver=args.transceiver_bays)
                        print(f"[DRY-RUN] {rel} (ModuleType SFP) → adjustments +{count}")
                        for c in changes: print(f" - {c}")
                    else:
                        print(f"[DRY-RUN] {rel} (ModuleType unknown) → copied unchanged")
                continue

            # Real run
            changed, count, changes, err = process_yaml(src, dst, kind, create_bay_for_transceiver=args.transceiver_bays)
            if err:
                errors.append(err)
                print(f"[ERR ] {rel} — {err}")
                continue
            if changed:
                yaml_changed += 1
                for c in changes:
                    report.append(f"{rel}: {c}")
                if kind == "device":
                    device_bays_created += sum(1 for c in changes if c.startswith("Module bay created"))
                    device_bays_created += sum(1 for c in changes if c.startswith("Module bay created (combo)"))
                else:
                    module_bays_created += sum(1 for c in changes if c.startswith("Module bay created"))
                sfp_modules_adjusted += sum(1 for c in changes if c.startswith("Module iface"))
                print(f"[OK  ] {rel} — {kind} YAML transformed (+{count})")
            else:
                print(f"[COPY] {rel} — {kind} YAML copied unchanged")
        else:
            if args.dry_run:
                print(f"[DRY-RUN] {rel} (asset) → copy unchanged")
                continue
            err = copy_asset(src, dst)
            if err:
                errors.append(err)
                print(f"[ERR ] {rel} — {err}")
            else:
                print(f"[COPY] {rel} — asset copied")

    # Summary
    print("\nSummary")
    print(f" Files scanned                    : {total_files}")
    print(f" YAML files transformed           : {yaml_changed}")
    print(f" DeviceType module bays created   : {device_bays_created}")
    print(f" ModuleType module bays created   : {module_bays_created}")
    print(f" SFP module iface adjustments     : {sfp_modules_adjusted}")
    if report:
        print("\nChanges:")
        for line in report:
            print(f" - {line}")
    if errors:
        print("\nErrors:")
        for e in errors:
            print(f" - {e}")

if __name__ == "__main__":
    main()
