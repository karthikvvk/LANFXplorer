import subprocess
import os
import sys

# Folder where EXE is located
base_dir = os.path.dirname(sys.executable)

bat_file = os.path.join(base_dir, "app.bat")

subprocess.Popen(
    bat_file,
    shell=True,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    stdin=subprocess.DEVNULL,
    creationflags=subprocess.CREATE_NO_WINDOW
)