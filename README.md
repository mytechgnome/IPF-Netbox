# IPF-Netbox
Collect device and module information from IP Fabric and import the corresponding templates from device-library into Netbox

# Requirements
- Populate .env with required data
- Install GitPython library - pip install GitPython
- Install PyYAML library - pip install PyYAML
- Install pandas library - pip install pandas
- Install python-dotenv library - pip install python-dotenv
- *If running on NetBox server recommended to add installs to /opt/netbox/local_requirements.txt
- NetBox IP Fabric Plugin installed and configured

# Netbox IP Fabric Plugin changes required:
Modify Device Type Transform Map field maps
- Remove Manufacturer mapping
- Add mapping source 'model' target 'part_number' and check coalesce
- Uncheck coalesce from the model -> slug mapping
Modify Manufacturer Transform Map field map
- Remove vendor -> name mapping

# Notes
- Code is very immature, and could be refactored and optomized
- Matching is fuzzy, and can be adjusted in the sensitivity settings of the .env file
-   Because matching is fuzzy, devices might be mapped incorrectly
- Import does not overwrite or modify existing objects

# To Do
- Error handling
- Improved detection of device and module names
- Logging
- Dry-run option
- Import inventory from IPF as modules, not inventory items
- Convert SFP interfaces to be module bays

# Warnings
- This is still in development, and may not work as expected
