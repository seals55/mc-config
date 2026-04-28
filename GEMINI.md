# Gemini Project Context: mc-config

## Project Overview
`mc-config` is a comprehensive utility for managing and version-controlling Minecraft configuration files and mods for Prism Launcher instances. It features a modern Terminal User Interface (TUI) that automates instance detection, mod fetching from Modrinth, and asset synchronization.

- **Purpose:** Centralized storage, automated mod fetching, and intelligent deployment for Minecraft instances.
- **Type:** Configuration & Automation Utility.
- **Target Platform:** Prism Launcher (Windows).
- **Core Feature:** Automatic detection of Minecraft version and mod loader (Fabric, Forge, NeoForge, Quilt).

## Directory Structure
- `mods/`: Local storage for mod files (`.jar`). Populated via the TUI or `fetch_mods.py`.
- `config/`: Source directory for configuration files, maintaining the standard `.minecraft/config` structure.
- `mc_manager_tui.py`: The primary interactive management tool (TUI).
- `run.bat`: Windows wrapper script for easy setup and launch.
- `fetch_mods.py`: CLI-based automated mod downloader (fallback).
- `update_instance.py`: CLI-based instance synchronization tool (fallback).
- `README.md`: Basic project identification.
- `GEMINI.md`: Instructional context for AI interactions.

## Key Files
- `run.bat`: Automates virtual environment creation and launches the TUI.
- `mc_manager_tui.py`: An interactive application that scans for Prism Launcher instances, detects their metadata (`mmc-pack.json`), and provides a one-click "Sync & Update" workflow.

## Usage & Development

### 1. Interactive Management (Recommended)
Simply double-click `run.bat` on Windows. This will:
1. Create a Python virtual environment (`.venv`) if it doesn't exist.
2. Install the necessary libraries (`textual`, `requests`).
3. Launch the `mc_manager_tui.py` application.

### 2. Manual/CLI Workflow
For non-interactive use, you can still use the underlying scripts:
- **Fetch Mods:** `python fetch_mods.py`
- **Sync Instance:** `python update_instance.py <Instance_Name>`

### TUI Behavior
- **Instance Detection:** Scans `%APPDATA%/PrismLauncher/instances` and parses `instance.cfg` for names and `mmc-pack.json` for technical versions.
- **Mod Fetching:** Automatically searches Modrinth for mods compatible with the detected MC version and loader.
- **Synchronization:** 
    - **Mods:** Copies missing mods to the instance (prevents duplicates).
    - **Configs:** Overwrites instance configurations with local versions from the `config/` folder.

## AI Interaction Guidelines
- **Mod List:** To update the list of mods managed by the TUI, modify the `self.mod_list` in the `SyncScreen` class within `mc_manager_tui.py`.
- **TUI Enhancements:** When modifying the TUI, utilize the `textual` framework's reactive patterns and ensure that background tasks (like downloads) are handled via `@work` decorators to keep the UI responsive.
- **Safety:** Always verify that local configuration changes are compatible with the target Minecraft version detected by the scanner.
