import platform
import subprocess
import json
import time
import sys
import os
import zipfile
import hashlib

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
    print("ERROR: BUCKET_NAME not set in .env")
    sys.exit(1)

import glob

def find_java():
    """Find the newest Java installation, bypassing PATH order issues."""
    # Check known install directories for Microsoft/Adoptium/Oracle JDKs
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
            print("WARNING: Tailscale is not running or not logged in.")
            print("  Open Tailscale and sign in to your tailnet.")
            return ""
        except Exception:
            continue
    print("WARNING: Tailscale is not installed. Players outside your LAN won't be able to connect.")
    print("  Run setup.bat to install it.")
    return ""

def sync(s, d):
    r = subprocess.run(["rclone", "sync", s, d])
    if r.returncode != 0:
        print("Sync incomplete/failed. Run script again to resume.")
        sys.exit(1)

def pull():
    sync(f"b2_mc:{BUCKET}/minecraft-world", "./minecraft-world")

def push():
    sync("./minecraft-world", f"b2_mc:{BUCKET}/minecraft-world")

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

def chk_lock():
    try:
        subprocess.run(["rclone", "copy", f"b2_mc:{BUCKET}/state.json", "./"], check=True, capture_output=True)
        with open("state.json", "r") as f:
            return json.load(f)
    except:
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
                print(f"ERROR: Server downgrade detected! Local {local_ver} < Last {last_version}.")
                print("Downgrading risks severe world corruption. Please upgrade your server.jar.")
                sys.exit(1)
        # If hash fallback, require strict equality
        else:
            if cur_parsed != last_parsed:
                print(f"ERROR: Server JAR mismatch detected! Local does not match last active version.")
                print("Using mismatched servers can corrupt chunks. Update your server.jar.")
                sys.exit(1)
    return local_ver

def main():
    uid = get_id()
    ip = get_ip()
    st = chk_lock()
    
    is_locked = st and st.get("id") is not None
    
    if is_locked:
        if st.get("id") == uid:
            print("Smart lock bypass. Resuming...")
            # We still need to check version safety before resuming
            local_ver = check_version_safety(st)
        else:
            print(f"Locked by IP: {st.get('ip')}")
            sys.exit(0)
    else:
        # Check version safety before we pull, saving time
        local_ver = check_version_safety(st)
        
        print("Acquiring lock...")
        set_lock(uid, ip, version=local_ver)
        print("Pulling data...")
        pull() # Halts natively if pull is interrupted
        
    print("Starting Server...")
    if ip:
        print(f"Your Tailscale IP: {ip} — share this with your friends to connect!")
    else:
        print("No Tailscale IP detected. Players can only join via your local network.")
    java_path = find_java()
    print(f"Using Java: {java_path}")
    os.makedirs("minecraft-world", exist_ok=True)
    c = [java_path, "-Xmx4G", "-Xms4G", "-jar", "server.jar", "nogui"]
    s = subprocess.run(c, cwd="minecraft-world")
    
    if s.returncode == 0:
        print("Server stopped. Pushing data...")
        push() # Halts natively if push is interrupted
        print("Removing lock...")
        rm_lock()
        print("Done.")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--force-unlock":
        rm_lock()
        print("Unlocked.")
    else:
        main()
