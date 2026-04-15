import platform
import subprocess
import json
import time
import sys
import os
import zipfile
import hashlib

def get_id():
    # Time: O(1), Space: O(1)
    os_name = platform.system()
    if os_name == "Windows":
        c = 'powershell.exe "(Get-ItemProperty -Path \'HKLM:\\SOFTWARE\\Microsoft\\Cryptography\').MachineGuid"'
        return subprocess.check_output(c, shell=True).decode().strip()
    elif os_name == "Linux":
        with open("/etc/machine-id", "r") as f:
            return f.read().strip()
    elif os_name == "Darwin":
        c = "ioreg -rd1 -c IOPlatformExpertDevice | awk '/IOPlatformUUID/ { split($0, line, \"\\\"\"); printf(\"%s\\n\", line[4]); }'"
        return subprocess.check_output(c, shell=True).decode().strip()
    return ""

def get_ip():
    # Time: O(1), Space: O(1)
    try:
        return subprocess.check_output(["tailscale", "ip", "-4"]).decode().strip()
    except:
        return ""

def sync(s, d):
    # Time: O(N) where N is num files, Space: O(1)
    r = subprocess.run(["rclone", "sync", s, d])
    if r.returncode != 0:
        print("Sync incomplete/failed. Run script again to resume.")
        sys.exit(1)

def pull():
    # Time: O(N), Space: O(1)
    sync("b2_mc:mc_bucket/world", "./world")

def push():
    # Time: O(N), Space: O(1)
    sync("./world", "b2_mc:mc_bucket/world")

def get_server_version(jar_path="server.jar"):
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
    # Time: O(1) network call, Space: O(1)
    try:
        subprocess.run(["rclone", "copy", "b2_mc:mc_bucket/state.json", "./"], check=True, capture_output=True)
        with open("state.json", "r") as f:
            return json.load(f)
    except:
        return None

def set_lock(uid, ip, version=None):
    # Time: O(1) network call, Space: O(1)
    st = chk_lock() or {}
    st["id"] = uid
    st["ip"] = ip
    st["ts"] = int(time.time())
    if version:
        st["server_version"] = version
        
    with open("state.json", "w") as f:
        json.dump(st, f)
    subprocess.run(["rclone", "copy", "state.json", "b2_mc:mc_bucket/"], check=True)

def rm_lock():
    # Instead of deleting state.json (which clears the version memory), we just nullify the id and ip.
    st = chk_lock()
    if st:
        st["id"] = None
        st["ip"] = None
        with open("state.json", "w") as f:
            json.dump(st, f)
        subprocess.run(["rclone", "copy", "state.json", "b2_mc:mc_bucket/"], check=True)

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
    # Time: O(M) where M is server uptime, Space: O(1)
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
    c = ["java", "-Xmx4G", "-Xms4G", "-jar", "server.jar", "nogui"]
    s = subprocess.run(c)
    
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
