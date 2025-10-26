import subprocess
import re
import nmap

def get_live_hosts(subnet='192.168.0.1/24'):
    """Performs a UDP scan on port 161 to find SNMP-enabled hosts."""
    cmd = ['sudo', 'nmap', '-sU', '-p', '161', subnet]
    result = subprocess.run(cmd, capture_output=True, text=True)

    live_ips = []
    for line in result.stdout.splitlines():
        if line.startswith("Nmap scan report for"):
            ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
            if ip_match:
                live_ips.append(ip_match.group(1))
    return live_ips

def scan_tcp_ports(ip):
    """Performs a TCP port scan on the given IP."""
    nm = nmap.PortScanner()
    print(f"\nScanning TCP ports on {ip}...")
    nm.scan(hosts=ip, arguments='-Pn -sS -T4')
    for host in nm.all_hosts():
        print(f"Host: {host} ({nm[host].hostname()})")
        print(f"State: {nm[host].state()}")
        for proto in nm[host].all_protocols():
            ports = nm[host][proto].keys()
            for port in sorted(ports):
                state = nm[host][proto][port]['state']
                print(f"Port: {port}/{proto} - {state}")

# Run the workflow
hosts = get_live_hosts()
print(f"Discovered hosts: {hosts}")
for ip in hosts:
    scan_tcp_ports(ip)
