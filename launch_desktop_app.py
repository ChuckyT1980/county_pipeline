"""
Standalone Desktop Window Launcher for California Parcel Map
Launches the map application directly in a dedicated native desktop window.
"""
import os
import sys
import time
import urllib.request
import subprocess

PYTHON_EXE = r"C:\Users\chuck\AppData\Local\Programs\Python\Python311\python.exe"
BASE_DIR = r"C:\Users\chuck\Downloads\county_pipeline"
SERVER_SCRIPT = os.path.join(BASE_DIR, "server", "app.py")

def start_server():
    """Start local Flask server silently in background."""
    print("Starting background map server...")
    subprocess.Popen([PYTHON_EXE, SERVER_SCRIPT], cwd=BASE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def wait_for_server(url="http://127.0.0.1:8080/"):
    """Wait until local server is up and responding."""
    for _ in range(30):
        try:
            res = urllib.request.urlopen(url)
            if res.getcode() == 200:
                print("Server is ready!")
                return True
        except Exception:
            time.sleep(0.3)
    return False

def launch_window():
    """Launch native desktop window using pywebview or Microsoft Edge App mode."""
    url = "http://127.0.0.1:8080/"
    try:
        import webview
        print("Launching native desktop window via pywebview...")
        window = webview.create_window(
            title='California Interactive Parcel Map — Desktop Edition',
            url=url,
            width=1400,
            height=900,
            resizable=True,
            min_size=(1000, 700)
        )
        webview.start()
    except Exception as e:
        print("Launching desktop app window via Edge App mode...", e)
        cmd = f'start msedge --app="{url}"'
        os.system(cmd)

if __name__ == "__main__":
    # Ensure server is running
    try:
        urllib.request.urlopen("http://127.0.0.1:8080/")
    except Exception:
        start_server()

    wait_for_server()
    launch_window()
