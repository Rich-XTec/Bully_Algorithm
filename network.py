import socket
import sys

def connect_skt(skt, ip_address_and_port):
    while True:
        try:
            skt.connect(ip_address_and_port)
            break
        except ConnectionRefusedError:
            pass

def bind_and_listen_skt(skt, ip_address_and_port, max_num_connections):
    skt.bind(ip_address_and_port)
    skt.listen(max_num_connections)

def setup_skt(ip_address_and_port, mode, num_connections=5, debug_file=None):
    skt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if mode == 's':
        bind_and_listen_skt(skt, ip_address_and_port, num_connections)
    elif mode == 'c':
        connect_skt(skt, ip_address_and_port)
    else:
        print('ERROR: Correct mode not provided while calling setup_skt(), should be s/c\n', \
            end='', flush=True, file=debug_file)
        sys.exit(0)
    return skt