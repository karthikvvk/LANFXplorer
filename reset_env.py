import os

def reset_environment():
    # 1. Delete Certificate Files
    files_to_delete = [
        'cert.pem',
        'key.pem',
        'ca_cert.pem',
        'ca_key.pem'
    ]
    
    print("Deleting certificate files...")
    for file_name in files_to_delete:
        if os.path.exists(file_name):
            try:
                os.remove(file_name)
                print(f"Deleted: {file_name}")
            except OSError as e:
                print(f"Error deleting {file_name}: {e}")
        else:
            print(f"Not found: {file_name}")

    # 2. Modify .env config
    env_file = '.env'
    keys_to_reset = [
        'HOST',
        'SUBNET',
        'CIDR',
        'GATEWAY',
        'BROADCAST',
        'INTERFACE',
        'RECIVHOST',
        'USER',
        'PASSWORD',
        'DEST_HOST',
    ]

    print("\nModifying .env configs...")
    if os.path.exists(env_file):
        try:
            with open(env_file, 'r') as f:
                lines = f.readlines()

            new_lines = []
            for line in lines:
                key_match = False
                for key in keys_to_reset:
                    if line.startswith(f"{key}="):
                        new_lines.append(f"{key}=''\n")
                        print(f"Reset {key}")
                        key_match = True
                        break
                
                if not key_match:
                    new_lines.append(line)

            with open(env_file, 'w') as f:
                f.writelines(new_lines)
            print("Finished modifying .env")

        except Exception as e:
            print(f"Error modifying .env: {e}")
    else:
        print(f"{env_file} not found.")

if __name__ == "__main__":
    reset_environment()
