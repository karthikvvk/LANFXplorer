import socket

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("0.0.0.0", 9001))

while True:
    data, addr = sock.recvfrom(65535)
    sock.sendto(data, addr)
