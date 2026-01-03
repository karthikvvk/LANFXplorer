# LANFXplorer

**High-speed, secure file transfer application for local networks using QUIC protocol**

LANFXplorer is a cross-platform application that enables fast and secure file transfers between devices on the same local network. Built with Flutter for the UI and Python for the backend, it leverages the QUIC protocol for efficient data transmission with built-in encryption and PKI-based authentication.

---

## Table of Contents

- [Features](#features)
- [User Guide](#user-guide)
  - [Installation](#installation)
  - [Getting Started](#getting-started)
  - [Using the Application](#using-the-application)
- [Developer Guide](#developer-guide)
  - [Prerequisites](#prerequisites)
  - [Project Structure](#project-structure)
  - [Development Setup](#development-setup)
  - [Building the Application for Release](#building-the-application-for-release)
  - [Architecture Overview](#architecture-overview)
- [Configuration](#configuration)


---

## Features

- **🚀 High-Speed Transfers**: Utilizes QUIC protocol for efficient, low-latency file transfers
- **🔒 Secure by Default**: PKI-based certificate authentication with TLS encryption
- **🌐 Network Discovery**: Automatically detects other LANFXplorer hosts on the local network
- **🔄 Bidirectional**: Both send and receive files on the same device
- **⚡ Multi-threaded**: Concurrent file transfers for maximum throughput
- **🖥️ Cross-Platform**: Supports Linux and Windows (macOS support planned)

---

# User Guide

### Installation & Run

#### Linux

1. **Download** the latest release or build from source
2. **Run the installer**:
   ```bash
   ./install.sh
   ```


3. **Launch the application**:
   ```bash
   ./app.sh
   ```


#### Windows

1. **Download** the latest release
2. **Run the installer**:
   ```cmd
   install.bat
   ```


3. **Launch the application**:
   ```cmd
   app.bat
   ```

---

### Getting Started

#### Create Your Profile

When you first launch LANFXplorer, you'll need to create a profile:

1. **Enter a Username**: Choose any name you'd like (e.g., your device name or personal identifier)

2. **Set a Strong Password**: 
   - Create a secure password for authentication
   - You'll need this password when other devices connect to you
   - Confirm the password by entering it twice

3. **Set Default Directory**: 
   - Choose where received files will be saved
   - Default location: `~/Downloads` (your user Downloads folder)
   - You can change this to any folder you prefer

4. **Click "Create Profile"** to initialize your device

#### Quick Setup with Defaults

For testing or quick setup, click **"Use Defaults"** which will:
- Username: Your system username
- Password: `password` (⚠️ **Warning**: Change this for production use!)
- Directory: `~/Downloads`

#### Using the Application

1. **Network Discovery**: 
   - LANFXplorer automatically scans your local network
   - Other LANFXplorer devices will appear in the host list
   - Select a device to connect

2. **Sending Files**:
   - Click the **Browse** or **Select Files** button
   - Choose files or folders to transfer
   - Select the destination device from available hosts
   - Click **Send** and monitor progress

3. **Receiving Files**:
   - Incoming transfers are accepted automatically
   - Files save to your configured default directory
   - View transfer status and history in the UI

---

# Developer Guide

### Prerequisites

#### Required Software

- **Python 3.9+** (Python 3.9 recommended for compatibility)
- **Flutter SDK 3.6.0+**
- **Git**
- **OpenSSL** (for certificate generation)

#### Platform-Specific Requirements

**Linux:**
- build-essential
- libssl-dev
- CMake 3.10+
- Ninja build system
- GTK 3.0+

**Windows:**
- Visual Studio 2022 (Build Tools or Community Edition)
- Windows SDK

### Development Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/karthikvvk/LANFXplorer.git
   cd LANFXplorer
   ```

2. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Install Flutter dependencies**:
   ```bash
   flutter pub get
   ```



5. **Build the Flutter UI**:
   ```bash
   flutter build linux --release   # Linux
   flutter build windows --release # Windows
   ```


Run components in same **order**:


```bash
python3 startsetup.py #generates certificates and config

python3 recive.py #Initialise Riciver server and Handshake Listener (QUIC Server)

python3 api_bridge.py #Initialise API server Password Sharing endpoints

./lanfxplorer #FOR 1st RUN
./build/linux/x64/release/bundle/lanfxplorer #FOR SUBSEQUENT RUNS AFTER BUILD
```

### Building the Application for Release


Use the automated builder:

```bash
python3 builder.py
```

This will:
1. Build the Flutter application
2. Bundle all dependencies
3. Package Python backend
4. Create distributable `appbuild/` directory
5. Archive for distribution


---

## Configuration & Debug

### Environment Variables

Configuration is managed through `.env` files and the system keyring:

- **QUIC_PORT**: Port for QUIC server (default: 4433)
- **API_PORT**: Port for Flask API (default: 5000)
- **INSTALLER**: Installation status flag
- **Passwords**: Stored securely in system keyring (Linux: Secret Service, Windows: Credential Manager)

### Certificate Management

Certificates are stored in:
- **CA Certificates**: `ca_cert.pem`, `ca_key.pem`
- **Server Certificates**: `cert.pem`, `key.pem`
- **Peer Exports**: `pkica_export/peers.json`

To regenerate certificates:

```bash
python3 scripts/make_ca_and_certs.py
```

### Configuration Files

- **`config_manager.py`**: Handles environment and keyring configuration
- **`path_security.py`**: Validates and secures file paths
- **`pubspec.yaml`**: Flutter dependencies and app metadata
- **`requirements.txt`**: Python dependencies



---

## Contributions :) Please do:

1. Fork the repository
2. Make your changes
3. Submit a pull request

---