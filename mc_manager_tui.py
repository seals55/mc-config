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
from dataclasses import dataclass, asdict

try:
    from textual.app import App, ComposeResult
    from textual.widgets import Header, Footer, Button, Static, Label, ListView, ListItem, Log, DataTable
    from textual.containers import Container, Vertical, Horizontal
    from textual.screen import Screen
    from textual import work
    TUI_AVAILABLE = True
except ImportError:
    TUI_AVAILABLE = False

try:
    from rich.console import Console
    from rich import print as rprint
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

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
        if not latest or latest == "Unknown" or latest == "...": return False
        if current == latest: return False
        def normalize(v: str) -> str:
            v = re.sub(r'\[.*?\]', '', v)
            v = v.split('|')[0]
            v = re.sub(r'^[0-9.]+-', '', v.strip())
            v = re.split(r'[-+ ]', v.strip())[0]
            return v.strip().lower()
        nc, nl = normalize(current), normalize(latest)
        return nc != nl and nl != ""

class APICache:
    def __init__(self):
        self.path = "api_cache.json"
        self.data = {}
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r') as f: self.data = json.load(f)
            except: pass

    def get(self, key: str):
        entry = self.data.get(key)
        if entry and time.time() - entry['ts'] < 86400: return entry['val']
        return None

    def set(self, key: str, val: Dict):
        self.data[key] = {'ts': time.time(), 'val': val}
        try:
            with open(self.path, 'w') as f: json.dump(self.data, f)
        except: pass

class APIClient:
    cache = APICache()
    @staticmethod
    def check_modrinth(mod_id: str, mc_version: str, loader: str) -> Optional[Dict]:
        key = f"mr_{mod_id}_{mc_version}_{loader}"
        cached = APIClient.cache.get(key)
        if cached: return cached
        url = f"https://api.modrinth.com/v2/project/{mod_id}/version"
        loaders = [loader.lower()]
        if loader.lower() == "neoforge": loaders.append("forge")
        params = {"loaders": json.dumps(loaders), "game_versions": json.dumps([mc_version])}
        try:
            resp = requests.get(url, params=params, timeout=5)
            if resp.status_code == 200:
                versions = resp.json()
                if versions:
                    res = {"version": versions[0]["version_number"], "url": f"https://modrinth.com/mod/{mod_id}", "source": "Modrinth"}
                    APIClient.cache.set(key, res); return res
        except: pass
        return None

    @staticmethod
    def check_curseforge(name: str, mc_version: str, loader: str) -> Optional[Dict]:
        slug = name.lower().replace(" ", "-").replace("?", "")
        key = f"cf_{slug}_{mc_version}_{loader}"
        cached = APIClient.cache.get(key)
        if cached: return cached
        url = f"https://api.cfwidget.com/minecraft/mc-mods/{slug}"
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json(); res = None
                for f in data.get("versions", {}).get(mc_version, []):
                    if any(loader.lower() in v.lower() for v in f.get("versions", [])):
                        res = {"version": f.get("display", f.get("name", "Unknown")), "url": f"https://www.curseforge.com/minecraft/mc-mods/{slug}", "source": "CurseForge"}; break
                if not res:
                    for f in data.get("files", []):
                        if mc_version in f.get("versions", []) and any(loader.lower() in v.lower() for v in f.get("versions", [])):
                            res = {"version": f.get("display", f.get("name", "Unknown")), "url": f"https://www.curseforge.com/minecraft/mc-mods/{slug}", "source": "CurseForge"}; break
                if res: APIClient.cache.set(key, res); return res
        except: pass
        return None

class SyncManager:
    def __init__(self, instance: InstanceInfo, logger: Callable[[str], None], status_callback: Optional[Callable[[str, str, str, str, str, str, str], None]] = None):
        self.instance = instance; self.logger = logger; self.status_callback = status_callback 

    def run(self):
        try:
            repo_root = os.path.dirname(os.path.abspath(__file__))
            local_mods_dir, dst_mods = os.path.join(repo_root, "mods"), os.path.join(self.instance.minecraft_path, "mods")
            dst_backups = os.path.join(self.instance.minecraft_path, "backups", "mods")
            os.makedirs(dst_mods, exist_ok=True); os.makedirs(dst_backups, exist_ok=True)
            inst_mods = ModScanner.get_local_mods(dst_mods); inst_map = {m.mod_id: m for m in inst_mods}
            local_mods = ModScanner.get_local_mods(local_mods_dir)

            for mod in local_mods:
                inst_mod = inst_map.get(mod.mod_id); inst_ver = inst_mod.version if inst_mod else "Missing"
                sync_s = "[green]Applied[/green]" if inst_mod and not ModScanner.is_newer(inst_ver, mod.version) else ("[cyan]Update Pending[/cyan]" if inst_mod else "[yellow]Not Applied[/yellow]")
                if self.status_callback: self.status_callback(mod.name, mod.version, inst_ver, "...", "...", sync_s, "")

            self.logger("\n[bold]Checking for mod updates...[/bold]")
            for mod in local_mods:
                upd = APIClient.check_modrinth(mod.mod_id, self.instance.mc_version, self.instance.loader)
                if not upd: upd = APIClient.check_curseforge(mod.name, self.instance.mc_version, self.instance.loader)
                inst_mod = inst_map.get(mod.mod_id); inst_ver = inst_mod.version if inst_mod else "Missing"
                status, latest_v, link = "[green]Up to date[/green]", mod.version, ""
                if upd:
                    latest_v, link = upd["version"], upd["url"]
                    if ModScanner.is_newer(mod.version, latest_v): status = f"[cyan]Update available ({upd['source']})[/cyan]"
                sync_s = "[green]Applied[/green]" if inst_mod and not ModScanner.is_newer(inst_ver, mod.version) else ("[cyan]Update Pending[/cyan]" if inst_mod else "[yellow]Not Applied[/yellow]")
                if self.status_callback: self.status_callback(mod.name, mod.version, inst_ver, latest_v, status, sync_s, link)
                dst_path = os.path.join(dst_mods, mod.filename)
                if not os.path.exists(dst_path):
                    for item in os.listdir(dst_mods):
                        if mod.mod_id.lower() in item.lower() and item != mod.filename:
                            self.logger(f"  Backing up {item}"); shutil.move(os.path.join(dst_mods, item), os.path.join(dst_backups, f"{item}.bak"))
                    self.logger(f"  Copying {mod.filename}..."); shutil.copy2(mod.path, dst_path)
                    if self.status_callback: self.status_callback(mod.name, mod.version, mod.version, latest_v, status, "[green]Applied[/green]", link)

            l_cfg, d_cfg = os.path.join(repo_root, "config"), os.path.join(self.instance.minecraft_path, "config")
            if os.path.exists(l_cfg):
                self.logger("\n[bold]Step 2: Syncing Configurations[/bold]"); count = 0
                for root, dirs, files in os.walk(l_cfg):
                    rel = os.path.relpath(root, l_cfg); d_root = os.path.join(d_cfg, rel); os.makedirs(d_root, exist_ok=True)
                    for f in files: shutil.copy2(os.path.join(root, f), os.path.join(d_root, f)); count += 1
                self.logger(f"Updated {count} configuration files.")
            self.logger("\n[bold green]Success: Sync Complete![/bold green]"); return True
        except Exception as e:
            import traceback; self.logger(f"\n[bold red]FATAL ERROR: {str(e)}[/bold red]")
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
        cfg_p, pack_p = os.path.join(path, "instance.cfg"), os.path.join(path, "mmc-pack.json")
        if not os.path.exists(cfg_p): return None
        name = os.path.basename(path)
        with open(cfg_p, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if line.startswith("name="): name = line.split("=", 1)[1].strip(); break
        mv, ldr = "Unknown", "vanilla"
        if os.path.exists(pack_p):
            try:
                with open(pack_p, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for comp in data.get("components", []):
                        uid = comp.get("uid", "")
                        if uid == "net.minecraft": mv = comp.get("version", "Unknown")
                        elif "fabric-loader" in uid: ldr = "fabric"
                        elif "neoforged" in uid: ldr = "neoforge"
                        elif "minecraftforge" in uid: ldr = "forge"
                        elif "quilt-loader" in uid: ldr = "quilt"
            except: pass
        m_p = os.path.join(path, "minecraft")
        if not os.path.exists(m_p): m_p = os.path.join(path, ".minecraft")
        return InstanceInfo(name, path, mv, ldr, m_p)

def cli_logger(msg: str):
    if RICH_AVAILABLE:
        rprint(msg)
    else:
        # Simple ANSI fallback for common rich tags
        m = msg.replace("[bold]", "\033[1m").replace("[/bold]", "\033[22m")
        m = m.replace("[green]", "\033[32m").replace("[/green]", "\033[39m")
        m = m.replace("[red]", "\033[31m").replace("[/red]", "\033[39m")
        m = m.replace("[yellow]", "\033[33m").replace("[/yellow]", "\033[39m")
        m = m.replace("[cyan]", "\033[36m").replace("[/cyan]", "\033[39m")
        m = m.replace("[bold green]", "\033[1;32m")
        m = m.replace("[bold red]", "\033[1;31m")
        print(m + "\033[0m")

if TUI_AVAILABLE:
    class InstanceSelectScreen(Screen):
        def __init__(self, instances: List[InstanceInfo]):
            super().__init__(); self.instances = instances
        def compose(self) -> ComposeResult:
            yield Header(); yield Label("Select a Prism Launcher Instance:", id="title")
            with Container(id="list-container"):
                yield ListView(*[ListItem(Label(f"{i.name} ({i.mc_version} - {i.loader})"), id=f"inst_{idx}") for idx, i in enumerate(self.instances)])
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
            yield DataTable(id="mod-table"); yield Log(id="sync-log")
            with Horizontal(id="actions"):
                yield Button("Sync & Check Updates", variant="primary", id="btn-sync"); yield Button("Back", id="btn-back")
            yield Footer()
        def on_mount(self) -> None:
            table = self.query_one(DataTable)
            self.columns = table.add_columns("Mod", "Local", "Instance", "Latest", "Update Status", "Sync Status")
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
            def status_cb(name, local, instance, latest, status, sync, link):
                row_key = None
                for key in table.rows:
                    if table.get_row(key)[0] == name: row_key = key; break
                if not row_key: row_key = table.add_row(name, local, instance, latest, status, sync)
                else:
                    table.update_cell(row_key, self.columns[1], local); table.update_cell(row_key, self.columns[2], instance)
                    table.update_cell(row_key, self.columns[3], latest); table.update_cell(row_key, self.columns[4], status)
                    table.update_cell(row_key, self.columns[5], sync)
                if link: self.links[name] = link
            manager = SyncManager(self.instance, log.write_line, status_cb)
            import asyncio
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, manager.run)
            self.query_one("#btn-sync", Button).label = "Re-Sync"

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
        cli_logger(f"Starting CLI sync for: [bold cyan]{instance.name}[/bold cyan] ({instance.mc_version})")
        manager = SyncManager(instance, cli_logger)
        manager.run()
    else:
        if not TUI_AVAILABLE: print("Error: Textual library not found. Use CLI mode by providing an instance name."); sys.exit(1)
        app = MCManagerApp(); app.run()

if __name__ == "__main__":
    main()
