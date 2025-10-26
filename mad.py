import os
import subprocess

def gethostlist():
    for i in range(10):
        os.system("arp-scan --interface=wlan0 --localnet | awk '/^[0-9]+\./{print $1}' >> ips.txt")


    fh = open("ips.txt", "r")
    lines = fh.readlines()
    fh.close()
    unique_ips = set()
    for line in lines:
        unique_ips.add(line.strip())


    ssh_open_ips = []

    for ip in unique_ips:
        # Run nmap and capture return code
        result = subprocess.run(
            ["nmap", "-Pn", "-p22", "-oG", "-", ip],
            stdout=subprocess.DEVNULL,  # ignore stdout
            stderr=subprocess.DEVNULL
        )
        # If return code is 0, nmap ran successfully
        # Check if port 22 is open using grep
        check = subprocess.run(
            f"nmap -Pn -p22 -oG - {ip} | grep -q '22/open'",
            shell=True
        )
        if check.returncode == 0:
            ssh_open_ips.append(ip)

    return ssh_open_ips

