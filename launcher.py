import platform
import subprocess
import json
import time
import sys
import os
import zipfile
import hashlib

# ── ANSI color helpers ──────────────────────────────────────────────
# Enable ANSI escape codes on Windows 10+
if os.name == "nt":
    os.system("")

class C:
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    CYAN    = "\033[96m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RESET   = "\033[0m"

def info(msg):
    print(f"{C.CYAN}ℹ {msg}{C.RESET}")

def success(msg):
    print(f"{C.GREEN}✔ {msg}{C.RESET}")

def warn(msg):
    print(f"{C.YELLOW}⚠ {msg}{C.RESET}")

def error(msg):
    print(f"{C.RED}✖ {msg}{C.RESET}")

def bold(msg):
    print(f"{C.BOLD}{msg}{C.RESET}")

def highlight(msg):
    print(f"{C.BOLD}{C.GREEN}{msg}{C.RESET}")

# ── .env loader ─────────────────────────────────────────────────────
def load_env(path=".env"):
    env = {}
    if os.path.exists(path):
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    return env

ENV = load_env()
BUCKET = ENV.get("BUCKET_NAME", "")
if not BUCKET:
    error("BUCKET_NAME not set in .env")
    sys.exit(1)

# ── Java finder ─────────────────────────────────────────────────────
def find_java():
    """Find the newest Java installation, bypassing PATH order issues."""
    search_dirs = [
        os.path.join(os.environ.get("ProgramFiles", ""), "Microsoft"),
        os.path.join(os.environ.get("ProgramFiles", ""), "Eclipse Adoptium"),
        os.path.join(os.environ.get("ProgramFiles", ""), "Java"),
    ]
    candidates = []
    for base in search_dirs:
        if not os.path.isdir(base):
            continue
        for entry in os.listdir(base):
            java_exe = os.path.join(base, entry, "bin", "java.exe")
            if os.path.isfile(java_exe):
                # Extract version number from folder name (e.g. "jdk-25.0.2.10-hotspot")
                nums = [int(x) for x in entry.replace("-", ".").split(".") if x.isdigit()]
                candidates.append((tuple(nums), java_exe))
    if candidates:
        candidates.sort(reverse=True)
        return candidates[0][1]
    # Fallback to PATH
    return "java"

# ── Identity ────────────────────────────────────────────────────────
def get_id():
    os_name = platform.system()
    if os_name == "Windows":
        c = 'powershell.exe "(Get-ItemProperty -Path \'HKLM:\\SOFTWARE\\Microsoft\\Cryptography\').MachineGuid"'
        return subprocess.check_output(c, shell=True).decode().strip()
    elif os_name == "Linux":
        with open("/etc/machine-id", "r") as f:
            return f.read().strip()
    return ""

def get_ip():
    # Try 'tailscale' from PATH first, then fall back to default Windows install path
    tailscale_paths = [
        "tailscale",
        os.path.join(os.environ.get("ProgramFiles", ""), "Tailscale", "tailscale.exe"),
    ]
    for ts_path in tailscale_paths:
        try:
            ip = subprocess.check_output([ts_path, "ip", "-4"], stderr=subprocess.DEVNULL).decode().strip()
            if ip:
                return ip
        except FileNotFoundError:
            continue
        except subprocess.CalledProcessError:
            warn("Tailscale is not running or not logged in.")
            print(f"  {C.DIM}Open Tailscale and sign in to your tailnet.{C.RESET}")
            return ""
        except Exception:
            continue
    warn("Tailscale is not installed. Players outside your LAN won't be able to connect.")
    print(f"  {C.DIM}Run setup.bat to install it.{C.RESET}")
    return ""

# ── Cloud sync ──────────────────────────────────────────────────────
def sync(s, d):
    r = subprocess.run(["rclone", "sync", s, d, "--progress", "--b2-hard-delete"])
    if r.returncode != 0:
        error("Sync incomplete/failed. Run script again to resume.")
        sys.exit(1)

def pull():
    sync(f"b2_mc:{BUCKET}/minecraft-world", "./minecraft-world")

def push():
    sync("./minecraft-world", f"b2_mc:{BUCKET}/minecraft-world")

# ── Version checking ────────────────────────────────────────────────
def get_server_version(jar_path="minecraft-world/server.jar"):
    if not os.path.exists(jar_path):
        return "0.0.0"
    
    try:
        with zipfile.ZipFile(jar_path, 'r') as z:
            if 'version.json' in z.namelist():
                with z.open('version.json') as f:
                    data = json.load(f)
                    return data.get('id', "0.0.0")
    except Exception:
        pass
        
    # Fallback to hash
    h = hashlib.sha256()
    try:
        with open(jar_path, 'rb') as f:
            while chunk := f.read(8192):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return "0.0.0"

def parse_version(ver_str):
    parts = str(ver_str).split('.')
    if all(p.isdigit() for p in parts) and len(parts) > 0:
        return tuple(int(p) for p in parts)
    return str(ver_str)

# ── Lock management ─────────────────────────────────────────────────
def chk_lock():
    try:
        subprocess.run(["rclone", "copy", f"b2_mc:{BUCKET}/state.json", "./"], check=True, capture_output=True)
        with open("state.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        # rclone is missing from the system
        error("rclone not found. Please install it and add to PATH.")
        sys.exit(1)
    except Exception:
        # state.json missing or bucket error
        return None

def set_lock(uid, ip, version=None):
    st = chk_lock() or {}
    st["id"] = uid
    st["ip"] = ip
    st["ts"] = int(time.time())
    if version:
        st["server_version"] = version
        
    with open("state.json", "w") as f:
        json.dump(st, f)
    subprocess.run(["rclone", "copy", "state.json", f"b2_mc:{BUCKET}/"], check=True)

def rm_lock():
    # Instead of deleting state.json (which clears the version memory), we just nullify the id and ip.
    st = chk_lock()
    if st:
        st["id"] = None
        st["ip"] = None
        with open("state.json", "w") as f:
            json.dump(st, f)
        subprocess.run(["rclone", "copy", "state.json", f"b2_mc:{BUCKET}/"], check=True)

def check_version_safety(st):
    local_ver = get_server_version()
    last_version = st.get("server_version") if st else None
    
    if last_version and last_version != "0.0.0" and local_ver != "0.0.0":
        cur_parsed = parse_version(local_ver)
        last_parsed = parse_version(last_version)
        
        # If both are semantic versions
        if isinstance(cur_parsed, tuple) and isinstance(last_parsed, tuple):
            if cur_parsed < last_parsed:
                error(f"Server downgrade detected! Local {local_ver} < Last {last_version}.")
                error("Downgrading risks severe world corruption. Please upgrade your server.jar.")
                sys.exit(1)
        # If hash fallback, require strict equality
        else:
            if cur_parsed != last_parsed:
                error("Server JAR mismatch detected! Local does not match last active version.")
                error("Using mismatched servers can corrupt chunks. Update your server.jar.")
                sys.exit(1)
    return local_ver

# ── Main ────────────────────────────────────────────────────────────
def main():
    uid = get_id()
    ip = get_ip()
    st = chk_lock()
    
    is_locked = st and st.get("id") is not None
    
    if is_locked:
        if st.get("id") == uid:
            info("Smart lock bypass. Resuming...")
            # We still need to check version safety before resuming
            local_ver = check_version_safety(st)
        else:
            error(f"Server is locked by another host — IP: {C.BOLD}{st.get('ip')}{C.RESET}{C.RED}")
            sys.exit(0)
    else:
        # Check version safety before we pull, saving time
        local_ver = check_version_safety(st)
        
        info("Acquiring lock...")
        set_lock(uid, ip, version=local_ver)
        info("Pulling data...")
        pull() # Halts natively if pull is interrupted
        
    bold("Starting Server...")
    if ip:
        highlight(f"  ▸ Connect via Tailscale IP: {ip}")
    else:
        warn("No Tailscale IP detected. Players can only join via your local network.")
    java_path = find_java()
    print(f"  {C.DIM}Using Java: {java_path}{C.RESET}")
    os.makedirs("minecraft-world", exist_ok=True)
    c = [java_path, "-Xmx4G", "-Xms4G", "-jar", "server.jar", "nogui"]
    s = subprocess.run(c, cwd="minecraft-world")
    
    if s.returncode == 0:
        info("Server stopped. Pushing data...")
        push() # Halts natively if push is interrupted
        info("Removing lock...")
        rm_lock()
        success("Done. World saved and lock released.")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--force-unlock":
        rm_lock()
        success("Unlocked.")
    else:
        main()
