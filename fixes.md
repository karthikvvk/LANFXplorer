Now enough pieces are visible to see the whole PKI picture.

The good news is that the crypto primitives themselves are mostly fine:

```text
RSA 2048
SHA256
CSR generation
CA signing
Certificate fingerprints
SAN support
```

The weak points are almost entirely in the **trust model**, not the crypto.

---

# Critical Issue 1: Rogue CA Attack

Current flow:

```text
Peer starts
   ↓
WHO_IS_CA broadcast
   ↓
First responder wins
   ↓
Receive CA cert
   ↓
Trust it
```

The dangerous code is effectively:

```python
client_cert, ca_cert_pem = await ca_mgr.get_signed_cert(...)
```

There is no verification that:

```text
This CA is the CA I trusted yesterday
```

Only:

```text
This CA answered first
```

Imagine:

```text
Laptop A = legitimate CA

Attacker laptop joins LAN

Attacker responds:
"I_AM_CA"
```

before Laptop A.

Every new node now trusts attacker certificates.

This is the single largest security issue in the whole project.

---

# Fix: TOFU CA Pinning

SSH solved this 25 years ago.

First connection:

```text
CA fingerprint:
A1:B2:C3:D4
```

Store it permanently.

Next startup:

```text
CA fingerprint changed
```

↓

```text
WARNING
Unknown CA
```

Require user approval.

Current code has:

```python
fingerprint_pem()
PeerStore
```

which is already enough to implement this.

---

# Critical Issue 2: CA Certificate Not Verified During Enrollment

Current flow:

```python
reader, writer = await asyncio.open_connection(host, port)

ca_cert_pem = await reader.readexactly(...)
```

The CA literally sends:

```text
"Here is my CA certificate"
```

and the client accepts it.

There is no check:

```text
Does this CA match previously trusted CA?
```

or

```text
Does fingerprint match stored CA?
```

This is effectively:

```text
Trust whoever answered
```

again.

---

# Critical Issue 3: CA Private Key Stored Unencrypted

Current code:

```python
ca_key_pem = key.private_bytes(
    ...
    encryption_algorithm=serialization.NoEncryption()
)
```

Then:

```python
with open("ca_key.pem")
```

---

Meaning:

```text
ca_key.pem
```

is plaintext.

Anyone obtaining:

```text
ca_key.pem
```

owns the network forever.

They can:

```text
Sign certificates
Impersonate peers
Become CA
```

---

For home LAN:

maybe acceptable.

For anything bigger:

not acceptable.

---

Possible improvement:

```text
OS keyring
or
password-protected CA key
```

Even a user password protecting the CA key would be much better.

---

# Critical Issue 4: CA Key Lifetime

Current design:

```text
Node becomes CA
```

↓

Generates:

```text
ca_key.pem
ca_cert.pem
```

↓

Forever trusted.

---

No rotation.

No renewal.

No expiry handling.

No replacement process.

---

Imagine:

```text
CA certificate expires
```

after:

```python
365 days
```

Current architecture appears to have no recovery plan.

---

Need:

```text
CA rotation process
```

or

```text
Long-lived CA
Short-lived client certs
```

---

# Critical Issue 5: No Verification of CSR Ownership

Current signing server:

```python
csr_pem = await reader.readexactly(...)
client_cert = sign_csr(...)
```

That's it.

No checks.

---

Meaning:

Anybody who reaches:

```text
CA signing port
```

gets a certificate.

---

Current flow:

```text
CSR
↓
Signed
```

No:

```text
Password
Approval
Enrollment policy
```

---

In enterprise PKI:

```text
Enrollment authorization
```

is separate from:

```text
Signing
```

Your CA currently signs everything.

---

# Critical Issue 6: Authentication is Password-Based, Not Certificate-Based

This surprised me.

You built:

```text
CA
CSR
Certificates
Fingerprints
PeerStore
```

---

Then actual authentication is:

```python
{
  "type":"AUTH",
  "password":"..."
}
```

on TCP 4437.

---

Meaning:

Current trust hierarchy is:

```text
Password
   ↑
Real authority
```

Certificates are mostly decorative right now.

---

The certificate fingerprint:

```python
fp
```

is only used for bookkeeping:

```python
peer_store.approve_peer(fp)
```

---

But authentication success comes from:

```python
hmac.compare_digest(password, expected)
```

---

So the system is actually:

```text
Shared Secret Authentication
```

not

```text
Certificate Authentication
```

---

This is a major architectural mismatch.

---

# What I'd Change

Current:

```text
Certificate
+
Password
```

but password is authoritative.

---

Instead:

```text
Certificate = Identity

Password = User Approval
```

---

Example:

```text
Laptop A connects

Certificate verified
```

↓

Unknown fingerprint

↓

Prompt:

```text
Trust Laptop A?
```

↓

Store fingerprint.

---

After that:

```text
Certificate alone
```

authenticates peer.

---

Password becomes optional:

```text
Require password before receiving files
```

like AirDrop approval.

Not identity verification.

---

# Issue 7: PeerStore Encryption Is Mostly Cosmetic

Interesting one.

You encrypt:

```text
cert_pem
```

using Fernet.

But:

```python
.peers_key
```

is stored beside:

```text
peers.json
```

---

Attacker steals directory:

```text
.peers_key
peers.json
```

---

Can decrypt everything.

---

This protects against:

```text
Accidental viewing
```

not

```text
Compromised account
```

---

Not harmful.

Just don't assume it provides strong security.

---

# Issue 8: PeerStore Doesn't Pin the CA

You already built:

```text
PeerStore
fingerprints
trust states
```

---

But currently stores:

```text
Peer fingerprints
```

not

```text
CA fingerprint
```

---

That's the first thing I'd add.

Example:

```json
{
  "trusted_ca": {
      "fingerprint":"..."
  }
}
```

---

Then:

```text
CA changed
```

becomes detectable.

---

# Issue 9: Certificate Revocation Exists But Isn't Enforced

You have:

```python
revoke_peer()
is_revoked()
```

Very nice.

---

But I don't see:

```python
verify_peer_cert()
```

checking:

```python
peer_store.is_revoked(fp)
```

during connection establishment.

---

Meaning:

```text
Revoked peer
```

may still connect.

Need to inspect QUIC side to confirm.

---

# Issue 10: CA Discovery is Unauthenticated

Current protocol:

```text
WHO_IS_CA
```

↓

```text
I_AM_CA 192.168.1.5 4436
```

---

No signature.

No verification.

No challenge.

Nothing.

---

This makes spoofing trivial.

Even if you add CA pinning later, first-time setup remains vulnerable.

That's why SSH uses:

```text
Trust On First Use
```

and warns on change.

---

# The biggest architectural realization

After seeing all of this, LANFXplorer currently behaves like:

```text
Password-based file transfer
```

with

```text
Certificate infrastructure
```

around it.

Not:

```text
Certificate-authenticated file transfer
```

yet.

The PKI is generating identities, fingerprints, trust stores, CA signing, revocation structures, and certificate chains — but the actual access decision is still made by:

```python
hmac.compare_digest(password, expected)
```

If there is one direction I'd push the project, it would be:

```text
Phase 1:
Add CA fingerprint pinning

Phase 2:
Require certificate validation for every peer

Phase 3:
Make certificate identity the primary trust decision

Phase 4:
Use password only as user approval / transfer authorization
```

Those four changes would improve security more than every path-security and config-manager improvement combined.










Sudoers rule (so your user script can read nvme without a password prompt)
bashsudo visudo -f /etc/sudoers.d/nvme-readonly
Add this line (replace yourusername with your actual username):
yourusername ALL=(ALL) NOPASSWD: /usr/bin/nvme smart-log /dev/nvme0
