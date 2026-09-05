import os
import sys
import subprocess
import webbrowser
import time

def check_dependencies():
    print("==========================================================")
    print("      AGENTIC OS KERNEL GUARDIAN - SYSTEM LAUNCHER       ")
    print("==========================================================")
    print("[1/3] Checking environment and dependencies...")
    
    # Try importing psutil
    try:
        import psutil
        print(" -> System metrics module (psutil) verified.")
    except ImportError:
        print(" -> Installing psutil...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "psutil"], check=False)
        except Exception:
            pass

def start_server():
    print("[2/3] Starting Kernel Guardian Daemon & Web Server on http://127.0.0.1:5000...")
    
    # Auto open browser after 1.5s
    def _open_browser():
        time.sleep(1.5)
        webbrowser.open("http://127.0.0.1:5000")

    import threading
    threading.Thread(target=_open_browser, daemon=True).start()

    from backend.main import start_app
    start_app(host="127.0.0.1", port=5000)

if __name__ == "__main__":
    check_dependencies()
    start_server()
