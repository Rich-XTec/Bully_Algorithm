import argparse
import random
import sys
from multiprocessing import Process, Manager
from node import run_proc

def setup_argument_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('--num-of-processes', '-numproc', type=int, required=True, \
        help='pass the required number of processes')
    parser.add_argument('--detector-process', '-detectproc', type=int, required=True, \
        help='pass the process ID/priority which will detect initial coordinator failure')
    return parser.parse_args()


if __name__ == '__main__':

    debug_file = open('debug.txt', 'w')
    output_file = open('output.txt', 'w')

    # setting up input of command line arguments
    args = setup_argument_parser()
    num_of_processes = args.num_of_processes
    detector_process = args.detector_process
    if num_of_processes <= 2:
        print('ERROR: Number of processes must be greater than 2\n', \
            end='', flush=True, file=debug_file)
        sys.exit(0)
    if detector_process == num_of_processes:
        print('ERROR: The detector process cannot be the initial coordinator\n', \
            end='', flush=True, file=debug_file)
        sys.exit(0)
    elif detector_process <= 0:
        print('ERROR: The detector process cannot have ID/priority less than or equal to 0\n', \
            end='', flush=True, file=debug_file)
        sys.exit(0)
    elif detector_process > num_of_processes:
        print('ERROR: The detector process cannot have ID/priority greater than the number of processes\n', \
            end='', flush=True, file=debug_file)
        sys.exit(0)

    # initializing ip address and port for all processes (localhost is used for all processes)
    base_port = random.randrange(9000, 20000, num_of_processes + 1)
    ip_addresses_ports = {}
    for iterator in range(1, num_of_processes + 1):
        ip_addresses_ports[iterator] = ('127.0.0.1', base_port + iterator)

    print("\n" + "="*55)
    print("INICIALIZANDO SERVIDORES (ALGORITMO DE BULLY)")
    print("="*55)
    for p_id, (ip, port) in ip_addresses_ports.items():
        porta_cliente = port + 10000
        print(f"Nó ID {p_id} | Porta Interna: {port} | Porta CLIENTE: {porta_cliente}")
    print("="*55 + "\n")

    manager = Manager()
    lock = manager.Lock()
    shared_vars = manager.dict()
    jobs = []

    # setting variables to be shared among all processes
    shared_vars['ip_addresses_ports'] = ip_addresses_ports
    shared_vars['coordinator_id'] = num_of_processes
    shared_vars['detector_id'] = detector_process
    shared_vars['lport_priority_links'] = []

    # process id is the same as process priority
    for process_id in range(num_of_processes, 0, -1):
        if process_id == detector_process:
            process = Process(target=run_proc, args=(process_id, shared_vars, lock, True))
        else:
            process = Process(target=run_proc, args=(process_id, shared_vars, lock, False))
        jobs.append(process)
        process.start()
    for process in jobs:
        process.join()

    debug_file.close()
    output_file.close()