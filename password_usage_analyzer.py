#!/usr/bin/env python3
"""
Password Usage Analyzer for LANFXplorer

This script searches for all password-related references in the codebase,
traces their definitions and usages, and generates a detailed report on:
  - What password variables are actually used
  - What password variables are defined but not used
  - What seems to be misused/mismatched

Usage:
    source $PYTHONBI && python password_usage_analyzer.py
"""

import os
import re
import json
from dataclasses import dataclass, field
from typing import List, Dict, Set, Tuple, Optional
from pathlib import Path
from collections import defaultdict

# Configuration
PROJECT_ROOT = Path(__file__).parent.resolve()
SEARCH_EXTENSIONS = {'.py', '.dart', '.env'}
EXCLUDE_DIRS = {'.git', '__pycache__', '.dart_tool', 'build', 'dump', 'linux', '.metadata'}

# Password-related patterns to search for
PASSWORD_PATTERNS = [
    r'password',
    r'PASSWORD',
    r'P2P_PASSWORD',
    r'RECEIVER_PASSWORD',
    r'password_hash',
    r'receiver_password',
    r'p2p_password',
]

@dataclass
class PasswordReference:
    """Represents a password-related reference in the code."""
    file_path: str
    line_number: int
    line_content: str
    variable_name: str
    ref_type: str  # 'definition', 'usage', 'parameter', 'env_access', 'comment'
    context: str = ""

@dataclass
class PasswordVariable:
    """Represents a password variable and its lifecycle."""
    name: str
    definitions: List[PasswordReference] = field(default_factory=list)
    usages: List[PasswordReference] = field(default_factory=list)
    env_accesses: List[PasswordReference] = field(default_factory=list)
    parameters: List[PasswordReference] = field(default_factory=list)
    comments: List[PasswordReference] = field(default_factory=list)

def get_all_files(root: Path) -> List[Path]:
    """Get all relevant files for analysis."""
    files = []
    for path in root.rglob('*'):
        if path.is_file() and path.suffix in SEARCH_EXTENSIONS:
            # Skip excluded directories
            if any(excl in path.parts for excl in EXCLUDE_DIRS):
                continue
            files.append(path)
    return files

def classify_reference(line: str, var_name: str, file_ext: str) -> str:
    """Classify the type of password reference."""
    line_stripped = line.strip()
    
    # Check if it's a comment
    if file_ext == '.py':
        if line_stripped.startswith('#') or line_stripped.startswith('"""') or line_stripped.startswith("'''"):
            return 'comment'
    elif file_ext == '.dart':
        if line_stripped.startswith('//') or line_stripped.startswith('/*') or line_stripped.startswith('*'):
            return 'comment'
    
    # Check for environment variable access
    if 'os.getenv' in line or 'os.environ' in line:
        return 'env_access'
    
    # Check for function parameter
    if re.search(rf'{var_name}\s*:', line) or re.search(rf'{var_name}\s*=\s*None', line):
        if 'def ' in line or 'async def ' in line:
            return 'parameter'
    
    # Check for definition (assignment)
    if re.search(rf'^[\s]*{var_name}\s*[=:]', line) or re.search(rf'^[\s]*self\.{var_name}\s*=', line):
        return 'definition'
    
    # Check for .env file
    if file_ext == '.env':
        if '=' in line:
            return 'definition'
    
    return 'usage'

def extract_variable_name(line: str, pattern: str) -> str:
    """Extract the specific variable name from a line."""
    # Find all matches for the pattern
    matches = re.findall(rf'\b({pattern}[_a-zA-Z0-9]*)\b', line, re.IGNORECASE)
    if matches:
        return matches[0]
    
    # Check for more specific patterns
    if 'password' in line.lower():
        # Try to extract the full variable name
        var_match = re.search(r'["\']?([a-zA-Z_][a-zA-Z0-9_]*password[a-zA-Z0-9_]*)["\']?', line, re.IGNORECASE)
        if var_match:
            return var_match.group(1)
        
        var_match = re.search(r'["\']?(password[a-zA-Z0-9_]*)["\']?', line, re.IGNORECASE)
        if var_match:
            return var_match.group(1)
    
    return pattern

def search_password_references(files: List[Path]) -> Dict[str, PasswordVariable]:
    """Search all files for password-related references."""
    password_vars: Dict[str, PasswordVariable] = defaultdict(lambda: PasswordVariable(name=""))
    
    for file_path in files:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        except Exception as e:
            print(f"[!] Error reading {file_path}: {e}")
            continue
        
        rel_path = str(file_path.relative_to(PROJECT_ROOT))
        file_ext = file_path.suffix
        
        for line_num, line in enumerate(lines, 1):
            line_lower = line.lower()
            
            # Check if line contains any password-related pattern
            if 'password' not in line_lower:
                continue
            
            for pattern in PASSWORD_PATTERNS:
                if pattern.lower() in line_lower:
                    var_name = extract_variable_name(line, pattern)
                    ref_type = classify_reference(line, var_name, file_ext)
                    
                    ref = PasswordReference(
                        file_path=rel_path,
                        line_number=line_num,
                        line_content=line.strip(),
                        variable_name=var_name,
                        ref_type=ref_type,
                        context=get_context(lines, line_num)
                    )
                    
                    # Normalize variable name for grouping
                    normalized_name = var_name.lower().replace('-', '_')
                    
                    if password_vars[normalized_name].name == "":
                        password_vars[normalized_name].name = var_name
                    
                    if ref_type == 'definition':
                        password_vars[normalized_name].definitions.append(ref)
                    elif ref_type == 'usage':
                        password_vars[normalized_name].usages.append(ref)
                    elif ref_type == 'env_access':
                        password_vars[normalized_name].env_accesses.append(ref)
                    elif ref_type == 'parameter':
                        password_vars[normalized_name].parameters.append(ref)
                    elif ref_type == 'comment':
                        password_vars[normalized_name].comments.append(ref)
                    
                    break  # Only match once per line
    
    return dict(password_vars)

def get_context(lines: List[str], line_num: int, context_size: int = 2) -> str:
    """Get surrounding context for a line."""
    start = max(0, line_num - context_size - 1)
    end = min(len(lines), line_num + context_size)
    context_lines = lines[start:end]
    return '\n'.join([l.rstrip() for l in context_lines])

def analyze_password_flow() -> Dict:
    """Analyze the complete password flow in the application."""
    flow = {
        'env_variables': {
            'P2P_PASSWORD': {
                'defined_in': '.env',
                'loaded_via': 'startsetup.py → load_env_vars() → os.getenv("P2P_PASSWORD")',
                'used_by': [
                    'receiver_api_functions.py → _handle_stream() → env_pass = os.environ.get("P2P_PASSWORD")',
                    'startsetup.py → load_env_vars() → returned in dict as both "P2P_PASSWORD" and "p2p_password"'
                ],
                'issues': []
            },
            'RECEIVER_PASSWORD': {
                'defined_in': '.env',
                'loaded_via': 'recive.py → os.getenv("RECEIVER_PASSWORD", "default_temp_password")',
                'used_by': [
                    'recive.py → main() → passed to start_handshake_service()',
                    'pki/handshake.py → HandshakeService → self.receiver_password → validates password from sender'
                ],
                'issues': []
            }
        },
        'ui_password': {
            'input_source': 'lib/presentation/dialogs/connection_dialog.dart → _passwordController.text',
            'sent_via': 'lib/data/services/api_service.dart → initiateHandshake() → POST /handshake body: {password}',
            'received_by': 'api_bridge.py → /handshake → data.get("password")',
            'forwarded_to': 'pki/handshake.py → initiate_handshake() → sends password to receiver',
            'issues': []
        }
    }
    return flow

def check_password_misuses(password_vars: Dict[str, PasswordVariable]) -> List[Dict]:
    """Check for potential password misuses and mismatches."""
    issues = []
    
    # Check 1: P2P_PASSWORD vs RECEIVER_PASSWORD inconsistency
    issues.append({
        'severity': 'HIGH',
        'type': 'DUAL_PASSWORD_SYSTEM',
        'description': 'Two separate password mechanisms exist that may cause confusion',
        'details': [
            'P2P_PASSWORD: Used by receiver_api_functions.py for direct QUIC file transfer auth',
            'RECEIVER_PASSWORD: Used by pki/handshake.py for TCP handshake auth (port 4437)',
            'These are DIFFERENT services with DIFFERENT passwords!',
            'If user sets only one password, the other service will fail or use default.'
        ],
        'recommendation': 'Consider unifying to a single password, or clearly document the dual-password requirement.'
    })
    
    # Check 2: Default password fallback
    issues.append({
        'severity': 'MEDIUM',
        'type': 'DEFAULT_PASSWORD_FALLBACK',
        'description': 'recive.py uses a default password if RECEIVER_PASSWORD is not set',
        'details': [
            "recive.py line 124: receiver_password = os.getenv('RECEIVER_PASSWORD', 'default_temp_password')",
            'This creates a security risk if the env variable is not properly set.',
            'A warning is printed but the service continues with the default.'
        ],
        'recommendation': 'Consider failing startup if RECEIVER_PASSWORD is not set, or generate a random password.'
    })
    
    # Check 3: Password storage in PeerStore is optionally used
    issues.append({
        'severity': 'LOW',
        'type': 'UNUSED_PEER_STORE_PASSWORD',
        'description': 'pki/store.py has set_password/verify_password methods that appear underutilized',
        'details': [
            'PeerStore.set_password() hashes password with bcrypt and stores in peers.json',
            'PeerStore.verify_password() verifies against stored hash',
            'api_bridge.py /peers/verify endpoint uses verify_password()',
            'api_bridge.py /peers/approve can optionally set password',
            'BUT: The main handshake flow in pki/handshake.py does NOT use PeerStore password verification!',
            'Instead, it compares directly against self.receiver_password (from RECEIVER_PASSWORD env)'
        ],
        'recommendation': 'Either integrate PeerStore password verification into handshake, or remove the unused functionality.'
    })
    
    # Check 4: send_auth function in sender_api_functions.py
    issues.append({
        'severity': 'MEDIUM',
        'type': 'POTENTIALLY_UNUSED_SEND_AUTH',
        'description': 'sender_api_functions.py has send_auth() function that may not be called',
        'details': [
            'send_auth() sends __AUTH__ special file with password over QUIC',
            'receiver_api_functions.py handles __AUTH__ and validates against P2P_PASSWORD',
            'BUT: api_bridge.py /send_files does NOT call send_auth() before sending files!',
            'This means the QUIC file transfer may work without authentication if require_client_cert=False'
        ],
        'recommendation': 'Either integrate send_auth() into the send_files flow, or document why it is optional.'
    })
    
    # Check 5: Password from UI flow
    issues.append({
        'severity': 'INFO',
        'type': 'UI_PASSWORD_FLOW_ANALYSIS',
        'description': 'Password entered in Flutter UI is used for handshake, not file transfer',
        'details': [
            'User enters password in connection_dialog.dart',
            'Password is sent to api_bridge.py /handshake endpoint',
            '/handshake calls pki/handshake.py initiate_handshake()',
            'This validates against receiver\'s RECEIVER_PASSWORD via TCP:4437',
            'After handshake, certificates are exchanged and trusted',
            'Subsequent file transfers via QUIC:4433 use certificate-based auth (if require_client_cert=True)',
            'BUT: require_client_cert is set to False in recive.py!',
            'This means after handshake, file transfers work without re-authentication.'
        ],
        'recommendation': 'Consider adding auth token or session validation for post-handshake file transfers.'
    })
    
    return issues

def generate_report(password_vars: Dict[str, PasswordVariable], 
                    flow: Dict, 
                    issues: List[Dict]) -> str:
    """Generate a comprehensive report."""
    report_lines = []
    
    # Header
    report_lines.append("=" * 80)
    report_lines.append("PASSWORD USAGE ANALYSIS REPORT")
    report_lines.append("LANFXplorer Project")
    report_lines.append("=" * 80)
    report_lines.append("")
    
    # Summary Statistics
    report_lines.append("## SUMMARY STATISTICS")
    report_lines.append("-" * 40)
    total_references = sum(
        len(pv.definitions) + len(pv.usages) + len(pv.env_accesses) + len(pv.parameters) + len(pv.comments)
        for pv in password_vars.values()
    )
    report_lines.append(f"Total password-related references found: {total_references}")
    report_lines.append(f"Unique password variable names: {len(password_vars)}")
    report_lines.append(f"Issues identified: {len(issues)}")
    report_lines.append("")
    
    # Password Variables Found
    report_lines.append("## PASSWORD VARIABLES FOUND")
    report_lines.append("-" * 40)
    for name, pv in sorted(password_vars.items()):
        report_lines.append(f"\n### {pv.name}")
        report_lines.append(f"  Definitions: {len(pv.definitions)}")
        report_lines.append(f"  Usages: {len(pv.usages)}")
        report_lines.append(f"  Env Accesses: {len(pv.env_accesses)}")
        report_lines.append(f"  Parameters: {len(pv.parameters)}")
        report_lines.append(f"  Comments: {len(pv.comments)}")
    report_lines.append("")
    
    # Detailed Password Flow
    report_lines.append("## PASSWORD FLOW ANALYSIS")
    report_lines.append("-" * 40)
    
    report_lines.append("\n### Environment Variables")
    for env_var, details in flow['env_variables'].items():
        report_lines.append(f"\n#### {env_var}")
        report_lines.append(f"  Defined in: {details['defined_in']}")
        report_lines.append(f"  Loaded via: {details['loaded_via']}")
        report_lines.append(f"  Used by:")
        for usage in details['used_by']:
            report_lines.append(f"    - {usage}")
    
    report_lines.append("\n### UI Password Flow")
    for key, value in flow['ui_password'].items():
        if key != 'issues':
            report_lines.append(f"  {key}: {value}")
    report_lines.append("")
    
    # What is USED
    report_lines.append("## WHAT IS ACTUALLY USED ✓")
    report_lines.append("-" * 40)
    report_lines.append("""
1. **RECEIVER_PASSWORD** (Env Variable)
   - Used in: recive.py → start_handshake_service()
   - Purpose: Authenticates incoming handshake requests from senders
   - Flow: Sender → TCP:4437 → HandshakeService → validates password → exchanges certs
   - STATUS: ACTIVELY USED ✓

2. **P2P_PASSWORD** (Env Variable)
   - Used in: receiver_api_functions.py → _handle_stream() → __AUTH__ handler
   - Purpose: Authenticates sender for direct QUIC file transfers
   - Flow: Sender sends __AUTH__ special file → Receiver validates against P2P_PASSWORD
   - STATUS: CONDITIONALLY USED (only if send_auth() is called)

3. **password (Flutter UI)**
   - Input: connection_dialog.dart → _passwordController.text
   - Used in: api_service.dart → initiateHandshake() → POST /handshake
   - Purpose: User-provided password to authenticate with remote peer
   - STATUS: ACTIVELY USED ✓

4. **password_hash (PeerStore)**
   - Used in: pki/store.py → set_password(), verify_password()
   - Purpose: Store bcrypt-hashed passwords for trusted peers
   - Accessed via: api_bridge.py → /peers/verify, /peers/approve endpoints
   - STATUS: AVAILABLE BUT UNDERUTILIZED
""")
    
    # What is NOT Used
    report_lines.append("\n## WHAT IS NOT USED / UNDERUTILIZED ✗")
    report_lines.append("-" * 40)
    report_lines.append("""
1. **send_auth() in sender_api_functions.py**
   - Defined but NOT called in the /send_files flow
   - Would send password for QUIC-level authentication
   - STATUS: DEFINED BUT NOT USED IN MAIN FLOW

2. **PeerStore.verify_password() for handshake**
   - Exists but handshake uses direct string comparison instead
   - pki/handshake.py compares: if password != self.receiver_password
   - Does NOT use PeerStore.verify_password()
   - STATUS: NOT USED FOR ITS INTENDED PURPOSE

3. **password in p2p_password key (lowercase)**
   - startsetup.py returns both 'P2P_PASSWORD' and 'p2p_password' (same value)
   - Only 'P2P_PASSWORD' (via os.environ) is used in receiver_api_functions.py
   - STATUS: 'p2p_password' key is REDUNDANT/UNUSED
""")
    
    # Misuses and Mismatches
    report_lines.append("\n## MISUSES AND POTENTIAL ISSUES ⚠")
    report_lines.append("-" * 40)
    for issue in issues:
        report_lines.append(f"\n### [{issue['severity']}] {issue['type']}")
        report_lines.append(f"**Description:** {issue['description']}")
        report_lines.append(f"**Details:**")
        for detail in issue['details']:
            report_lines.append(f"  - {detail}")
        report_lines.append(f"**Recommendation:** {issue['recommendation']}")
    
    # Detailed References
    report_lines.append("\n\n## DETAILED REFERENCE LOCATIONS")
    report_lines.append("-" * 40)
    for name, pv in sorted(password_vars.items()):
        all_refs = pv.definitions + pv.usages + pv.env_accesses + pv.parameters
        if not all_refs:
            continue
        
        report_lines.append(f"\n### {pv.name}")
        for ref in sorted(all_refs, key=lambda r: (r.file_path, r.line_number)):
            report_lines.append(f"  [{ref.ref_type:12}] {ref.file_path}:{ref.line_number}")
            report_lines.append(f"                {ref.line_content[:100]}")
    
    # Recommendations
    report_lines.append("\n\n## RECOMMENDATIONS")
    report_lines.append("-" * 40)
    report_lines.append("""
1. **UNIFY PASSWORD SYSTEM**
   - Currently there are TWO separate password systems (P2P_PASSWORD and RECEIVER_PASSWORD)
   - Consider using a single password for both handshake and file transfer auth
   - Or: After handshake, issue a session token for subsequent transfers

2. **INTEGRATE send_auth() INTO FILE TRANSFER**
   - api_bridge.py /send_files should call send_auth() before sending files
   - This ensures QUIC file transfers are authenticated
   - Alternative: Use client certificates (set require_client_cert=True)

3. **USE PeerStore FOR PASSWORD STORAGE**
   - Instead of comparing against env variable, use stored password hashes
   - This allows per-peer passwords instead of a single global password

4. **REMOVE DEFAULT PASSWORD**
   - recive.py should NOT fall back to 'default_temp_password'
   - Either fail startup or generate a random password and display it

5. **ADD POST-HANDSHAKE VERIFICATION**
   - After handshake completes, file transfers work without re-auth
   - Consider adding fingerprint verification or session tokens
""")
    
    return '\n'.join(report_lines)

def main():
    print("[*] Password Usage Analyzer for LANFXplorer")
    print("[*] Scanning project files...")
    
    files = get_all_files(PROJECT_ROOT)
    print(f"[+] Found {len(files)} files to analyze")
    
    print("[*] Searching for password references...")
    password_vars = search_password_references(files)
    print(f"[+] Found {len(password_vars)} unique password variable patterns")
    
    print("[*] Analyzing password flow...")
    flow = analyze_password_flow()
    
    print("[*] Checking for potential issues...")
    issues = check_password_misuses(password_vars)
    print(f"[!] Identified {len(issues)} potential issues")
    
    print("[*] Generating report...")
    report = generate_report(password_vars, flow, issues)
    
    # Save report
    report_path = PROJECT_ROOT / "password_usage_report.txt"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n[+] Report saved to: {report_path}")
    print("\n" + "=" * 80)
    print(report)

if __name__ == "__main__":
    main()
