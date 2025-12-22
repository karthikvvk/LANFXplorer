#!/usr/bin/env python3
"""Test password authentication"""
import asyncio
import os
from startsetup import load_env_vars
from sender_api_functions import quic_connect, send_auth, close_connection

async def test():
    env = load_env_vars()
    
    host = "192.168.0.100"  # Send to ourselves
    port = int(env.get("port", 4433))
    password = env.get("P2P_PASSWORD") or env.get("p2p_password")
    
    print(f"Testing authentication to {host}:{port}")
    print(f"Password: {password}")
    
    client_cert = env.get("certi")
    client_key = env.get("key")
    ca_cert = env.get("ca_cert")
    
    print(f"Certs: {client_cert}, {client_key}, {ca_cert}")
    
    try:
        print("Connecting...")
        conn = await quic_connect(
            host=host,
            port=port,
            client_cert=client_cert,
            client_key=client_key,
            ca_cert=ca_cert
        )
        print("Connected!")
        
        print("Sending authentication...")
        result = await send_auth(conn, password)
        print(f"Authentication result: {result}")
        
        await close_connection(conn)
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
