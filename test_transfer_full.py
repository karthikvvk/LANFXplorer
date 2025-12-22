#!/usr/bin/env python3
"""Direct test of file transfer"""
import asyncio
import os
from startsetup import load_env_vars
from sender_api_functions import quic_connect, send_auth, send_file, close_connection

async def test():
    env = load_env_vars()
    
    host = "192.168.0.100"
    port = int(env.get("port", 4433))
    password = env.get("P2P_PASSWORD")
    
    client_cert = env.get("certi")
    client_key = env.get("key")
    ca_cert = env.get("ca_cert")
    
    test_file = "/home/muruga/workspace/quic_explorer/LANFXplorer/test_transfer.txt"
    
    print(f"Testing file transfer to {host}:{port}")
    print(f"File: {test_file}")
    
    try:
        print("\n1. Connecting...")
        conn = await quic_connect(
            host=host,
            port=port,
            client_cert=client_cert,
            client_key=client_key,
            ca_cert=ca_cert
        )
        print("✓ Connected!")
        
        print("\n2. Authenticating...")
        result = await send_auth(conn, password)
        print(f"✓ Auth result: {result}")
        
        if not result:
            print("❌ Authentication failed!")
            await close_connection(conn)
            return
        
        print("\n3. Sending file...")
        await send_file(conn, test_file)
        print("✓ File sent!")
        
        print("\n4. Closing connection...")
        await close_connection(conn)
        print("✓ Done!")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
