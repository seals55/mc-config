import os
import json
import shutil
import sys
import requests
import argparse
import webbrowser
import time
from datetime import datetime
from typing import Optional, List, Dict, Callable
from dataclasses import dataclass

try:
    from textual.app import App, ComposeResult
    from textual.widgets import Header, Footer, Button, Static, Label, ListView, ListItem, Log, DataTable
    from textual.containers import Container, Vertical, Horizontal
    from textual.screen import Screen
    from textual import work
    TUI_AVAILABLE = True
except ImportError:
    TUI_AVAILABLE = False

@dataclass
class InstanceInfo:
    name: str
    path: str
    mc_version: str
    loader: str # forge, neoforge, fabric, quilt, vanilla
    minecraft_path: str

class ModrinthAPI:
    @staticmethod
    def get_project_info(slug_or_id: str):
        url = f"https://api.modrinth.com/v2/project/{slug_or_id}"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            return None
        return None

    @staticmethod
    def get_latest_version(slug: str, mc_version: str, loader: str):
        url = f"https://api.modrinth.com/v2/project/{slug}/version"
        loaders = [loader.lower()]
        if loader.lower() == "neoforge":
            loaders.append("forge")
            
        params = {
            "loaders": json.dumps(loaders),
            "game_versions": json.dumps([mc_version])
        }
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                versions = response.json()
                return versions[0] if versions else None
        except Exception:
            return None
        return None

class CurseForgeAPI:
    @staticmethod
    def get_latest_file_id(slug: str, mc_version: str, loader: str) -> Optional[int]:
        url = f"https://api.cfwidget.com/minecraft/mc-mods/{slug}"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                version_files = data.get("versions", {}).get(mc_version, [])
                for f in version_files:
                    if any(loader.lower() in v.lower() for v in f.get("versions", [])):
                        return f.get("id")
                files = data.get("files", [])
                for f in files:
                    f_versions = f.get("versions", [])
                    if mc_version in f_versions and any(loader.lower() in v.lower() for v in f_versions):
                        return f.get("id")
        except Exception: pass
        return None

class SyncManager:
    CF_LOADER_IDS = {"forge": 1, "fabric": 4, "quilt": 5, "neoforge": 6}

    def __init__(self, instance: InstanceInfo, mod_list: List[str], logger: Callable[[str], None], status_callback: Optional[Callable[[str, str, str, str], None]] = None):
        self.instance = instance
        self.mod_list = mod_list
        self.logger = logger
        self.status_callback = status_callback 

    def run(self):
        try:
            repo_root = os.path.dirname(os.path.abspath(__file__))
            local_config = os.path.join(repo_root, "config")
            local_manual = os.path.join(repo_root, "manual_downloads")
            os.makedirs(local_config, exist_ok=True)
            os.makedirs(local_manual, exist_ok=True)

            dst_mods = os.path.join(self.instance.minecraft_path, "mods")
            dst_config = os.path.join(self.instance.minecraft_path, "config")
            dst_backups = os.path.join(self.instance.minecraft_path, "backups", "mods")
            meta_path = os.path.join(self.instance.minecraft_path, "mod_meta.json")
            
            os.makedirs(dst_mods, exist_ok=True)
            os.makedirs(dst_config, exist_ok=True)
            os.makedirs(dst_backups, exist_ok=True)

            mod_meta = {}
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, 'r') as f: mod_meta = json.load(f)
                except Exception: mod_meta = {}

            self.logger("\n[bold]Step 1: Checking Mods & Required Dependencies[/bold]")
            
            to_process = list(self.mod_list)
            processed_norm = set() # Track normalized slugs to avoid cf:mod vs mod duplication
            updated_count = 0
            installed_count = 0
            final_resolved_slugs = set()

            while to_process:
                raw_slug = to_process.pop(0)
                is_cf = raw_slug.startswith("cf:")
                norm_slug = raw_slug[3:] if is_cf else raw_slug
                
                if norm_slug in processed_norm: continue
                processed_norm.add(norm_slug)

                if is_cf:
                    final_resolved_slugs.add(raw_slug)
                    if self.handle_cf_mod(raw_slug, norm_slug, dst_mods, dst_backups):
                        updated_count += 1 # Rough count
                    continue

                # Modrinth Logic
                project_info = ModrinthAPI.get_project_info(norm_slug)
                if not project_info:
                    if self.status_callback: self.status_callback(raw_slug, "N/A", "Unknown", "[yellow]Not on Modrinth[/yellow]")
                    final_resolved_slugs.add(raw_slug)
                    continue

                # project_info already contains title and slug
                display_name = project_info.get("title", norm_slug)
                mod_slug = project_info.get("slug", norm_slug)
                final_resolved_slugs.add(mod_slug if not is_cf else raw_slug)

                # Use display_name for UI key to match the row
                ui_key = display_name 

                version_data = ModrinthAPI.get_latest_version(mod_slug, self.instance.mc_version, self.instance.loader)
                if version_data:
                    project_id = version_data['project_id']
                    latest_ver = version_data['version_number']
                    
                    deps = version_data.get('dependencies', [])
                    for dep in deps:
                        if dep.get('dependency_type') == 'required':
                            dep_id = dep.get('project_id')
                            if dep_id and dep_id not in processed_norm:
                                # Fetch dependency info to show name in UI while checking
                                dep_info = ModrinthAPI.get_project_info(dep_id)
                                dep_name = dep_info.get("title", dep_id) if dep_info else dep_id
                                if self.status_callback:
                                    self.status_callback(dep_name, "N/A", "Pending...", "[yellow]Queued dependency...[/yellow]")
                                to_process.append(dep_id)

                    file_data = next((f for f in version_data['files'] if f['primary']), version_data['files'][0])
                    filename, url = file_data['filename'], file_data['url']
                    new_mod_path = os.path.join(dst_mods, filename)
                    old_info = mod_meta.get(project_id)
                    
                    if isinstance(old_info, dict):
                        old_filename, old_version = old_info.get("file"), old_info.get("version", "Unknown")
                    else:
                        old_filename = old_info if isinstance(old_info, str) else None
                        old_version = "Unknown" if old_filename else "None"

                    curr_ver_display = old_version if old_filename else "Not Installed"
                    if self.status_callback: self.status_callback(ui_key, curr_ver_display, latest_ver, "[yellow]Processing...[/yellow]")

                    if old_filename and old_filename != filename:
                        if self.backup_and_download(ui_key, display_name, old_filename, filename, url, dst_mods, dst_backups, new_mod_path, project_id, latest_ver, mod_meta):
                            updated_count += 1
                    elif not os.path.exists(new_mod_path):
                        self.logger(f"Installing {display_name} -> {filename}...")
                        if self.download_mod(url, new_mod_path):
                            mod_meta[project_id] = {"file": filename, "version": latest_ver}
                            if self.status_callback: self.status_callback(ui_key, latest_ver, latest_ver, "[green]Installed[/green]")
                            installed_count += 1
                    else:
                        self.logger(f"Mod {filename} is up to date.")
                        if self.status_callback: self.status_callback(ui_key, latest_ver, latest_ver, "[green]Up to date[/green]")
                        mod_meta[project_id] = {"file": filename, "version": latest_ver}
                else:
                    self.logger(f"  [yellow]No compatible version found for {display_name}[/yellow]")
                    if self.status_callback: self.status_callback(ui_key, "N/A", "N/A", "[yellow]No compat ver[/yellow]")

            # Deduplicate final list for mods.json
            deduped_slugs = set()
            for s in final_resolved_slugs:
                if s.startswith("cf:"):
                    deduped_slugs.add(s)
                    base = s[3:]
                    if base in deduped_slugs: deduped_slugs.remove(base)
                else:
                    if f"cf:{s}" not in final_resolved_slugs: deduped_slugs.add(s)

            if set(self.mod_list) != deduped_slugs:
                self.logger("\nUpdating mods.json with resolved slugs...")
                self.save_mod_list(repo_root, list(deduped_slugs))

            with open(meta_path, 'w') as f: json.dump(mod_meta, f, indent=4)
            self.logger(f"\nSummary: {installed_count} installed, {updated_count} updated.")

            self.logger("\n[bold]Step 2: Syncing Configurations[/bold]")
            if os.path.exists(local_config):
                config_count = 0
                for root, dirs, files in os.walk(local_config):
                    rel_path = os.path.relpath(root, local_config)
                    dest_root = os.path.join(dst_config, rel_path)
                    os.makedirs(dest_root, exist_ok=True)
                    for f in files:
                        shutil.copy2(os.path.join(root, f), os.path.join(dest_root, f))
                        config_count += 1
                self.logger(f"Updated {config_count} configuration files.")

            self.logger("\n[bold green]Success: Sync Complete![/bold green]")
            return True
        except Exception as e:
            import traceback
            error_msg = f"FATAL ERROR: {str(e)}\n{traceback.format_exc()}"
            self.logger(f"\n[bold red]FATAL ERROR: {str(e)}[/bold red]")
            with open("error.log", "w", encoding="utf-8") as f: f.write(error_msg)
            return False

    def handle_cf_mod(self, raw_slug: str, slug: str, dst_mods: str, dst_backups: str) -> bool:
        self.logger(f"\n[bold cyan]CurseForge Mod: {slug}[/bold cyan]")
        if self.status_callback: self.status_callback(raw_slug, "Manual", "Resolving...", "[yellow]Resolving File ID...[/yellow]")
        
        file_id = CurseForgeAPI.get_latest_file_id(slug, self.instance.mc_version, self.instance.loader)
        if file_id:
            url = f"https://www.curseforge.com/minecraft/mc-mods/{slug}/download/{file_id}"
            self.logger(f"Found File ID: {file_id}. Opening direct download page...")
        else:
            loader_id = self.CF_LOADER_IDS.get(self.instance.loader.lower(), 1)
            url = f"https://www.curseforge.com/minecraft/mc-mods/{slug}/files?version={self.instance.mc_version}&gameVersionTypeId={loader_id}"
            self.logger(f"[yellow]Could not resolve File ID. Opening files page...[/yellow]")
        
        if self.status_callback: self.status_callback(raw_slug, "Manual", str(file_id) if file_id else "Latest", "[blue]Waiting for download...[/blue]")
        
        webbrowser.open(url)
        downloads_path = os.path.join(os.path.expanduser("~"), "Downloads")
        self.logger(f"Monitoring {downloads_path} for new .jar file...")
        
        start_time = time.time()
        initial_jars = {f for f in os.listdir(downloads_path) if f.endswith(".jar")}
        found_file = None
        while time.time() - start_time < 120:
            current_jars = {f for f in os.listdir(downloads_path) if f.endswith(".jar")}
            new_jars = current_jars - initial_jars
            if new_jars:
                found_file = max(new_jars, key=lambda x: os.path.getmtime(os.path.join(downloads_path, x)))
                break
            time.sleep(1)
        
        if found_file and (slug.replace("-", "").lower() in found_file.replace("_", "").lower() or slug.lower() in found_file.lower()):
            self.logger(f"Found {found_file}. Moving to instance...")
            for item in os.listdir(dst_mods):
                if item != found_file and (slug.lower() in item.lower() or slug.replace("-","").lower() in item.lower()):
                    shutil.move(os.path.join(dst_mods, item), os.path.join(dst_backups, f"{item}.bak"))
            shutil.move(os.path.join(downloads_path, found_file), os.path.join(dst_mods, found_file))
            self.logger(f"  [green]Successfully installed {found_file}[/green]")
            if self.status_callback: self.status_callback(raw_slug, "Installed", "Latest", "[green]Synced (Manual)[/green]")
            return True
        else:
            self.logger(f"[red]Download not found or timed out.[/red]")
            return False

    def backup_and_download(self, raw_slug, display_name, old_filename, filename, url, dst_mods, dst_backups, new_mod_path, project_id, latest_ver, mod_meta):
        old_path = os.path.join(dst_mods, old_filename)
        if os.path.exists(old_path):
            backup_path = os.path.join(dst_backups, f"{old_filename}.bak")
            shutil.move(old_path, backup_path)
        if self.download_mod(url, new_mod_path):
            mod_meta[project_id] = {"file": filename, "version": latest_ver}
            if self.status_callback: self.status_callback(raw_slug, latest_ver, latest_ver, "[green]Updated[/green]")
            return True
        return False

    def download_mod(self, url, path) -> bool:
        try:
            resp = requests.get(url, stream=True)
            if resp.status_code == 200:
                with open(path, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=8192): f.write(chunk)
                return True
        except Exception: pass
        return False

    def save_mod_list(self, repo_root: str, mods: List[str]):
        try:
            with open(os.path.join(repo_root, "mods.json"), 'w') as f: json.dump(sorted(list(set(mods))), f, indent=4)
        except Exception: pass

class InstanceScanner:
    def __init__(self, base_path: str): self.base_path = base_path
    def scan(self) -> List[InstanceInfo]:
        instances = []
        if not os.path.exists(self.base_path): return []
        for folder in os.listdir(self.base_path):
            path = os.path.join(self.base_path, folder)
            if os.path.isdir(path):
                info = self.parse_instance(path)
                if info: instances.append(info)
        return sorted(instances, key=lambda x: x.name)
    def parse_instance(self, path: str) -> Optional[InstanceInfo]:
        cfg_path = os.path.join(path, "instance.cfg")
        pack_path = os.path.join(path, "mmc-pack.json")
        if not os.path.exists(cfg_path): return None
        name = os.path.basename(path)
        with open(cfg_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if line.startswith("name="): name = line.split("=", 1)[1].strip(); break
        mc_version, loader = "Unknown", "vanilla"
        if os.path.exists(pack_path):
            try:
                with open(pack_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for comp in data.get("components", []):
                        uid = comp.get("uid", "")
                        if uid == "net.minecraft": mc_version = comp.get("version", "Unknown")
                        elif "fabric-loader" in uid: loader = "fabric"
                        elif "neoforged" in uid: loader = "neoforge"
                        elif "minecraftforge" in uid: loader = "forge"
                        elif "quilt-loader" in uid: loader = "quilt"
            except Exception: pass
        minecraft_path = os.path.join(path, "minecraft")
        if not os.path.exists(minecraft_path): minecraft_path = os.path.join(path, ".minecraft")
        return InstanceInfo(name, path, mc_version, loader, minecraft_path)

if TUI_AVAILABLE:
    class InstanceSelectScreen(Screen):
        def __init__(self, instances: List[InstanceInfo]):
            super().__init__(); self.instances = instances
        def compose(self) -> ComposeResult:
            yield Header()
            yield Label("Select a Prism Launcher Instance:", id="title")
            with Container(id="list-container"):
                yield ListView(*[ListItem(Label(f"{i.name} ({i.mc_version} - {i.loader})"), id=f"inst_{idx}") for idx, i in enumerate(self.instances)])
            yield Footer()
        def on_list_view_selected(self, event: ListView.Selected):
            idx = int(event.item.id.split("_")[1])
            self.app.selected_instance = self.instances[idx]
            self.app.push_screen(SyncScreen(self.instances[idx]))

    class SyncScreen(Screen):
        def __init__(self, instance: InstanceInfo):
            super().__init__(); self.instance = instance; self.mod_list = self.load_mod_list()
        def load_mod_list(self) -> List[str]:
            repo_root = os.path.dirname(os.path.abspath(__file__))
            mods_json = os.path.join(repo_root, "mods.json")
            if os.path.exists(mods_json):
                try:
                    with open(mods_json, 'r') as f: return json.load(f)
                except Exception: pass
            return ["cf:infinite-storage-cell"]
        def compose(self) -> ComposeResult:
            yield Header()
            with Vertical(id="details"):
                yield Label(f"Instance: [bold]{self.instance.name}[/bold]")
                yield Label(f"Version:  {self.instance.mc_version}")
                yield Label(f"Loader:   {self.instance.loader}")
                yield Label(f"Path:     {self.instance.minecraft_path}")
            yield DataTable(id="mod-table")
            yield Log(id="sync-log")
            with Horizontal(id="actions"):
                yield Button("Sync & Update", variant="primary", id="btn-sync")
                yield Button("Back", id="btn-back")
            yield Footer()
        def on_mount(self) -> None:
            table = self.query_one(DataTable)
            self.columns = table.add_columns("Mod", "Current Version", "Latest Version", "Status")
            for mod in self.mod_list: table.add_row(mod, "Pending...", "Pending...", "Ready")
            self.run_sync()
        def on_button_pressed(self, event: Button.Pressed):
            if event.button.id == "btn-back": self.app.pop_screen()
            elif event.button.id == "btn-sync": self.run_sync()
        @work(exclusive=True)
        async def run_sync(self):
            log, table = self.query_one("#sync-log", Log), self.query_one(DataTable)
            def status_cb(raw_slug, curr, latest, status):
                row_key = None
                for key in table.rows:
                    if table.get_row(key)[0] == raw_slug: row_key = key; break
                if not row_key: row_key = table.add_row(raw_slug, curr, latest, status)
                else:
                    if curr: table.update_cell(row_key, self.columns[1], curr)
                    if latest: table.update_cell(row_key, self.columns[2], latest)
                    table.update_cell(row_key, self.columns[3], status)
            manager = SyncManager(self.instance, self.mod_list, log.write_line, status_cb)
            await self.run_in_thread(manager.run)
            self.query_one("#btn-sync", Button).label = "Sync Again"
        async def run_in_thread(self, func):
            import asyncio
            return await asyncio.get_event_loop().run_in_executor(None, func)

    class MCManagerApp(App):
        CSS = """
        #list-container { height: 10; border: solid green; margin: 1; }
        #details { background: $boost; padding: 1; margin-bottom: 1; }
        #mod-table { height: 1fr; border: double gray; margin: 1 0; }
        #sync-log { height: 8; border: solid gray; margin-bottom: 1; }
        #actions { height: 3; align: center middle; }
        Button { margin: 0 1; }
        #title { text-align: center; width: 100%; color: $accent; }
        """
        BINDINGS = [("q", "quit", "Quit")]
        def on_mount(self) -> None:
            appdata = os.environ.get("APPDATA")
            base_path = os.path.join(appdata, "PrismLauncher", "instances") if appdata else ""
            instances = InstanceScanner(base_path).scan()
            if not instances: self.exit(f"No instances found in {base_path}"); return
            self.push_screen(InstanceSelectScreen(instances))

def main():
    parser = argparse.ArgumentParser(description="Minecraft Instance Manager")
    parser.add_argument("instance", nargs="?", help="Instance name for CLI mode (skips TUI)")
    args = parser.parse_args()
    appdata = os.environ.get("APPDATA")
    if not appdata: print("Error: APPDATA environment variable not found."); sys.exit(1)
    base_path = os.path.join(appdata, "PrismLauncher", "instances")
    if args.instance:
        scanner = InstanceScanner(base_path)
        instances = scanner.scan()
        instance = next((i for i in instances if i.name == args.instance or os.path.basename(i.path) == args.instance), None)
        if not instance: print(f"Error: Instance '{args.instance}' not found."); sys.exit(1)
        repo_root = os.path.dirname(os.path.abspath(__file__))
        mods_json = os.path.join(repo_root, "mods.json")
        mod_list = ["cf:infinite-storage-cell"]
        if os.path.exists(mods_json):
            with open(mods_json, 'r') as f: mod_list = json.load(f)
        print(f"Starting CLI sync for: {instance.name} ({instance.mc_version})")
        manager = SyncManager(instance, mod_list, print)
        manager.run()
    else:
        if not TUI_AVAILABLE: print("Error: Textual library not found. Run with an instance name for CLI mode or install textual."); sys.exit(1)
        app = MCManagerApp()
        app.run()

if __name__ == "__main__":
    main()
