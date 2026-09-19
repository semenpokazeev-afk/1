"""
Runner to launch both ARBITER Gateway and Cloudflare Tunnel concurrently
and save the generated public URL into public_url.txt
"""

import os
import re
import sys
import time
import subprocess
import threading

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

def stream_logs(process, prefix, url_file):
    url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
    try:
        for line in iter(process.stderr.readline, ''):
            if not line:
                break
            line_str = line.strip()
            print(f"[{prefix}] {line_str}")
            match = url_pattern.search(line_str)
            if match:
                url = match.group(0)
                print("\n" + "=" * 60)
                print(f"ARBITER PUBLIC LIVE URL: {url}")
                print("=" * 60 + "\n")
                with open(url_file, "w", encoding="utf-8") as f:
                    f.write(url + "\n")
    except Exception as e:
        print(f"[{prefix} reader error]: {e}")

def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    python_exe = sys.executable
    cloudflared_exe = r"C:\Program Files (x86)\cloudflared\cloudflared.exe"
    url_file = os.path.join(root_dir, "public_url.txt")

    if not os.path.exists(cloudflared_exe):
        print(f"Error: cloudflared not found at {cloudflared_exe}")
        return

    print("Starting ARBITER uvicorn server on http://0.0.0.0:8000 ...")
    server_proc = subprocess.Popen(
        [python_exe, "-m", "uvicorn", "arbiter.gateway.app:app", "--host", "0.0.0.0", "--port", "8000"],
        cwd=root_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace"
    )

    time.sleep(3)

    print("Starting Cloudflare Tunnel ...")
    tunnel_proc = subprocess.Popen(
        [cloudflared_exe, "tunnel", "--url", "http://127.0.0.1:8000"],
        cwd=root_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace"
    )

    t = threading.Thread(target=stream_logs, args=(tunnel_proc, "Cloudflare", url_file), daemon=True)
    t.start()

    try:
        while True:
            time.sleep(1)
            if server_proc.poll() is not None:
                print("Server process exited.")
                break
            if tunnel_proc.poll() is not None:
                print("Tunnel process exited.")
                break
    except KeyboardInterrupt:
        print("Stopping services...")
    finally:
        try:
            tunnel_proc.terminate()
        except Exception:
            pass
        try:
            server_proc.terminate()
        except Exception:
            pass

if __name__ == "__main__":
    main()
