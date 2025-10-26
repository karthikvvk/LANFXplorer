#!/usr/bin/env bash
set -euo pipefail

# Output file
OUT="hosts.txt"

# Network to scan - change if needed
NETWORK="192.168.0.1/24"

# Clear previous output
: > "$OUT"

# 1) UDP scan to find hosts (port 161)
echo "Running UDP discovery on $NETWORK (requires sudo)..."
# -oG - -> greppable output to stdout. awk extracts IPs with Status: Up
mapfile -t DISCOVERED_IPS < <(sudo nmap -sU -p161 --max-retries 3 --host-timeout 30s -oG - "$NETWORK" | awk '/Status: Up/ {print $2}')

if [ ${#DISCOVERED_IPS[@]} -eq 0 ]; then
  echo "No hosts found by UDP scan."
  exit 0
fi

echo "Discovered ${#DISCOVERED_IPS[@]} hosts. Checking SSH (tcp/22)..."

# 2) Check SSH on each discovered IP and append if open
for ip in "${DISCOVERED_IPS[@]}"; do
  echo -n "Scanning $ip for SSH... "
  # Use -Pn to skip host discovery (we already know host is up), -oG - to parse easily
  if nmap -Pn -p22 -oG - "$ip" | awk -F'Ports: ' '/Ports: / {print $2}' | grep -qE '(^|[^0-9])22/[^ ]*open'; then
    echo "OPEN -> saving to $OUT"
    echo "$ip" >> "$OUT"
  else
    echo "closed/filtered"
  fi
done

echo "Done. SSH hosts written to $OUT (if any)."
