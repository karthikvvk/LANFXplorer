#!/usr/bin/env python3

import os
import shutil
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
    "files.iml",
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
    "app_config.py"
    ""
]

# Set Flutter bundle source and executable name based on OS
if SYSTEM.startswith("win"):
    FLUTTER_BUNDLE_SRC = "\\build\\windows\\runner\\Release"
    EXECUTABLE_NAME = "lanfxplorer.exe"
else:
    FLUTTER_BUNDLE_SRC = "/build/linux/x64/release/bundle"
    EXECUTABLE_NAME = "lanfxplorer"


def comment_out_logs(file_path):
    """
    Comment out console.log and print statements in a file.
    Handles JavaScript/TypeScript (.js, .ts, .jsx, .tsx), Python (.py), and Dart (.dart) files.
    """
    # Determine file extension
    ext = os.path.splitext(file_path)[1].lower()
    
    # Skip non-code files
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
    
    if ext in ['.js', '.ts', '.jsx', '.tsx', '.dart']:
        # Comment out console.log (but NOT console.error, console.warn, etc.)
        # Match console.log with various whitespace patterns
        lines = content.split('\n')
        new_lines = []
        
        for line in lines:
            # Check if line contains console.log (not already commented)
            if 'console.log' in line and not line.strip().startswith('//'):
                # Make sure it's actually console.log and not console.error, etc.
                if re.search(r'\bconsole\.log\s*\(', line):
                    # Comment it out
                    new_lines.append('//' + line)
                    modified = True
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        
        content = '\n'.join(new_lines)
    
    if ext == '.py' or ext == '.dart':
        # Comment out print statements (not already commented)
        lines = content.split('\n')
        new_lines = []
        
        for line in lines:
            # Check if line contains print( and is not already commented
            if ext == '.py':
                comment_char = '#'
            else:
                comment_char = '//'
            
            if not line.strip().startswith(comment_char):
                # Match print( with word boundary to avoid matching substring in function names
                if re.search(r'\bprint\s*\(', line):
                    # Comment it out
                    new_lines.append(comment_char + line)
                    modified = True
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        
        content = '\n'.join(new_lines)
    
    # Write back if modified
    if modified and content != original_content:
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        except Exception as e:
            print(f"[!] Could not write {file_path}: {e}")
            return False
    
    return False


def process_directory(directory):
    """
    Recursively process all files in a directory and comment out console.log and print statements.
    """
    files_modified = 0
    
    for root, dirs, files in os.walk(directory):
        # Skip node_modules, .git, and other common directories
        dirs[:] = [d for d in dirs if d not in ['node_modules', '.git', '.dart_tool', 'build', '.idea']]
        
        for file in files:
            file_path = os.path.join(root, file)
            if comment_out_logs(file_path):
                files_modified += 1
                print(f"[*] Commented logs in: {os.path.relpath(file_path, directory)}")
    
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

    # Copy listed items
    for item in ITEMS:
        src = os.path.join(ROOT, item)
        dst = os.path.join(APPBUILD, item)

        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)

    # Copy flutter bundle - maintain full directory structure
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

    # Comment out console.log and print statements in the build directory
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
    print(f"\n# 2. Create the GitHub release with the archive")
    print(f'gh release create v{version} {archive_name} \\')
    print(f'  --title "LANFXplorer v{version}" \\')
    print(f'  --notes "Release v{version}"')
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()