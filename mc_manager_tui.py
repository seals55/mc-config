import os
import json
import shutil
import sys
import requests
from typing import Optional, List, Dict
from dataclasses import dataclass

try:
    from textual.app import App, ComposeResult
    from textual.widgets import Header, Footer, Button, Static, Label, ListView, ListItem, Log, DataTable
    from textual.containers import Container, Vertical, Horizontal
    from textual.screen import Screen
    from textual import work
except ImportError:
    print("Error: The 'textual' library is required for the TUI.")
    print("Please install it with: pip install textual requests")
    sys.exit(1)

@dataclass
class InstanceInfo:
    name: str
    path: str
    mc_version: str
    loader: str # forge, neoforge, fabric, quilt, vanilla
    minecraft_path: str

class ModrinthAPI:
    @staticmethod
    def get_latest_version(slug: str, mc_version: str, loader: str):
        url = f"https://api.modrinth.com/v2/project/{slug}/version"
        params = {
            "loaders": f'["{loader.lower()}"]',
            "game_versions": f'["{mc_version}"]'
        }
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                versions = response.json()
                return versions[0] if versions else None
        except Exception:
            return None
        return None

class InstanceScanner:
    def __init__(self, base_path: str):
        self.base_path = base_path

    def scan(self) -> List[InstanceInfo]:
        instances = []
        if not os.path.exists(self.base_path):
            return []

        for folder in os.listdir(self.base_path):
            path = os.path.join(self.base_path, folder)
            if os.path.isdir(path):
                info = self.parse_instance(path)
                if info:
                    instances.append(info)
        return sorted(instances, key=lambda x: x.name)

    def parse_instance(self, path: str) -> Optional[InstanceInfo]:
        cfg_path = os.path.join(path, "instance.cfg")
        pack_path = os.path.join(path, "mmc-pack.json")
        
        if not os.path.exists(cfg_path):
            return None

        # Parse Name
        name = os.path.basename(path)
        with open(cfg_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if line.startswith("name="):
                    name = line.split("=", 1)[1].strip()
                    break

        # Parse Version and Loader
        mc_version = "Unknown"
        loader = "vanilla"
        if os.path.exists(pack_path):
            try:
                with open(pack_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    components = data.get("components", [])
                    for comp in components:
                        uid = comp.get("uid", "")
                        version = comp.get("version", "Unknown")
                        if uid == "net.minecraft":
                            mc_version = version
                        elif "fabric-loader" in uid:
                            loader = "fabric"
                        elif "neoforged" in uid:
                            loader = "neoforge"
                        elif "minecraftforge" in uid:
                            loader = "forge"
                        elif "quilt-loader" in uid:
                            loader = "quilt"
            except Exception as e:
                print(f"Error parsing mmc-pack.json at {pack_path}: {e}")
                pass

        # Determine minecraft folder
        minecraft_path = os.path.join(path, "minecraft")
        if not os.path.exists(minecraft_path):
            minecraft_path = os.path.join(path, ".minecraft")

        return InstanceInfo(name, path, mc_version, loader, minecraft_path)

class InstanceSelectScreen(Screen):
    def __init__(self, instances: List[InstanceInfo]):
        super().__init__()
        self.instances = instances

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Select a Prism Launcher Instance:", id="title")
        with Container(id="list-container"):
            yield ListView(*[ListItem(Label(f"{i.name} ({i.mc_version} - {i.loader})"), id=f"inst_{idx}") 
                           for idx, i in enumerate(self.instances)])
        yield Footer()

    def on_list_view_selected(self, event: ListView.Selected):
        idx = int(event.item.id.split("_")[1])
        self.app.selected_instance = self.instances[idx]
        self.app.push_screen(SyncScreen(self.instances[idx]))

class SyncScreen(Screen):
    def __init__(self, instance: InstanceInfo):
        super().__init__()
        self.instance = instance
        self.mod_list = self.load_mod_list()

    def load_mod_list(self) -> List[str]:
        repo_root = os.path.dirname(os.path.abspath(__file__))
        mods_json = os.path.join(repo_root, "mods.json")
        if os.path.exists(mods_json):
            try:
                with open(mods_json, 'r') as f:
                    return json.load(f)
            except Exception:
                return ["infinite-storage-cell"]
        return ["infinite-storage-cell"]

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
        for mod in self.mod_list:
            table.add_row(mod, "Pending...", "Pending...", "Ready")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "btn-back":
            self.app.pop_screen()
        elif event.button.id == "btn-sync":
            self.run_sync()

    @work(exclusive=True)
    async def run_sync(self):
        log = self.query_one("#sync-log", Log)
        table = self.query_one(DataTable)
        log.write_line("Starting synchronization...")
        
        # Column indices/keys for easier access
        col_mod, col_curr, col_latest, col_status = self.columns

        try:
            repo_root = os.path.dirname(os.path.abspath(__file__))
            local_config = os.path.join(repo_root, "config")
            os.makedirs(local_config, exist_ok=True)

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
                    with open(meta_path, 'r') as f:
                        mod_meta = json.load(f)
                except Exception:
                    mod_meta = {}

            log.write_line("\n[bold]Step 1: Checking Mods & Required Dependencies[/bold]")
            
            to_process = list(self.mod_list)
            processed = set()
            updated_count = 0
            installed_count = 0

            while to_process:
                slug_or_id = to_process.pop(0)
                if slug_or_id in processed:
                    continue
                processed.add(slug_or_id)

                # Find existing row or add new one
                row_key = None
                for key in table.rows:
                    if table.get_row(key)[0] == slug_or_id:
                        row_key = key
                        break
                
                if row_key:
                    table.update_cell(row_key, col_status, "[yellow]Checking...[/yellow]")
                else:
                    row_key = table.add_row(slug_or_id, "N/A", "Pending...", "[yellow]Checking...[/yellow]")

                version_data = ModrinthAPI.get_latest_version(slug_or_id, self.instance.mc_version, self.instance.loader)
                
                if version_data:
                    project_id = version_data['project_id']
                    latest_ver = version_data['version_number']
                    table.update_cell(row_key, col_latest, latest_ver)

                    deps = version_data.get('dependencies', [])
                    for dep in deps:
                        if dep.get('dependency_type') == 'required':
                            dep_id = dep.get('project_id')
                            if dep_id and dep_id not in processed:
                                to_process.append(dep_id)

                    file_data = next((f for f in version_data['files'] if f['primary']), version_data['files'][0])
                    filename = file_data['filename']
                    url = file_data['url']
                    
                    new_mod_path = os.path.join(dst_mods, filename)
                    old_info = mod_meta.get(project_id)
                    
                    if isinstance(old_info, str):
                        old_filename = old_info
                        old_version = "Unknown"
                    elif isinstance(old_info, dict):
                        old_filename = old_info.get("file")
                        old_version = old_info.get("version", "Unknown")
                    else:
                        old_filename = None
                        old_version = "None"

                    table.update_cell(row_key, col_curr, old_version if old_filename else "Not Installed")

                    if old_filename and old_filename != filename:
                        table.update_cell(row_key, col_status, "[cyan]Update Available[/cyan]")
                        old_path = os.path.join(dst_mods, old_filename)
                        if os.path.exists(old_path):
                            log.write_line(f"Updating {slug_or_id}: Backing up {old_filename}...")
                            backup_path = os.path.join(dst_backups, f"{old_filename}.bak")
                            shutil.move(old_path, backup_path)
                        
                        log.write_line(f"  -> Downloading {filename}...")
                        table.update_cell(row_key, col_status, "[blue]Updating...[/blue]")
                        if self.download_mod(url, new_mod_path, log):
                            mod_meta[project_id] = {"file": filename, "version": latest_ver}
                            table.update_cell(row_key, col_status, "[green]Updated[/green]")
                            table.update_cell(row_key, col_curr, latest_ver)
                            updated_count += 1
                        else:
                            table.update_cell(row_key, col_status, "[red]Failed[/red]")
                
                    elif not os.path.exists(new_mod_path):
                        log.write_line(f"Installing {slug_or_id} -> {filename}...")
                        table.update_cell(row_key, col_status, "[blue]Installing...[/blue]")
                        if self.download_mod(url, new_mod_path, log):
                            mod_meta[project_id] = {"file": filename, "version": latest_ver}
                            table.update_cell(row_key, col_status, "[green]Installed[/green]")
                            table.update_cell(row_key, col_curr, latest_ver)
                            installed_count += 1
                        else:
                            table.update_cell(row_key, col_status, "[red]Failed[/red]")
                    else:
                        log.write_line(f"Mod {filename} is up to date.")
                        table.update_cell(row_key, col_status, "[green]Up to date[/green]")
                        mod_meta[project_id] = {"file": filename, "version": latest_ver}
                else:
                    log.write_line(f"  [yellow]No compatible version found for {slug_or_id}[/yellow]")
                    table.update_cell(row_key, col_status, "[yellow]No compat ver[/yellow]")

            with open(meta_path, 'w') as f:
                json.dump(mod_meta, f, indent=4)

            log.write_line(f"\nSummary: {installed_count} installed, {updated_count} updated.")

            log.write_line("\n[bold]Step 2: Syncing Configurations[/bold]")
            if os.path.exists(local_config):
                config_count = 0
                for root, dirs, files in os.walk(local_config):
                    rel_path = os.path.relpath(root, local_config)
                    dest_root = os.path.join(dst_config, rel_path)
                    os.makedirs(dest_root, exist_ok=True)
                    for f in files:
                        shutil.copy2(os.path.join(root, f), os.path.join(dest_root, f))
                        config_count += 1
                log.write_line(f"Updated {config_count} configuration files.")

            log.write_line("\n[bold green]Success: Sync Complete![/bold green]")
        except Exception as e:
            import traceback
            error_msg = f"FATAL ERROR: {str(e)}\n{traceback.format_exc()}"
            log.write_line(f"\n[bold red]FATAL ERROR: {str(e)}[/bold red]")
            log.write_line("See error.log for details.")
            with open("error.log", "w", encoding="utf-8") as f:
                f.write(error_msg)
            
        self.query_one("#btn-sync", Button).label = "Sync Again"

    def download_mod(self, url, path, log) -> bool:
        try:
            resp = requests.get(url, stream=True)
            if resp.status_code == 200:
                with open(path, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                log.write_line(f"  [green]Successfully saved to instance.[/green]")
                return True
            else:
                log.write_line(f"  [red]Download failed: {resp.status_code}[/red]")
                return False
        except Exception as e:
            log.write_line(f"  [red]Error: {e}[/red]")
            return False

class MCManagerApp(App):
    CSS = """
    #list-container {
        height: 10;
        border: solid green;
        margin: 1;
    }
    #details {
        background: $boost;
        padding: 1;
        margin-bottom: 1;
    }
    #mod-table {
        height: 1fr;
        border: double gray;
        margin: 1 0;
    }
    #sync-log {
        height: 8;
        border: solid gray;
        margin-bottom: 1;
    }
    #actions {
        height: 3;
        align: center middle;
    }
    Button {
        margin: 0 1;
    }
    #title {
        text-align: center;
        width: 100%;
        color: $accent;
    }
    """
    BINDINGS = [("q", "quit", "Quit")]

    def on_mount(self) -> None:
        appdata = os.environ.get("APPDATA")
        if not appdata:
            self.exit("APPDATA environment variable not found.")
            return

        base_path = os.path.join(appdata, "PrismLauncher", "instances")
        scanner = InstanceScanner(base_path)
        instances = scanner.scan()
        
        if not instances:
            self.exit(f"No Prism Launcher instances found in {base_path}")
            return

        self.push_screen(InstanceSelectScreen(instances))

if __name__ == "__main__":
    app = MCManagerApp()
    app.run()
