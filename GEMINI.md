# Gemini Project Context: mc-config

## Project Overview
`mc-config` is a utility for managing Minecraft configuration files and mods for Prism Launcher instances. It uses a local-first workflow where mods are placed in a `mods/` directory and synchronized to specific instances.

- **Purpose:** Centralized storage, update checking, and intelligent deployment for Minecraft instances.
- **Type:** Configuration & Automation Utility.
- **Target Platform:** Prism Launcher (Windows).

## Directory Structure
- `mods/`: **Primary source for mods.** Place your `.jar` files here.
- `config/`: Source directory for configuration files.
- `mc_manager_tui.py`: The interactive management tool (TUI & CLI).
- `run.bat`: Windows wrapper script for easy setup and launch.

## Key Features
- **Auto-Detection:** Identifies mods in the `mods/` folder by peeking into JAR metadata.
- **Update Checking:** Checks Modrinth and CurseForge for newer versions based on local mod IDs.
- **Direct Links:** Provides clickable links in the TUI to download pages if updates are found.
- **Instance Sync:** Synchronizes the local `mods/` and `config/` folders to selected Prism Launcher instances.

## Usage & Development

### 1. Adding Mods
Place any mod `.jar` files you want to manage into the local `mods/` directory.

### 2. Interactive Management (TUI)
Double-click `run.bat` or run `python mc_manager_tui.py`.
- Select an instance to start the sync and update check.
- **Click on a mod row** in the table to open its download page if an update is available.

### 3. Headless Management (CLI)
Bypass the TUI by providing the instance name:
```bash
python mc_manager_tui.py "Instance Name"
```

### TUI Behavior
- **Update System:** Tracks local versions and identifies newer releases online.
- **Backup System:** When a mod is updated in the local folder and synced, the instance's old version is moved to `backups/mods/`.
- **Config Sync:** Overwrites instance configurations with local versions from the project's `config/` folder.

## AI Interaction Guidelines
- **Mod List:** To update the list of mods managed by the TUI, modify the `self.mod_list` in the `SyncScreen` class within `mc_manager_tui.py`.
- **TUI Enhancements:** When modifying the TUI, utilize the `textual` framework's reactive patterns and ensure that background tasks (like downloads) are handled via `@work` decorators to keep the UI responsive.
- **Safety:** Always verify that local configuration changes are compatible with the target Minecraft version detected by the scanner.
