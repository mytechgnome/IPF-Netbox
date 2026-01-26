'''
This script creates a .env file to store configuration settings for IP Fabric and Netbox access.
It prompts the user for necessary information and writes it to the .env file.

Created by: Dan Kelcher
Date: January 5, 2026
'''

def create_env_file():
    import os
    from pathlib import Path
# region # Check if .env file exists
    try:
        currentdir = Path(__file__).parent # Get directory of current script
    except:
        currentdir = os.getcwd() # Fallback to current working directory

    if os.path.isfile(os.path.join(currentdir, '.env')):
        print('.env file already exists.')
        updateenv = input('Would you like to update the existing .env file? (y/n): ').strip().lower()
        if updateenv == 'y':
            pass
        else:
            print('Exiting to avoid overwriting existing configuration.')
            exit()
# endregion
# region # Create local .env file for IP Fabric and Netbox access
# region ## Prompt user for settings
    ipfip = input('Please enter the IP address of the IP Fabric server: ').strip()
    ipftoken = input('Please enter your IP Fabric API token: ').strip()
    netbox = input('Do you want to connect to Netbox? (y/n): ').strip().lower()
    if netbox == 'y':
        netboxip = input('Please enter the IP address of the Netbox server: ').strip()
        netboxtoken = input('Please enter your Netbox API token: ').strip()
    disableverify = input('Disable SSL verification? (y/n): ').strip().lower()
    if disableverify == 'y':
        disableverify = 'True'
    elif disableverify == 'n':
        disableverify = 'False'
    else:
        print('Invalid input. Defaulting to SSL verification enabled.')
    advancedsettings = input('Would you like to configure advanced settings? (y/n): ').strip().lower()
    if advancedsettings == 'y':
        print('Advanced settings configuration is not yet implemented.')
        vendornamesensitivity = input('Set vendor name case sensitivity (1-10, 10 = exact match): ').strip()
        if not vendornamesensitivity.isdigit() or not (1 <= int(vendornamesensitivity) <= 10):
            print('Invalid input. Defaulting to 8.')
            vendornamesensitivity = '0.8'
        else:
            vendornamesensitivity = str(int(vendornamesensitivity) / 10)
        modellnamesensitivity = input('Set model name case sensitivity (1-10, 10 = exact match): ').strip()
        if not modellnamesensitivity.isdigit() or not (1 <= int(modellnamesensitivity) <= 10):
            print('Invalid input. Defaulting to 8.')
            modellnamesensitivity = '0.8'
        else:
            modellnamesensitivity = str(int(modellnamesensitivity) / 10)
        deviceimagesensitivity = input('Set device image name case sensitivity (1-10, 10 = exact match): ').strip()
        if not deviceimagesensitivity.isdigit() or not (1 <= int(deviceimagesensitivity) <= 10):
            print('Invalid input. Defaulting to 8.')
            deviceimagesensitivity = '0.8'
        else:
            deviceimagesensitivity = str(int(deviceimagesensitivity) / 10)
        modulenamesensitivity = input('Set module name case sensitivity (1-10, 10 = exact match): ').strip()
        if not modulenamesensitivity.isdigit() or not (1 <= int(modulenamesensitivity) <= 10):
            print('Invalid input. Defaulting to 8.')
            modulenamesensitivity = '0.8'
        else:
            modulenamesensitivity = str(int(modulenamesensitivity) / 10)
        print('Repository for Device Type Library:')
        print('Default: https://github.com/netbox-community/devicetype-library.git')
        customrepository = input('Enter custom repository path (or leave blank for default): ').strip()
        if customrepository == '':
            customrepository = 'https://github.com/netbox-community/devicetype-library.git'
# endregion
# region ## Write settings to .env file
    with open(os.path.join(currentdir, '.env'), 'w') as f:
        f.write('# IP Fabric settings\n')
        f.write('ipfabricbaseurl=https://')
        f.write(ipfip)
        f.write('/api/v7/\n')
        f.write('ipfabrictoken=')
        f.write(ipftoken)
        f.write('\n')
        if netbox == 'y':
            f.write('# Netbox settings\n')
            f.write('netboxbaseurl=https://')
            f.write(netboxip)
            f.write('/api/\n')
            f.write('netboxtoken=')
            f.write(netboxtoken)
            f.write('\n')
        f.write('# SSL verification setting\n')
        f.write('disableverifyssl=')
        f.write(disableverify)
        f.write('\n')
        if advancedsettings == 'y':
            f.write('# Advanced settings\n')
            f.write('vendornamesensitivity=')
            f.write(vendornamesensitivity)
            f.write('\n')
            f.write('modelnamesensitivity=')
            f.write(modellnamesensitivity)
            f.write('\n')
            f.write('deviceimagesensitivity=')
            f.write(deviceimagesensitivity)
            f.write('\n')
            f.write('modulenamesensitivity=')
            f.write(modulenamesensitivity)
            f.write('\n')
            f.write('reposource=')
            f.write(customrepository)
            f.write('\n')
    print('.env file created successfully.')
# endregion
# endregion
if __name__ == '__main__':
    create_env_file()