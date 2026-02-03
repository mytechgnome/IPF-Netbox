# IPF-Netbox
Collect device and module information from IP Fabric and import the corresponding templates from device-library into Netbox  

**This is a work in progress. Not everything works properly. There are bugs. The documentation isn't fully updated.**
The scripts for Platforms, Roles, Sites, and Virtual Chassis work well, but those are included in the current plugin already.  
The DeviceTypes script seems stable, but matching can be an issue. There are also going to be issues because not all devices are in the DeviceTypeLibrary.  
The Wireless script imports SSIDs.
The VPN script is a placeholder for now.  It should be easy to get finished, but it's a low priority right now.  
The other scripts (Cables, Devices, Modules) are still getting worked on. There are issues with conflicts in how the current plugin operates, and these are being addressed. 

# Requirements
- Populate .env with required data
- Install GitPython library - pip install GitPython
- Install PyYAML library - pip install PyYAML
- Install pandas library - pip install pandas
- Install python-dotenv library - pip install python-dotenv
- *If running on NetBox server recommended to add installs to /opt/netbox/local_requirements.txt
- NetBox IP Fabric Plugin installed and configured (but without a sync run yet)

# Netbox IP Fabric Plugin changes required:
Modify Device Type Transform Map field maps
- Remove Manufacturer mapping
- Add mapping source 'model' target 'part_number' and check coalesce
- Uncheck coalesce from the model -> slug mapping
Modify Manufacturer Transform Map field map
- Remove vendor -> name mapping

# How to use
Before running a sync with IP Fabric, run 'IPF_NetBoc_ImportDeviceTypes.py'  
On the first run, it will prompt for the creation of the .env file if it doesn't exist already  
It will clone the DeviceTypeLibrary repo, collect inventory data from IP Fabric, attempt to match the devices found, and then add them into NetBox 

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
- Convert SFP interfaces to be module bays - this is tied to this NetBox fix [https://github.com/netbox-community/netbox/pull/21073](https://github.com/netbox-community/netbox/pull/21073)

# Bugs
- When used with the IP Fabric NetBox plugin a lot of the data from DeviceTypeLibrary is overwritten  
- The IP Fabric NetBox plugin imports interfaces as 1000base-T, no matter what the interface actually is
- Module mapping is not very accurate

# Warnings
- This is still in development, and may not work as expected
