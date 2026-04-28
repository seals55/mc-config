import os
import shutil
import argparse
import sys

def sync_folder(src, dst, overwrite=False):
    """
    Syncs files from src to dst. 
    If overwrite is True, it replaces existing files.
    If overwrite is False, it only copies missing files.
    """
    if not os.path.exists(src):
        print(f"Source folder {src} does not exist. Skipping.")
        return

    if not os.path.exists(dst):
        print(f"Creating destination folder {dst}")
        os.makedirs(dst, exist_ok=True)

    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)

        if os.path.isdir(s):
            sync_folder(s, d, overwrite)
        else:
            if overwrite or not os.path.exists(d):
                print(f"Copying {item} to {dst}")
                shutil.copy2(s, d)

def main():
    parser = argparse.ArgumentParser(description="Update Minecraft instance mods and configs.")
    parser.add_argument("instance_name", help="The name of the Prism Launcher instance to update.")
    parser.add_argument("--instances-path", help="Override the default Prism Launcher instances path.")
    
    args = parser.parse_args()

    # Determine the base instances path
    if args.instances_path:
        base_instances_path = args.instances_path
    else:
        appdata = os.environ.get("APPDATA")
        if not appdata:
            # Fallback/Error for non-windows if needed, but requested %appdata%
            print("Error: APPDATA environment variable not found. Please provide --instances-path.")
            sys.exit(1)
        base_instances_path = os.path.join(appdata, "PrismLauncher", "instances")

    instance_path = os.path.join(base_instances_path, args.instance_name)
    
    # Prism instances usually have a 'minecraft' or '.minecraft' folder
    # We'll check for both, prioritizing 'minecraft' which is default for newer versions
    minecraft_path = os.path.join(instance_path, "minecraft")
    if not os.path.exists(minecraft_path):
        minecraft_path = os.path.join(instance_path, ".minecraft")

    if not os.path.exists(instance_path):
        print(f"Error: Instance path {instance_path} does not exist.")
        sys.exit(1)

    print(f"Updating instance at: {minecraft_path}")

    # Local paths (assuming script is run from repo root)
    repo_root = os.path.dirname(os.path.abspath(__file__))
    local_mods = os.path.join(repo_root, "mods")
    local_config = os.path.join(repo_root, "config")

    # Destination paths
    dst_mods = os.path.join(minecraft_path, "mods")
    dst_config = os.path.join(minecraft_path, "config")

    # 1. Apply missing mods (don't overwrite existing ones by default)
    print("\n--- Syncing Mods (Missing Only) ---")
    sync_folder(local_mods, dst_mods, overwrite=False)

    # 2. Apply config changes (overwrite existing ones)
    print("\n--- Syncing Configs (Overwriting) ---")
    sync_folder(local_config, dst_config, overwrite=True)

    print("\nUpdate complete!")

if __name__ == "__main__":
    main()
