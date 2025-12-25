#!/usr/bin/env python3
"""
LANFXplorer Main Entry Point

Orchestrates the complete application startup in order:
1. installer.py - Check/install dependencies, firewall, directories
2. startsetup.py - PKI and environment setup
3. recive.py - QUIC receiver (background)
4. api_bridge.py - Flask API (background)  
5. flutter run - Flutter UI
"""
from startsetup import write_env
import os
import sys
import subprocess
import time
from pathlib import Path

# Ensure we're in the application directory
APP_DIR = Path(__file__).parent.resolve()
os.chdir(APP_DIR)

# Add app dir to path for imports
sys.path.insert(0, str(APP_DIR))


def print_header(text: str):
    """Print a formatted header."""
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")


def print_status(status: str, message: str):
    """Print a status message."""
    symbols = {"ok": "✓", "fail": "✗", "info": "ℹ", "warn": "⚠", "run": "→"}
    symbol = symbols.get(status, "•")
    print(f"[{symbol}] {message}")


def run_script(script_name: str, wait: bool = True) -> subprocess.Popen:
    """Run a Python script."""
    script_path = APP_DIR / script_name
    if not script_path.exists():
        print_status("fail", f"Script not found: {script_path}")
        return None
    
    print_status("run", f"Starting {script_name}...")
    
    try:
        proc = subprocess.Popen(
            [sys.executable, str(script_path)],
            cwd=str(APP_DIR),
            stdout=None if not wait else subprocess.PIPE,
            stderr=None if not wait else subprocess.PIPE,
        )
        
        if wait:
            proc.wait()
            if proc.returncode == 0:
                print_status("ok", f"{script_name} completed")
            else:
                print_status("fail", f"{script_name} failed with code {proc.returncode}")
        else:
            time.sleep(1)
            if proc.poll() is None:
                print_status("ok", f"{script_name} started (PID: {proc.pid})")
            else:
                print_status("fail", f"{script_name} failed to start")
                return None
        
        return proc
    except Exception as e:
        print_status("fail", f"{script_name} error: {str(e)}")
        return None


def run_installer_sync() -> bool:
    """
    Run the installer as a subprocess.
    This ensures any elevated privileges (sudo) gained during firewall
    configuration die with the subprocess and don't affect main.py.
    Returns True if installation succeeded.
    """
    print_status("run", "Running installer as subprocess...")
    
    try:
        result = subprocess.run(
            [sys.executable, str(APP_DIR / "installer.py")],
            cwd=str(APP_DIR),
            timeout=600,  # 10 minute timeout
        )
        
        if result.returncode == 0:
            print_status("ok", "Installation completed")
            return True
        else:
            print_status("warn", f"Installer returned code {result.returncode}")
            return False
    except subprocess.TimeoutExpired:
        print_status("fail", "Installer timed out")
        return False
    except Exception as e:
        print_status("fail", f"Installer error: {str(e)}")
        return False


def main():
    print_header("LANFXplorer Startup")
    print(f"   App Directory: {APP_DIR}")
    
    processes = []
    
    try:
        # =================================================================
        # Step 1: Run installer in sync thread (handles firewall with sudo)
        # =================================================================
        print_header("Step 1: Installation & Setup")
        if os.getenv("installer"):
            o = run_installer_sync()
            if not o:
                print_status("warn", "Installation had some issues, continuing anyway...")
            write_env(installer=False)
        else:
            print_status("warn", "Installation not enabled, continuing...")
        
        # =================================================================
        # Step 2: Run startsetup.py (PKI and environment)
        # =================================================================
        print_header("Step 2: PKI & Environment Setup")
        run_script("startsetup.py", wait=True)
        
        # =================================================================
        # Step 3: Start recive.py (QUIC receiver - background)
        # =================================================================
        print_header("Step 3: Starting Services")
        receiver = run_script("recive.py", wait=False)
        if receiver:
            processes.append(("Receiver", receiver))
        else:
            print_status("fail", "Cannot continue without receiver!")
            return
        
        # Wait for receiver to initialize
        time.sleep(2)
        
        # =================================================================
        # Step 4: Start api_bridge.py (Flask API - background)
        # =================================================================
        api = run_script("api_bridge.py", wait=False)
        if api:
            processes.append(("API Bridge", api))
        else:
            print_status("warn", "API Bridge failed, continuing anyway...")
        
        # Wait for API to be ready
        time.sleep(2)
        
        # =================================================================
        # Step 5: Start Flutter UI
        # =================================================================
        print_header("Step 4: Starting Flutter UI")
        print_status("run", "Launching Flutter application...")
        
        flutter_proc = subprocess.Popen(
            ["flutter", "run", "--release"],
            cwd=str(APP_DIR),
        )
        processes.append(("Flutter", flutter_proc))
        
        print_header("LANFXplorer Running")
        print_status("info", "Active services:")
        for name, proc in processes:
            print(f"        • {name} (PID: {proc.pid})")
        print("\n   Press Ctrl+C to stop all services\n")
        
        # Wait for Flutter to exit
        flutter_proc.wait()
        
    except KeyboardInterrupt:
        print("\n")
        print_status("info", "Shutdown requested...")
    except Exception as e:
        print_status("fail", f"Error: {str(e)}")
    finally:
        # Stop all background processes
        print_status("info", "Stopping services...")
        for name, proc in processes:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                    print_status("ok", f"{name} stopped")
                except subprocess.TimeoutExpired:
                    proc.kill()
                    print_status("warn", f"{name} killed")


if __name__ == "__main__":
    main()
