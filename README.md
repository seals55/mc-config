# mc-config

A comprehensive utility for managing and version-controlling Minecraft configuration files and mods for Prism Launcher instances.

## Features

- **Interactive TUI:** A modern Terminal User Interface for easy instance management.
- **Automatic Detection:** Scans for Prism Launcher instances and automatically identifies Minecraft versions and mod loaders (Fabric, Forge, NeoForge, Quilt).
- **Modrinth Integration:** Automatically fetches and downloads the latest compatible mod versions from Modrinth.
- **Configuration Sync:** Effortlessly synchronize your local configuration files to specific Minecraft instances.
- **Easy Setup:** Includes a Windows wrapper script that handles virtual environment creation and dependency installation.

## Quick Start (Windows)

1.  Clone this repository.
2.  Double-click **`run.bat`**.
3.  The script will set up a Python virtual environment, install dependencies, and launch the manager.
4.  Select your Prism Launcher instance from the list and click **Sync & Update**.

## Manual Usage

If you prefer using the command line directly:

### 1. Fetch Latest Mods
Downloads defined mods from Modrinth to the local `mods/` folder:
```bash
python fetch_mods.py
```

### 2. Update a Minecraft Instance
Applies local mods and configurations to a specific Prism Launcher instance:
```bash
python update_instance.py <Instance_Name>
```

## Requirements

- Python 3.7+
- [Prism Launcher](https://prismlauncher.org/)
- Internet connection (for mod fetching)

## Directory Structure

- `mods/`: Local storage for mod files (`.jar`).
- `config/`: Source directory for configuration files (follows the `.minecraft/config` structure).
- `mc_manager_tui.py`: The primary interactive management tool.
- `run.bat`: One-click setup and launch script for Windows.
- `fetch_mods.py`: Automated mod downloader.
- `update_instance.py`: Instance synchronization script.

## Contributing

To add new mods, add their Modrinth slugs to the `mods.json` file. The manager will automatically download all required dependencies.



