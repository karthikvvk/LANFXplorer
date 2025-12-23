import getpass
import os
import subprocess
import platform
import re
import threading
import asyncio
from ipaddress import IPv4Network, IPv4Address
import concurrent.futures
from typing import List
from dotenv import load_dotenv
import requests
import socket
import time


host_ip = ""
cidr = ""
gateway = ""
subnet = ""
broadcast = ""
interface = ""
system_name = ""
user = ""
pwd = ""
dest_host = ""
file_path = ""




def check_subnet(ip, host_ip):

    if not host_ip:
        raise ValueError("HOST environment variable not set")

    ip_parts = ip.strip().split('.')
    default_parts = host_ip.strip().split('.')
    ed = ip_parts[-1]
    
    if ed == '1' or ed == "200" or ed == "255":
        return False
    
    return ip_parts[:-1] == default_parts[:-1]

def get_OS_TYPE(REMOTE_HOST=""):
    try:
        response = requests.post(f"http://{REMOTE_HOST}:5000/osinfo", 
                                json={"request": "osinfo"})
        if response.status_code == 200:
            data = response.json()
            return {"os": data.get("os", "linux"), "user": data.get("user")}
        else:
            return {"os": "linux", "user": None}
    except:
        return {"os": "linux", "user": None}

def update_env():
    global gateway, cidr, file_path, host_ip, broadcast, system_name, interface, user, pwd, dest_host
    
    load_dotenv()
    
    host_ip = os.getenv("HOST", "")
    cidr = os.getenv("CIDR", "24")
    gateway = os.getenv("GATEWAY", "")
    subnet = os.getenv("SUBNET", "255.255.255.0")
    broadcast = os.getenv("BROADCAST", "")
    interface = os.getenv("INTERFACE", "")
    system_name = os.getenv("SYSTEM", platform.system().lower())
    user = os.getenv("USER", getpass.getuser())
    pwd = os.getenv("PWD", os.getcwd())
    dest_host = os.getenv("DEST_HOST", "")
    
    print(f"[+] Loaded scanner's environment variables")
    print(f"    Network: {gateway}/{cidr}")
    print(f"    Interface: {interface}")
    print(f"    System: {system_name}")

def checkfile():
    global gateway, cidr, file_path, host_ip, broadcast, system_name, interface, user, pwd, dest_host
    if not os.path.exists(file_path):
        open(file_path, "w").close()
        print(f"[+] Created {file_path}")

def gethostlist():
    global gateway, cidr, file_path, host_ip, broadcast, system_name, interface, user, pwd, dest_host
    
    update_env()
    host_list = scan_peers_udp()
    result = []
    for ip in host_list:
        subck = check_subnet(ip, host_ip)
        if subck:
            res = get_OS_TYPE(ip)
            username = res.get("user")
            if username:
                result.append({"host": ip, "user": username, "os": res.get("os", "linux")})
    return result
    
def scan_peers_udp(network=None):
   
    global gateway, cidr, file_path, host_ip, broadcast, system_name, interface, user, pwd, dest_host
    DISCOVERY_PORT = 4436
    PEER_DISCOVERY_MSG = b"WHO_IS_PEER"
    PEER_RESPONSE_PREFIX = b"I_AM_PEER"
    
    found = set()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(2.0)
        
        try:
            sock.sendto(PEER_DISCOVERY_MSG, ('<broadcast>', DISCOVERY_PORT))
        except Exception as e:
            pass
            
        if broadcast:
             try:
                 sock.sendto(PEER_DISCOVERY_MSG, (broadcast, DISCOVERY_PORT))
             except Exception:
                 pass
        
        start_time = time.time()
        while time.time() - start_time < 2.0:
            try:
                data, addr = sock.recvfrom(4096)
                if data.startswith(PEER_RESPONSE_PREFIX):
                    parts = data.decode().split()
                    if len(parts) >= 2:
                        found.add(parts[1])
                    else:
                        found.add(addr[0])
            except socket.timeout:
                break
            except Exception:
                pass
        sock.close()
    except Exception as e:
        print(f"[!] Peer UDP Scan failed: {e}", file=os.sys.stderr)
        
    return list(found)

class PeerDiscoveryListener:
    
    DISCOVERY_PORT = 4436
    PEER_DISCOVERY_MSG = b"WHO_IS_PEER"
    PEER_RESPONSE_PREFIX = b"I_AM_PEER"
    
    def __init__(self, host_ip: str):
       
        self.host_ip = host_ip
        self.transport = None
        self.protocol = None
    
    class Protocol(asyncio.DatagramProtocol):
        
        def __init__(self, host_ip: str):
            self.host_ip = host_ip
            self.transport = None
        
        def connection_made(self, transport):
            self.transport = transport
        
        def datagram_received(self, data: bytes, addr: tuple):
            if data == PeerDiscoveryListener.PEER_DISCOVERY_MSG:
                response = f"{PeerDiscoveryListener.PEER_RESPONSE_PREFIX.decode()} {self.host_ip}".encode()
                self.transport.sendto(response, addr)
    
    async def start(self):
        loop = asyncio.get_running_loop()
        
        self.transport, self.protocol = await loop.create_datagram_endpoint(
            lambda: self.Protocol(self.host_ip),
            local_addr=('0.0.0.0', self.DISCOVERY_PORT),
            allow_broadcast=True
        )
        print(f"[+] Peer Discovery Listener started on port {self.DISCOVERY_PORT}")
    
    def stop(self):
        if self.transport:
            self.transport.close()
            print(f"[+] Peer Discovery Listener stopped")

async def start_peer_discovery_listener(host_ip: str) -> PeerDiscoveryListener:
   
    listener = PeerDiscoveryListener(host_ip)
    await listener.start()
    return listener



class ManualScanner:
    
    def __init__(self):
        global gateway, cidr, file_path, host_ip, broadcast, system_name, interface, user, pwd, dest_host
    
    def scanfromlinux():
    
        checkfile()

        if not gateway:
            print("[!] GATEWAY not set in environment (GATEWAY).", file=os.sys.stderr)
            return []
        try:
            network = f"{gateway}/{cidr}"
        
            IPv4Network(network, strict=False)
        except Exception as e:
            print(f"[!] Invalid network from GATEWAY/CIDR: {e}", file=os.sys.stderr)
            return []

        methods = [
            ("ping_sweep", scan_ping_sweep),
            ("arp_neigh", scan_arp_table),
            ("nmap_unprivileged", scan_nmap_unprivileged),
            # ("udp_broadcast", scan_udp),
        ]
        hostset = set()
        for name, func in methods:
            try:
                found = func(network)
                if found:
                    hostset.update(found)
                
            except Exception as e:
                print(f"[!] {name} failed: {e}", file=os.sys.stderr)
                continue
        if hostset:
            append_host(hostset)
            return hostset
        return []

    def scan_nmap_unprivileged(network: str, ports: str = "22,80,443,445", timeout: int = 120) -> List[str]:
        try:
            try:
                subprocess.run(["nmap", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except FileNotFoundError:
                return []

            args = ["nmap", "-Pn", "-sT", "-p", ports, "-T4", "--open", network]

            result = subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=timeout)
            found = re.findall(r'Nmap scan report for (\d{1,3}(?:\.\d{1,3}){3})', result)
            unique = sorted(set(found))
            return unique
        except subprocess.TimeoutExpired:
            return []
        except Exception:
            return []

    def ping_silent_linux(ip: str) -> None:
        try:
            subprocess.run(["ping", "-c", "1", "-W", "1", ip],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
        except Exception:
            pass

    def scan_arp_table(network: str) -> List[str]:
    
        try:
            net = IPv4Network(network, strict=False)
        except Exception:
            return []

        all_ips = [str(ip) for ip in net]

        if len(all_ips) > 1024:
            all_ips = all_ips[:1024]

        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
            list(ex.map(ping_silent_linux, all_ips))

        try:
            out = subprocess.check_output(["ip", "neigh"], text=True)
        except Exception:
            return []

        ips = set(re.findall(r'(\d{1,3}(?:\.\d{1,3}){3})', out))
        filtered = [ip for ip in sorted(ips) if IPv4Address(ip) in net]
        return filtered

    def scan_ping_sweep(network: str) -> List[str]:
        try:
            net = IPv4Network(network, strict=False)
        except Exception:
            return []

        ip_list = [str(ip) for ip in net]

        if len(ip_list) > 4096:
            ip_list = ip_list[:4096]

        def ping_check(ip: str):
            try:
                res = subprocess.run(["ping", "-c", "1", "-W", "1", ip],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
                return ip if res.returncode == 0 else None
            except Exception:
                return None

        alive = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=200) as ex:
            for r in ex.map(ping_check, ip_list):
                if r:
                    alive.append(r)
        return alive

    def ping_silent(ip):
        try:
            subprocess.run(
                ["ping", "-n", "1", "-w", "100", ip],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except:
            pass

    def scanfromwin():
        
        checkfile()
        
        if cidr == "24":
            base = gateway.rsplit('.', 1)[0] + "."
            start, end = 1, 255
        elif cidr == "16":
            parts = gateway.split('.')
            base = f"{parts[0]}.{parts[1]}."
            base = gateway.rsplit('.', 1)[0] + "."
            start, end = 1, 255
        else:
            base = gateway.rsplit('.', 1)[0] + "."
            start, end = 1, 255
        
        print(f"[*] Scanning network: {base}0/{cidr}")
        print(f"[*] Pinging {end - start} addresses...")
        
        threads = []
        for i in range(start, end + 1):
            ip = base + str(i)
            thr = threading.Thread(target=ping_silent, args=(ip,))
            threads.append(thr)
        
        for thr in threads:
            thr.start()
        
        for thr in threads:
            thr.join()
        
        print("[*] Ping sweep complete, checking ARP cache...")
        
        try:
            result = subprocess.run(
                ["arp", "-a"], 
                capture_output=True, 
                text=True,
                
            )
            output = result.stdout
            
            ips = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', output)
            unique_ips = list(set(ips))
            
            if cidr == "24":
                unique_ips = [ip for ip in unique_ips if ip.startswith(base)]
            
            print(f"[+] Found {len(unique_ips)} hosts")
            append_host(unique_ips)
            return unique_ips
            
        except subprocess.TimeoutExpired:
            print("[!] ARP command timed out")
            return []
        except Exception as e:
            print(f"[!] Error reading ARP table: {e}")
            return []

    def append_host(lis):
        
        checkfile()
        
        try:
            with open(file_path, "r") as fh:
                data = fh.readlines()
            
            existing_ips = set(line.strip() for line in data if line.strip())
            
            total_ips = existing_ips.union(lis)
            
            with open(file_path, "w") as fh:
                for ip in sorted(total_ips, key=lambda x: [int(p) for p in x.split('.')]):
                    fh.write(ip + "\n")
            
            print(f"[+] Updated {file_path} with {len(total_ips)} total hosts")
            
        except Exception as e:
            print(f"[!] Error updating host list: {e}")
