#!/usr/bin/env python3

import os
import sys
import shutil
import subprocess
import tarfile
import zipfile
import platform
import datetime
import re

ROOT = os.getcwd()
APPBUILD = os.path.join(ROOT, "LANFXplorer")
SYSTEM = platform.system().lower()
date = datetime.datetime.now().strftime("%Y-%m-%d")

# Detect OS and build accordingly
try:
    os.system("flutter")
    if SYSTEM.startswith("win"):
        print("[*] Building for Windows...")
        os.system("flutter clean && flutter pub get && flutter build windows --release")
    else:
        print("[*] Building for Linux...")
        os.system("flutter clean && flutter pub get && flutter build linux --release")
except:
    print("flutter not found")

# Files and directories to include
ITEMS = [
    "analysis_options.yaml",
    "pki",
    "cli_profile.py",
    "logout.py",
    "api_bridge.py",
    "pubspec.lock",
    "app.sh",
    "app.bat",  # Windows launcher
    "pubspec.yaml",
    "receiver_api_functions.py",
    "config_manager.py",
    "receive.py",
    "devtools_options.yaml",
    "requirements.txt",
    "scanner.py",
    "host_selecter.py",
    "scripts",
    "installer.py",
    "sender_api_functions.py",
    "install.sh",
    "install.bat",  # Windows installer
    "send.py",
    "lanfxplorery.png",
    "startsetup.py",
    "main.py",
    "wifi_speed.py",
    "path_security.py",
    "app_config.py",
    "set_static_ip.py",
    "reset_env.py",
    "show_config.py",
    "32bitscreens",
    "firewall_manager.py",
    "install.py",

    
]

# Set Flutter bundle source and executable name based on OS
if SYSTEM.startswith("win"):
    FLUTTER_BUNDLE_SRC = "\\build\\windows\\x64\\runner\\Release"
    EXECUTABLE_NAME = "lanfxplorer.exe"
    PYTHON_UI_EXE_NAME = "python_ui.exe"
else:
    FLUTTER_BUNDLE_SRC = "/build/linux/x64/release/bundle"
    EXECUTABLE_NAME = "lanfxplorer"
    PYTHON_UI_EXE_NAME = "python_ui"

PYTHON_BUILD_DIR = os.path.join(ROOT, "python_build")


def build_python_ui():
    """
    Use PyInstaller to compile the Tkinter-based Python UI
    (32bitscreens/tkinter_app.py) into a standalone executable.
    Build artifacts go into ./python_build (temporary).
    Returns the path to the built executable, or None on failure.
    """
    entry_script = os.path.join(ROOT, "32bitscreens", "tkinter_app.py")
    if not os.path.exists(entry_script):
        print("[!] Python UI entry point not found, skipping PyInstaller build")
        return None

    base_dir = os.path.join(PYTHON_BUILD_DIR, "python_ui")
    dist_dir = os.path.join(base_dir, "dist")
    work_dir = os.path.join(base_dir, "work")
    spec_dir = base_dir

    # Collect all .py modules from 32bitscreens as hidden imports
    screens_dir = os.path.join(ROOT, "32bitscreens")
    hidden_imports = []
    for fname in os.listdir(screens_dir):
        if fname.endswith(".py") and fname != "__init__.py" and fname != "tkinter_app.py":
            mod_name = fname[:-3]  # strip .py
            hidden_imports.extend(["--hidden-import", mod_name])

    # Tkinter and its submodules (PyInstaller often misses these)
    tkinter_imports = [
        "tkinter",
        "tkinter.ttk",
        "tkinter.filedialog",
        "tkinter.messagebox",
        "tkinter.simpledialog",
        "_tkinter",
    ]
    for pkg in tkinter_imports:
        hidden_imports.extend(["--hidden-import", pkg])

    # Third-party packages used by 32bitscreens (e.g. api_client uses requests)
    third_party_imports = [
        "requests",
        "urllib3",
        "charset_normalizer",
        "certifi",
        "idna",
    ]
    for pkg in third_party_imports:
        hidden_imports.extend(["--hidden-import", pkg])

    # Find ALL site-packages directories where dependencies might live.
    # The builder may run from a venv (e.g. "virtual/") that only has PyInstaller,
    # while the actual app dependencies (requests, etc.) live in opt/python39.
    # We must tell PyInstaller where to find them.
    extra_paths = []
    seen_paths = set()

    def _add_path(p):
        if os.path.isdir(p) and p not in seen_paths:
            seen_paths.add(p)
            extra_paths.extend(["--paths", p])

    # 1. The project's bundled Python (opt/python39) — this is where
    #    requirements.txt packages are installed
    bundled_py_lib = os.path.join(ROOT, "opt", "python39", "lib")
    if os.path.isdir(bundled_py_lib):
        for dirpath, dirnames, filenames in os.walk(bundled_py_lib):
            if os.path.basename(dirpath) == "site-packages":
                _add_path(dirpath)
                print(f"    [paths] Found bundled site-packages: {dirpath}")

    # 2. The current Python's site-packages (fallback)
    try:
        import site
        for sp in site.getsitepackages():
            _add_path(sp)
        _add_path(site.getusersitepackages())
    except Exception:
        pass

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "python_ui",
        "--distpath", dist_dir,
        "--workpath", work_dir,
        "--specpath", spec_dir,
        "--paths", screens_dir,
        "--noconfirm",
    ] + extra_paths + hidden_imports + [entry_script]

    print(f"[*] Building Python UI with PyInstaller...")
    print(f"    Command: {' '.join(cmd)}")

    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print("[!] PyInstaller build failed! Do 'pip install pyinstaller' and try again")
        exit()
        return None

    exe_path = os.path.join(dist_dir, PYTHON_UI_EXE_NAME)
    if os.path.exists(exe_path):
        print(f"[*] Python UI built successfully: {exe_path}")
        return exe_path
    else:
        print(f"[!] Expected executable not found: {exe_path}")
        return None



def _is_in_except_block_py(lines, current_index):
    """
    Walk backwards to determine if the current line is inside a Python except block.
    Uses indentation to infer block membership.
    """
    current_line = lines[current_index]
    if not current_line.strip():
        return False

    current_indent = len(current_line) - len(current_line.lstrip())

    for i in range(current_index - 1, -1, -1):
        line = lines[i]
        if not line.strip():
            continue
        line_indent = len(line) - len(line.lstrip())
        # Found a line at a lower indent level — check if it opens an except/finally block
        if line_indent < current_indent:
            stripped = line.strip()
            if stripped.startswith(('except', 'finally')):
                return True
            # Hit a non-except block opener at lower indent — stop looking
            return False

    return False


def _get_catch_depth(lines, current_index, lang):
    """
    For JS/Dart: returns True if the current line is inside a catch/finally block.
    Scans backwards counting braces and looking for catch/finally keywords.
    """
    brace_depth = 0
    for i in range(current_index, -1, -1):
        line = lines[i]
        # Count braces in reverse (closing braces increase depth going backwards)
        brace_depth += line.count('}') - line.count('{')
        stripped = line.strip()
        # When we've closed back to a brace boundary, check if catch/finally opened it
        if brace_depth <= 0 and re.search(r'\b(catch|finally)\b', stripped):
            return True
        if brace_depth < 0:
            # We've exited the enclosing block entirely
            return False
    return False


def comment_out_logs(file_path):
    """
    Comment out console.log and print statements in a file.
    Skips statements inside except/catch/finally blocks.
    Handles JavaScript/TypeScript (.js, .ts, .jsx, .tsx), Python (.py), and Dart (.dart) files.
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext not in ['.js', '.ts', '.jsx', '.tsx', '.py', '.dart']:
        return False

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"[!] Could not read {file_path}: {e}")
        return False

    original_content = content
    modified = False

    lines = content.split('\n')
    new_lines = []

    for i, line in enumerate(lines):
        stripped = line.strip()

        if ext in ['.js', '.ts', '.jsx', '.tsx', '.dart']:
            comment_char = '//'
            already_commented = stripped.startswith('//')
            has_log = re.search(r'\bconsole\.log\s*\(', line) if ext != '.dart' else None
            has_print = re.search(r'\bprint\s*\(', line) if ext == '.dart' else None

            should_comment = (
                not already_commented
                and (has_log or has_print)
                and not _get_catch_depth(lines, i, lang='js')
            )

        elif ext == '.py':
            comment_char = '#'
            already_commented = stripped.startswith('#')
            has_print = re.search(r'\bprint\s*\(', line)

            should_comment = (
                not already_commented
                and has_print
                and not _is_in_except_block_py(lines, i)
            )

        else:
            should_comment = False

        if should_comment:
            new_lines.append(comment_char + line)
            modified = True
        else:
            new_lines.append(line)

    content = '\n'.join(new_lines)

    if modified and content != original_content:
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        except Exception as e:
            print(f"[!] Could not write {file_path}: {e}")
            return False

    return False



def build_app_exe():
    entry_script = os.path.join(ROOT, "app_launcher.py")

    base_dir = os.path.join(PYTHON_BUILD_DIR, "app")
    dist_dir = os.path.join(base_dir, "dist")
    work_dir = os.path.join(base_dir, "work")
    spec_dir = base_dir

    os.makedirs(base_dir, exist_ok=True)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--console",          # shows CMD window
        "--name", "app",
        "--distpath", dist_dir,
        "--workpath", work_dir,
        "--specpath", spec_dir,
        "--noconfirm",
        entry_script
    ]

    print("[*] Building app.exe...")
    result = subprocess.run(cmd, cwd=ROOT)

    exe_path = os.path.join(dist_dir, "app.exe")
    print(exe_path)

    return exe_path if os.path.exists(exe_path) else None





def build_install_exe():
    entry_script = os.path.join(ROOT, "install.py")

    base_dir = os.path.join(PYTHON_BUILD_DIR, "install")
    dist_dir = os.path.join(base_dir, "dist")
    work_dir = os.path.join(base_dir, "work")
    spec_dir = base_dir

    os.makedirs(base_dir, exist_ok=True)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--noconsole",          # ⭐ ensures CMD window
        "--name", "install",
        "--distpath", dist_dir,
        "--workpath", work_dir,
        "--specpath", spec_dir,
        entry_script
    ]

    print("[*] Building install.exe...")
    result = subprocess.run(cmd, cwd=ROOT)

    exe_path = os.path.join(dist_dir, "install.exe")
    return exe_path if os.path.exists(exe_path) else None



# DISABLED: Process directory function
def process_directory(directory):
    """
    Recursively process all files in a directory and comment out console.log and print statements.
    """
    files_modified = 0
    
    for root, dirs, files in os.walk(directory):
        # Skip node_modules, .git, and other common directories
        dirs[:] = [d for d in dirs if d not in ['node_modules', '.git', '.dart_tool', 'build', '.idea']]
        
        # for file in files:
        #     file_path = os.path.join(root, file)
        #     if comment_out_logs(file_path):
        #         files_modified += 1
        #         print(f"[*] Commented logs in: {os.path.relpath(file_path, directory)}")
    
    return files_modified


def get_version_from_pubspec():
    with open("pubspec.yaml", "r") as f:
        for line in f:
            if line.strip().startswith("version:"):
                return line.split(":", 1)[1].strip()
    raise RuntimeError("version not found in pubspec.yaml")


def main():
    # Fresh LANFXplorer
    if os.path.exists(APPBUILD):
        shutil.rmtree(APPBUILD)
    os.makedirs(APPBUILD)

    if os.path.exists(PYTHON_BUILD_DIR):
        shutil.rmtree(PYTHON_BUILD_DIR)

    os.makedirs(PYTHON_BUILD_DIR, exist_ok=True)


    # --- Build app.exe ---
    app_exe = build_app_exe()
    if app_exe:
        shutil.copy2(app_exe, os.path.join(APPBUILD, "app.exe"))
        print("[*] Included app.exe in archive")

    # --- Build install.exe ---
    install_exe = build_install_exe()
    if install_exe:
        shutil.copy2(install_exe, os.path.join(APPBUILD, "install.exe"))
        print("[*] Included install.exe in archive")

    # exit()

    # Copy listed items
    for item in ITEMS:
        src = os.path.join(ROOT, item)
        dst = os.path.join(APPBUILD, item)

        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)

    # Copy flutter bundle - maintain full directory structure
    if SYSTEM.startswith("win"):
        bundle_dest = os.path.join(APPBUILD, "build", "windows", "runner", "Release")
    else:
        bundle_dest = os.path.join(APPBUILD, "build", "linux", "x64", "release", "bundle")
    shutil.copytree(
        ROOT + FLUTTER_BUNDLE_SRC,
        bundle_dest,
        dirs_exist_ok=True,
    )

    # Copy built executable to root directory for easy trial runs
    executable_src = os.path.join(ROOT + FLUTTER_BUNDLE_SRC, EXECUTABLE_NAME)
    executable_dst = os.path.join(ROOT, EXECUTABLE_NAME)
    if os.path.exists(executable_src):
        shutil.copy2(executable_src, executable_dst)
        print(f"[*] Copied {EXECUTABLE_NAME} to root directory for easy testing")
    else:
        print(f"[!] Warning: Executable not found at {executable_src}")

    # --- Build and include Python UI (PyInstaller) ---
    python_ui_exe = build_python_ui()
    if python_ui_exe:
        python_ui_dest = os.path.join(APPBUILD, "python_ui")
        os.makedirs(python_ui_dest, exist_ok=True)
        shutil.copy2(python_ui_exe, os.path.join(python_ui_dest, PYTHON_UI_EXE_NAME))
        print(f"[*] Included Python UI executable in archive")
    else:
        print("[!] Warning: Python UI executable not included in archive")

    # Cleanup temporary python_build directory
    if os.path.exists(PYTHON_BUILD_DIR):
        shutil.rmtree(PYTHON_BUILD_DIR)
        print(f"[*] Cleaned up temporary python_build directory")

    # DISABLED: Comment out console.log and print statements
    print("\n[*] Commenting out console.log and print statements...")
    files_modified = process_directory(APPBUILD)
    print(f"[*] Modified {files_modified} files")

    # Read version
    version = get_version_from_pubspec()
    
    # Create archive based on OS
    if SYSTEM.startswith("win"):
        # Create zip for Windows
        archive_name = f"{SYSTEM}_{date}_{version}.zip"
        with zipfile.ZipFile(archive_name, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(APPBUILD):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.join("LANFXplorer", os.path.relpath(file_path, APPBUILD))
                    zipf.write(file_path, arcname)
        print(f"[*] Created archive: {archive_name}")
    else:
        # Create tar.gz for Linux
        archive_name = f"{SYSTEM}_{date}_{version}.tar.gz"
        with tarfile.open(archive_name, "w:gz") as tar:
            tar.add(APPBUILD, arcname="LANFXplorer")
        print(f"[*] Created archive: {archive_name}")

    # Cleanup: Delete the temporary LANFXplorer directory used for building
    if os.path.exists(APPBUILD):
        shutil.rmtree(APPBUILD)
        print(f"[*] Cleaned up temporary build directory: {APPBUILD}")

    # Output release instructions for the user
    print("\n" + "=" * 60)
    print("BUILD COMPLETE! Ready to release.")
    print("=" * 60)
    print("\nTo publish this release, run the following commands:\n")
    print(f"# 1. Create and push a version tag")
    print(f'git tag -a v{version} -m "LANFXplorer v{version}"')
    print(f"git push origin v{version}")
    print(f"\n# 2. Create the GitHub release")
    print(f'gh release create v{version} \\')
    print(f'  --title "LANFXplorer v{version}" \\')
    print(f'  --notes "Release v{version}"')
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()