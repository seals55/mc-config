# Gemini Project Context: mc-config

## Project Overview
`mc-config` is a comprehensive utility for managing and version-controlling Minecraft configuration files for Prism Launcher instances. It features a modern Terminal User Interface (TUI) that automates instance detection, on-demand mod fetching from Modrinth, and asset synchronization.

- **Purpose:** Centralized storage and intelligent deployment for Minecraft instances.
- **Type:** Configuration & Automation Utility.
- **Target Platform:** Prism Launcher (Windows).
- **Core Feature:** Automatic detection of Minecraft version and mod loader (Fabric, Forge, NeoForge, Quilt).

## Directory Structure
- `config/`: Source directory for configuration files.
- `mods.json`: A list of Modrinth slugs for the mods you want to manage.
- `mc_manager_tui.py`: The primary interactive management tool (TUI).
- `run.bat`: Windows wrapper script for easy setup and launch.

## Key Files
- `mods.json`: Edit this file to add or remove mods. The TUI will automatically handle required dependencies.
- `mc_manager_tui.py`: Now features recursive dependency resolution from Modrinth.

## Usage & Development

### Adding More Mods
To add more mods, simply add their Modrinth slugs to the `mods.json` file. For example:
```json
[
    "infinite-storage-cell",
    "ae2",
    "sodium"
]
```
The manager will automatically find and download any **required dependency mods** (like `cloth-config` or `indium`) that are needed for your selected mods to run.

### TUI Behavior
- **Dependency Resolution:** When you sync, the manager checks the latest version of each mod in `mods.json`, identifies all required dependencies, and downloads them directly to the instance if they are missing.
- **Update System:** Tracks installed mods via `mod_meta.json` in the instance folder. If a newer version of a mod is found, the old file is moved to a `backups/mods/` directory within the instance folder before the new one is downloaded.
- **Config Sync:** Overwrites instance configurations with local versions from the project's `config/` folder.

## AI Interaction Guidelines
- **Mod List:** To update the list of mods managed by the TUI, modify the `self.mod_list` in the `SyncScreen` class within `mc_manager_tui.py`.
- **TUI Enhancements:** When modifying the TUI, utilize the `textual` framework's reactive patterns and ensure that background tasks (like downloads) are handled via `@work` decorators to keep the UI responsive.
- **Safety:** Always verify that local configuration changes are compatible with the target Minecraft version detected by the scanner.
