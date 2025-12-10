import socket, time

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(1)

loss = 0
out_of_order = 0
last_seq = -1

for seq in range(1000):
    pkt = str(seq).encode()
    sock.sendto(pkt, ("SERVER_IP", 9001))
    try:
        data, _ = sock.recvfrom(65535)
        r = int(data.decode())

        if r != seq:
            out_of_order += 1
        if r < last_seq:
            out_of_order += 1
        
        last_seq = r
    except:
        loss += 1

print("LOSS:", loss, "OFO:", out_of_order)
