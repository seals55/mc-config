import os
import requests
import sys

# Configuration
MC_VERSION = "1.21.1"
LOADER = "neoforge"
MODS_DIR = "mods"

# Mod list: Add slugs from Modrinth (the part in the URL after /mod/)
MOD_LIST = [
    "infinite-storage-cell"
]

def get_latest_version(slug, mc_version, loader):
    """Fetches the latest version of a mod from Modrinth API."""
    print(f"Checking for updates: {slug}...")
    url = f"https://api.modrinth.com/v2/project/{slug}/version"
    params = {
        "loaders": f'["{loader}"]',
        "game_versions": f'["{mc_version}"]'
    }
    
    response = requests.get(url, params=params)
    if response.status_code != 200:
        print(f"Error fetching versions for {slug}: {response.status_code}")
        return None
    
    versions = response.json()
    if not versions:
        print(f"No compatible versions found for {slug} on {mc_version} ({loader})")
        return None
    
    # Modrinth returns versions in reverse chronological order (newest first)
    return versions[0]

def download_file(url, filename):
    """Downloads a file to the mods directory."""
    path = os.path.join(MODS_DIR, filename)
    
    if os.path.exists(path):
        print(f"File {filename} already exists. Skipping download.")
        return

    print(f"Downloading {filename}...")
    response = requests.get(url, stream=True)
    if response.status_code == 200:
        with open(path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print("Download complete.")
    else:
        print(f"Failed to download {filename}: {response.status_code}")

def main():
    if not os.path.exists(MODS_DIR):
        os.makedirs(MODS_DIR)

    for mod_slug in MOD_LIST:
        version_data = get_latest_version(mod_slug, MC_VERSION, LOADER)
        if version_data:
            # A version can have multiple files; we usually want the primary one
            file_data = next((f for f in version_data['files'] if f['primary']), version_data['files'][0])
            download_file(file_data['url'], file_data['filename'])

if __name__ == "__main__":
    try:
        import requests
    except ImportError:
        print("Error: The 'requests' library is required. Please install it with 'pip install requests'.")
        sys.exit(1)
        
    main()
