import os
import json
import shutil
import sys
import requests
import argparse
import webbrowser
import time
import re
import zipfile
from typing import Optional, List, Dict, Callable, Set, Tuple
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
    loader: str
    minecraft_path: str

@dataclass
class LocalMod:
    filename: str
    mod_id: str
    name: str
    version: str
    path: str

class ModScanner:
    @staticmethod
    def get_local_mods(mods_dir: str) -> List[LocalMod]:
        local_mods = []
        if not os.path.exists(mods_dir): return []
        for file in os.listdir(mods_dir):
            if file.endswith(".jar"):
                path = os.path.join(mods_dir, file)
                mod_info = ModScanner.parse_jar(path)
                if mod_info:
                    local_mods.append(LocalMod(
                        filename=file,
                        mod_id=mod_info.get("id", file),
                        name=mod_info.get("name", file),
                        version=mod_info.get("version", "Unknown"),
                        path=path
                    ))
        return local_mods

    @staticmethod
    def parse_jar(path: str) -> Optional[Dict]:
        try:
            with zipfile.ZipFile(path, 'r') as jar:
                names = jar.namelist()
                if "fabric.mod.json" in names:
                    with jar.open("fabric.mod.json") as f:
                        data = json.load(f)
                        return {"id": data.get("id"), "name": data.get("name"), "version": data.get("version")}
                modern_meta = ["META-INF/neoforge.mods.toml", "META-INF/mods.toml"]
                for meta_file in modern_meta:
                    if meta_file in names:
                        with jar.open(meta_file) as f:
                            content = f.read().decode('utf-8', errors='ignore')
                            mod_id = re.search(r'modId\s*=\s*["\']([^"\']+)["\']', content)
                            name = re.search(r'displayName\s*=\s*["\']([^"\']+)["\']', content)
                            version = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
                            if mod_id:
                                return {
                                    "id": mod_id.group(1),
                                    "name": name.group(1) if name else mod_id.group(1),
                                    "version": version.group(1) if version else "Unknown"
                                }
                if "mcmod.info" in names:
                    with jar.open("mcmod.info") as f:
                        data = json.load(f)
                        if isinstance(data, list): data = data[0]
                        return {"id": data.get("modid"), "name": data.get("name"), "version": data.get("version")}
        except Exception: pass
        return None

    @staticmethod
    def is_newer(current: str, latest: str) -> bool:
        if not latest or latest == "Unknown": return False
        if current == latest: return False
        
        def normalize(v: str) -> str:
            # 1. Remove everything in brackets: [Fabric/Forge/Neo]
            v = re.sub(r'\[.*?\]', '', v)
            # 2. Remove anything after a pipe: | What Durability
            v = v.split('|')[0]
            # 3. Remove common MC version patterns: 1.21.1-
            v = re.sub(r'^[0-9.]+-', '', v.strip())
            # 4. Remove common suffixes: -fabric, +neo, etc.
            v = re.split(r'[-+ ]', v.strip())[0]
            # 5. Clean up surrounding noise
            return v.strip().lower()

        norm_curr = normalize(current)
        norm_latest = normalize(latest)
        if norm_curr == norm_latest: return False
        
        # Very basic check: is it a different string after heavy cleaning?
        # We could do semantic versioning here, but usually "latest" is what we want.
        return norm_curr != norm_latest

class APIClient:
    @staticmethod
    def check_modrinth(mod_id: str, mc_version: str, loader: str) -> Optional[Dict]:
        url = f"https://api.modrinth.com/v2/project/{mod_id}/version"
        loaders = [loader.lower()]
        if loader.lower() == "neoforge": loaders.append("forge")
        params = {"loaders": json.dumps(loaders), "game_versions": json.dumps([mc_version])}
        try:
            resp = requests.get(url, params=params, timeout=5)
            if resp.status_code == 200:
                versions = resp.json()
                if versions:
                    v = versions[0]
                    return {"version": v["version_number"], "url": f"https://modrinth.com/mod/{mod_id}", "source": "Modrinth"}
        except Exception: pass
        return None

    @staticmethod
    def check_curseforge(name: str, mc_version: str, loader: str) -> Optional[Dict]:
        slug = name.lower().replace(" ", "-").replace("?", "")
        url = f"https://api.cfwidget.com/minecraft/mc-mods/{slug}"
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                # Check version-specific list
                version_files = data.get("versions", {}).get(mc_version, [])
                for f in version_files:
                    if any(loader.lower() in v.lower() for v in f.get("versions", [])):
                        return {"version": f.get("display", f.get("name", "Unknown")), "url": f"https://www.curseforge.com/minecraft/mc-mods/{slug}", "source": "CurseForge"}
                # Fallback to main files list
                for f in data.get("files", []):
                    f_vers = f.get("versions", [])
                    if mc_version in f_vers and any(loader.lower() in v.lower() for v in f_vers):
                        return {"version": f.get("display", f.get("name", "Unknown")), "url": f"https://www.curseforge.com/minecraft/mc-mods/{slug}", "source": "CurseForge"}
        except Exception: pass
        return None

class SyncManager:
    def __init__(self, instance: InstanceInfo, logger: Callable[[str], None], status_callback: Optional[Callable[[str, str, str, str, str, str], None]] = None):
        self.instance = instance
        self.logger = logger
        self.status_callback = status_callback # name, curr, latest, status, source, link

    def run(self):
        try:
            repo_root = os.path.dirname(os.path.abspath(__file__))
            local_mods_dir = os.path.join(repo_root, "mods")
            dst_mods = os.path.join(self.instance.minecraft_path, "mods")
            dst_backups = os.path.join(self.instance.minecraft_path, "backups", "mods")
            os.makedirs(dst_mods, exist_ok=True); os.makedirs(dst_backups, exist_ok=True)

            self.logger(f"\n[bold]Scanning local mods...[/bold]")
            local_mods = ModScanner.get_local_mods(local_mods_dir)
            if not local_mods: self.logger("[yellow]No mods found in local mods/ folder.[/yellow]")

            for mod in local_mods:
                self.logger(f"Mod: {mod.name} (Local: {mod.version})")
                if self.status_callback:
                    self.status_callback(mod.name, mod.version, "Checking...", "Checking...", "", "")

                update_info = APIClient.check_modrinth(mod.mod_id, self.instance.mc_version, self.instance.loader)
                if not update_info:
                    update_info = APIClient.check_curseforge(mod.name, self.instance.mc_version, self.instance.loader)

                status, latest_ver, source, link = "[green]Up to date[/green]", mod.version, "Local", ""

                if update_info:
                    latest_ver, link, source = update_info["version"], update_info["url"], update_info["source"]
                    self.logger(f"  Comparing: Local='{mod.version}' with Online='{latest_ver}'")
                    if ModScanner.is_newer(mod.version, latest_ver):
                        status = f"[cyan]Update available[/cyan]"
                        self.logger(f"  [cyan]Update available on {source}![/cyan]")
                
                if self.status_callback:
                    self.status_callback(mod.name, mod.version, latest_ver, status, source, link)

                dst_path = os.path.join(dst_mods, mod.filename)
                if not os.path.exists(dst_path):
                    for item in os.listdir(dst_mods):
                        if mod.mod_id.lower() in item.lower() and item != mod.filename:
                            self.logger(f"  Backing up old instance file: {item}")
                            shutil.move(os.path.join(dst_mods, item), os.path.join(dst_backups, f"{item}.bak"))
                    self.logger(f"  Copying to instance...")
                    shutil.copy2(mod.path, dst_path)

            local_config = os.path.join(repo_root, "config")
            dst_config = os.path.join(self.instance.minecraft_path, "config")
            if os.path.exists(local_config):
                self.logger("\n[bold]Step 2: Syncing Configurations[/bold]")
                count = 0
                for root, dirs, files in os.walk(local_config):
                    rel = os.path.relpath(root, local_config)
                    d_root = os.path.join(dst_config, rel)
                    os.makedirs(d_root, exist_ok=True)
                    for f in files: shutil.copy2(os.path.join(root, f), os.path.join(d_root, f)); count += 1
                self.logger(f"Updated {count} configuration files.")

            self.logger("\n[bold green]Success: Sync Complete![/bold green]")
            return True
        except Exception as e:
            import traceback
            self.logger(f"\n[bold red]FATAL ERROR: {str(e)}[/bold red]")
            with open("error.log", "w", encoding="utf-8") as f: f.write(traceback.format_exc())
            return False

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
        cfg_path, pack_path = os.path.join(path, "instance.cfg"), os.path.join(path, "mmc-pack.json")
        if not os.path.exists(cfg_path): return None
        name = os.path.basename(path)
        with open(cfg_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if line.startswith("name="): name = line.split("=", 1)[1].strip(); break
        mc_v, loader = "Unknown", "vanilla"
        if os.path.exists(pack_path):
            try:
                with open(pack_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for comp in data.get("components", []):
                        uid = comp.get("uid", "")
                        if uid == "net.minecraft": mc_v = comp.get("version", "Unknown")
                        elif "fabric-loader" in uid: loader = "fabric"
                        elif "neoforged" in uid: loader = "neoforge"
                        elif "minecraftforge" in uid: loader = "forge"
                        elif "quilt-loader" in uid: loader = "quilt"
            except Exception: pass
        m_path = os.path.join(path, "minecraft")
        if not os.path.exists(m_path): m_path = os.path.join(path, ".minecraft")
        return InstanceInfo(name, path, mc_v, loader, m_path)

if TUI_AVAILABLE:
    class InstanceSelectScreen(Screen):
        def __init__(self, instances: List[InstanceInfo]):
            super().__init__(); self.instances = instances
        def compose(self) -> ComposeResult:
            yield Header()
            yield Label("Select a Prism Launcher Instance:", id="title")
            with Container(id="list-container"):
                yield ListView(*[ListItem(Label(f"{i.name} ({i.mc_v} - {i.loader})"), id=f"inst_{idx}") for idx, i in enumerate(self.instances)])
            yield Footer()
        def on_list_view_selected(self, event: ListView.Selected):
            idx = int(event.item.id.split("_")[1]); self.app.selected_instance = self.instances[idx]; self.app.push_screen(SyncScreen(self.instances[idx]))

    class SyncScreen(Screen):
        def __init__(self, instance: InstanceInfo):
            super().__init__(); self.instance = instance
        def compose(self) -> ComposeResult:
            yield Header()
            with Vertical(id="details"):
                yield Label(f"Instance: [bold]{self.instance.name}[/bold]")
                yield Label(f"Version:  {self.instance.mc_version} | Loader: {self.instance.loader}")
            yield DataTable(id="mod-table")
            yield Log(id="sync-log")
            with Horizontal(id="actions"):
                yield Button("Sync & Check Updates", variant="primary", id="btn-sync"); yield Button("Back", id="btn-back")
            yield Footer()
        def on_mount(self) -> None:
            table = self.query_one(DataTable)
            self.columns = table.add_columns("Mod", "Local Version", "Latest Version", "Status", "Source")
            self.run_sync()
        def on_button_pressed(self, event: Button.Pressed):
            if event.button.id == "btn-back": self.app.pop_screen()
            elif event.button.id == "btn-sync": self.run_sync()
        def on_data_table_cell_selected(self, event: DataTable.CellSelected):
            row_data = self.query_one(DataTable).get_row(event.cell_key.row_key)
            if hasattr(self, "links") and row_data[0] in self.links: webbrowser.open(self.links[row_data[0]])
        @work(exclusive=True)
        async def run_sync(self):
            log, table = self.query_one("#sync-log", Log), self.query_one(DataTable)
            table.clear(); self.links = {}
            def status_cb(name, curr, latest, status, source, link):
                row_key = None
                for key in table.rows:
                    if table.get_row(key)[0] == name: row_key = key; break
                if not row_key: row_key = table.add_row(name, curr, latest, status, source)
                else:
                    table.update_cell(row_key, self.columns[1], curr); table.update_cell(row_key, self.columns[2], latest)
                    table.update_cell(row_key, self.columns[3], status); table.update_cell(row_key, self.columns[4], source)
                if link: self.links[name] = link
            manager = SyncManager(self.instance, log.write_line, status_cb)
            await self.run_in_thread(manager.run); self.query_one("#btn-sync", Button).label = "Re-Sync"
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
    parser.add_argument("instance", nargs="?", help="Instance name for CLI mode")
    args = parser.parse_args()
    appdata = os.environ.get("APPDATA")
    if not appdata: print("Error: APPDATA environment variable not found."); sys.exit(1)
    base_path = os.path.join(appdata, "PrismLauncher", "instances")
    if args.instance:
        scanner = InstanceScanner(base_path); instances = scanner.scan()
        instance = next((i for i in instances if i.name == args.instance or os.path.basename(i.path) == args.instance), None)
        if not instance: print(f"Error: Instance '{args.instance}' not found."); sys.exit(1)
        manager = SyncManager(instance, print); manager.run()
    else:
        if not TUI_AVAILABLE: print("Error: Textual library not found."); sys.exit(1)
        app = MCManagerApp(); app.run()

if __name__ == "__main__":
    main()
