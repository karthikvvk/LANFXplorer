import os

for i in range(255):
    os.system(f"ping -c 1 -W 1 10.186.74.{i}")