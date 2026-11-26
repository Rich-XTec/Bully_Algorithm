import sys
import time
import socket
import threading
import requests
from inspect import currentframe, getframeinfo

from network import setup_skt
from service import client_listener

debug_file = open('debug.txt', 'a')
output_file = open('output.txt', 'a')

def report_status(node_id, status, leader_id, internal_port, client_port, is_detector=False, event=None):
    payload = {
        'id': node_id,
        'status': status,
        'leader_id': leader_id,
        'internal_port': internal_port,
        'client_port': client_port,
        'is_detector': is_detector
    }
    if event:
        payload['event'] = event
    try:
        requests.post('http://127.0.0.1:5000/update', json=payload, timeout=0.5)
    except requests.RequestException:
        pass

def run_proc(priority, shared_vars, lock, is_detector):

    count = 0
    coordinator = True
    timeout = False
    
    num_connections = len(shared_vars['ip_addresses_ports']) - 1

    print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + '): priority ' + \
        str(priority) + ' has port ' + str(shared_vars['ip_addresses_ports'][priority][1]) + '\n', \
        end='', flush=True, file=debug_file)


    s_skt = setup_skt(('', shared_vars['ip_addresses_ports'][priority][1]), 's', num_connections, debug_file)
    
    print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + '): s_skt set by priority ' + \
        str(priority) + ' to ' + str(shared_vars['ip_addresses_ports'][priority][1]) + '\n', \
        end='', flush=True, file=debug_file)
    
    c_skts = {}
    lock.acquire()

    temp_shared_vars = shared_vars['lport_priority_links']
    for iterator in [iterator for iterator in range(1, len(shared_vars['ip_addresses_ports']) + 1) if iterator != priority]:
        c_skts[iterator] = setup_skt((shared_vars['ip_addresses_ports'][iterator][0], \
            shared_vars['ip_addresses_ports'][iterator][1]), 'c', shared_vars)
        temp_shared_vars.append(str(iterator) + ':' + str(c_skts[iterator].getsockname()[1]) + ':' + str(priority))
    shared_vars['lport_priority_links'] = temp_shared_vars
    lock.release()
    print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + '): c_skts set by priority ' + str(priority) + ' to ' + \
        str([shared_vars['ip_addresses_ports'][iterator][1] \
        for iterator in range(1, len(shared_vars['ip_addresses_ports']) + 1) if iterator != priority]) + '\n', \
        end='', flush=True, file=debug_file)
    new_skts = {}
    connection_accepts = []
    while len(shared_vars['lport_priority_links']) != len(shared_vars['ip_addresses_ports']) * \
        (len(shared_vars['ip_addresses_ports']) - 1):
        pass
    for _ in range(1, len(shared_vars['ip_addresses_ports'])):
        new_skt, addr = s_skt.accept()
        for value in shared_vars['lport_priority_links']:
            if str(priority) + ':' + str(addr[1]) in value:
                new_skts[int(value.strip().split(':')[2])] = new_skt
                connection_accepts.append(int(value.strip().split(':')[2]))
                break
    print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + '): connections accepted by priority ' + \
        str(priority) + ' from priorities ' + str(connection_accepts) + '\n', \
        end='', flush=True, file=debug_file)
    

    # -- INICIALIZA O SERVIÇO CLIENTE --
    # A porta do cliente será a porta interna + 10000 para não dar conflito
    client_port = shared_vars['ip_addresses_ports'][priority][1] + 10000
    
    # Inicia a thread que fica rodando em paralelo ao Bully
    t = threading.Thread(target=client_listener, args=(priority, shared_vars, client_port), daemon=True)
    t.start()

    print(f"[*] Processo do Nó ID {priority} rodando. Aguardando eventos...")

    internal_port = shared_vars['ip_addresses_ports'][priority][1]
    report_status(
        priority, "trabalhando", shared_vars['coordinator_id'],
        internal_port, client_port, is_detector=is_detector,
        event=f"Nó ID {priority} online (Porta Cliente: {client_port})"
    )

    # -- LOOP PRINCIPAL DO BULLY --
    while True:
        if shared_vars['coordinator_id'] == priority and coordinator:
            print('coordinator:' + str(priority) + '\n', end='', flush=True, file=output_file)
            coordinator = False

        report_status(
            priority, "trabalhando", shared_vars['coordinator_id'],
            internal_port, client_port, is_detector=is_detector
        )
        
        # work done by each process
        print('work:' + str(priority) + '\n', end='', flush=True, file=output_file)

        time.sleep(5)
        count += 1
        if is_detector:
            while not timeout:
                while True:
                    try:
                        c_skts[shared_vars['coordinator_id']].sendall(('heartbeat:' + str(priority)).encode('utf-8'))
                        print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + \
                            '): sent heartbeat message to priority ' + str(shared_vars['coordinator_id']) + \
                            ' by priority ' + str(priority) + '\n', end='', flush=True, file=debug_file)
                        new_skts[shared_vars['coordinator_id']].settimeout(10)
                        break
                    except ConnectionResetError:
                        pass
                try:
                    response = new_skts[shared_vars['coordinator_id']].recv(256).decode('ascii').strip().split(':')
                    new_skts[shared_vars['coordinator_id']].settimeout(None)
                    if response[0] != 'ack' or int(response[1]) != shared_vars['coordinator_id']:
                        print('ERROR lineno(' + str(getframeinfo(currentframe()).lineno) + \
                            '): got an invalid response or got a valid response but not from the coordinator\n', \
                            end='', flush=True, file=debug_file)
                        sys.exit(0)
                    print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + \
                        '): received ack message from priority ' + str(shared_vars['coordinator_id']) + \
                        ' by priority ' + str(priority) + '\n', end='', flush=True, file=debug_file)
                    report_status(
                        priority, "trabalhando", shared_vars['coordinator_id'],
                        internal_port, client_port, is_detector=True
                    )
                except socket.timeout:
                    new_skts[shared_vars['coordinator_id']].settimeout(None)
                    print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + \
                        '): did not receive ack message within time from priority ' + str(shared_vars['coordinator_id']) + \
                        ' by priority ' + str(priority) + '\n', end='', flush=True, file=debug_file)
                    timeout = True
                    if priority == len(shared_vars['ip_addresses_ports']) - 1:
                        lock.acquire()
                        shared_vars['coordinator_id'] = priority
                        lock.release()
                        report_status(
                            priority, "trabalhando", priority,
                            internal_port, client_port, is_detector=True,
                            event=f"Detector ID {priority} detectou falha do líder e assumiu como LÍDER"
                        )
                        for key in sorted(c_skts.keys())[:-1]:
                            # if key != len(shared_vars['ip_addresses_ports']):
                            while True:
                                try:
                                    c_skts[key].sendall(('coordinator:' + str(priority)).encode('utf-8'))
                                    print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + \
                                        '): sent coordinator message to priority ' + str(key) + \
                                        ' by priority ' + str(priority) + '\n', end='', flush=True, file=debug_file)
                                    break
                                except ConnectionResetError:
                                    pass
                    else:
                        lock.acquire()
                        shared_vars['coordinator_id'] = -1
                        lock.release()
                        report_status(
                            priority, "eleicao", -1,
                            internal_port, client_port, is_detector=True,
                            event=f"Detector ID {priority} detectou falha do líder e iniciou ELEIÇÃO"
                        )

                        # send an election msg to all priorities above and wait for their responses
                        # wait for an alive msg from at least one priority above it within some time
                        # wait for a coordinator msg within some time

                        num_alive = 0
                        for key in sorted(c_skts.keys())[priority - 1:-1]:
                            while True:
                                try:
                                    c_skts[key].sendall(('election:' + str(priority)).encode('utf-8'))
                                    print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + \
                                        '): sent election message to priority ' + str(key) + \
                                        ' by priority ' + str(priority) + '\n', end='', flush=True, file=debug_file)
                                    new_skts[key].settimeout(10)
                                    break
                                except ConnectionResetError:
                                    pass
                            try:
                                response = new_skts[key].recv(256).decode('ascii').strip().split(':')
                                new_skts[key].settimeout(None)
                                if response[0] != 'alive' or int(response[1]) != key:
                                    print('ERROR lineno(' + str(getframeinfo(currentframe()).lineno) + \
                                        '): got an invalid response or got a valid response but not from one of the required priorities\n', \
                                        end='', flush=True, file=debug_file)
                                    sys.exit(0)
                                print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + \
                                    '): received alive message from priority ' + str(key) + \
                                    ' by priority ' + str(priority) + '\n', end='', flush=True, file=debug_file)
                                num_alive += 1
                            except socket.timeout:
                                new_skts[key].settimeout(None)
                                print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + \
                                    '): did not receive alive message within time from priority ' + str(key) + \
                                    ' by priority ' + str(priority) + '\n', end='', flush=True, file=debug_file)
                        if num_alive > 0:
                            for key in sorted(c_skts.keys())[priority - 1:-1]:
                                try:
                                    new_skts[key].settimeout(10)
                                    response = new_skts[key].recv(256).decode('ascii').strip().split(':')
                                    new_skts[key].settimeout(None)
                                    if response[0] != 'coordinator' or int(response[1]) != key:
                                        print('ERROR lineno(' + str(getframeinfo(currentframe()).lineno) + \
                                            '): got an invalid response or got a valid response but not from one of the required priorities\n', \
                                            end='', flush=True, file=debug_file)
                                        sys.exit(0)
                                    print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + \
                                        '): received coordinator message from priority ' + str(key) + \
                                        ' by priority ' + str(priority) + '\n', end='', flush=True, file=debug_file)
                                    report_status(
                                        priority, "trabalhando", key,
                                        internal_port, client_port, is_detector=True,
                                        event=f"Nó ID {priority} reconheceu ID {key} como novo LÍDER"
                                    )
                                except socket.timeout:
                                    new_skts[key].settimeout(None)
                                    print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + \
                                        '): did not receive coordinator message within time from priority ' + str(key) + \
                                        ' by priority ' + str(priority) + '\n', end='', flush=True, file=debug_file)
                        else:
                            lock.acquire()
                            shared_vars['coordinator_id'] = priority
                            lock.release()
                            report_status(
                                priority, "trabalhando", priority,
                                internal_port, client_port, is_detector=True,
                                event=f"Detector ID {priority} venceu a eleição e assumiu como LÍDER"
                            )
                            for key in sorted(c_skts.keys())[:priority]:
                                while True:
                                    try:
                                        c_skts[key].sendall(('coordinator:' + str(priority)).encode('utf-8'))
                                        print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + \
                                            '): sent coordinator message to priority ' + str(key) + \
                                            ' by priority ' + str(priority) + '\n', end='', flush=True, file=debug_file)
                                        break
                                    except ConnectionResetError:
                                        pass
                        break
            if count == 15:

                # wait for a coordinator msg from the initial coordinator

                while shared_vars['coordinator_id'] != len(shared_vars['ip_addresses_ports']):
                    report_status(
                        priority, "trabalhando", shared_vars['coordinator_id'],
                        internal_port, client_port, is_detector=is_detector
                    )
                    time.sleep(2)
                response = new_skts[shared_vars['coordinator_id']].recv(256).decode('ascii').strip().split(':')
                if response[0] != 'coordinator' or int(response[1]) != shared_vars['coordinator_id']:
                    print('ERROR lineno(' + str(getframeinfo(currentframe()).lineno) + \
                        '): got an invalid response or got a valid response but not from the coordinator\n', \
                        end='', flush=True, file=debug_file)
                    sys.exit(0)
                print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + \
                    '): received coordinator message from priority ' + str(shared_vars['coordinator_id']) + \
                    ' by priority ' + str(priority) + '\n', end='', flush=True, file=debug_file)
            if count == 20:
                break
        elif priority != shared_vars['coordinator_id']:
            if count == 6:

                # wait for an election msg from the detector and send response (only processes with higher priorities need to wait)
                # then send an alive msg to the detector (only processes with higher priorities have to send)
                # process with current highest priority will then send a coordinator msg to all the processes
                # else wait for a coordinator msg in case the detector is the new coordinator (all processes need to wait)

                response = ''
                if priority > shared_vars['detector_id']:
                    try:
                        new_skts[shared_vars['detector_id']].settimeout(15)
                        response = new_skts[shared_vars['detector_id']].recv(256).decode('ascii').strip().split(':')
                        new_skts[shared_vars['detector_id']].settimeout(None)
                        if response[0] != 'election' and response[0] != 'coordinator' or \
                            int(response[1]) != shared_vars['detector_id']:
                            print('ERROR lineno(' + str(getframeinfo(currentframe()).lineno) + \
                                '): got an invalid response or got a valid response but not from the detector\n', \
                                end='', flush=True, file=debug_file)
                            sys.exit(0)
                        if response[0] == 'election':
                            print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + \
                                '): received election message from priority ' + str(shared_vars['detector_id']) + \
                                ' by priority ' + str(priority) + '\n', end='', flush=True, file=debug_file)
                        elif response[0] == 'coordinator':
                            # should also be able to use shared_vars['coordinator_id'] here
                            print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + \
                                '): received coordinator message from priority ' + str(shared_vars['detector_id']) + \
                                ' by priority ' + str(priority) + '\n', end='', flush=True, file=debug_file)
                    except socket.timeout:
                        new_skts[shared_vars['detector_id']].settimeout(None)
                        print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + \
                            '): did not receive election or coordinator message within time from priority ' + \
                            str(shared_vars['detector_id']) + ' by priority ' + str(priority) + '\n', \
                            end='', flush=True, file=debug_file)
                    # TODO here the process with current highest priority sends the coordinator msg to all the processes with lesser
                    # priority than itself after sending alive msg to the detector, though processes with higher priority than the
                    # detector just send the alive msg to the detector, after this they should again repeat the entire algo until
                    # they receive a coordinator msg from the highest priority process due to the initial election started by the
                    # detector
                    if response and response[0] == 'election':
                        report_status(
                            priority, "eleicao", -1,
                            internal_port, client_port, is_detector=False,
                            event=f"Nó ID {priority} recebeu ELEIÇÃO e enviou ALIVE"
                        )
                        while True:
                            try:
                                c_skts[shared_vars['detector_id']].sendall(('alive:' + str(priority)).encode('utf-8'))
                                print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + \
                                    '): sent alive message to priority ' + str(shared_vars['detector_id']) + \
                                    ' by priority ' + str(priority) + '\n', end='', flush=True, file=debug_file)
                                break
                            except ConnectionResetError:
                                pass
                        if priority == len(shared_vars['ip_addresses_ports']) - 1:
                            lock.acquire()
                            shared_vars['coordinator_id'] = priority
                            lock.release()
                            report_status(
                                priority, "trabalhando", priority,
                                internal_port, client_port, is_detector=False,
                                event=f"Nó ID {priority} venceu a eleição e assumiu como novo LÍDER"
                            )
                            for key in sorted(c_skts.keys())[:-1]:
                                while True:
                                    try:
                                        c_skts[key].sendall(('coordinator:' + str(priority)).encode('utf-8'))
                                        print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + \
                                            '): sent coordinator message to priority ' + str(key) + \
                                            ' by priority ' + str(priority) + '\n', end='', flush=True, file=debug_file)
                                        break
                                    except ConnectionResetError:
                                        pass
                else:
                    try:
                        new_skts[shared_vars['detector_id']].settimeout(15)
                        response = new_skts[shared_vars['detector_id']].recv(256).decode('ascii').strip().split(':')
                        new_skts[shared_vars['detector_id']].settimeout(None)
                        if response[0] != 'coordinator' or int(response[1]) != shared_vars['detector_id']:
                            print('ERROR lineno(' + str(getframeinfo(currentframe()).lineno) + \
                                '): got an invalid response or got a valid response but not from the detector\n', \
                                end='', flush=True, file=debug_file)
                            sys.exit(0)
                        elif response[0] == 'coordinator':
                            # should also be able to use shared_vars['coordinator_id'] here
                            print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + \
                                '): received coordinator message from priority ' + str(shared_vars['detector_id']) + \
                                ' by priority ' + str(priority) + '\n', end='', flush=True, file=debug_file)
                    except socket.timeout:
                        new_skts[shared_vars['detector_id']].settimeout(None)
                        print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + \
                            '): did not receive coordinator message within time from priority ' + str(shared_vars['detector_id']) + \
                            ' by priority ' + str(priority) + '\n', end='', flush=True, file=debug_file)
                    try:
                        new_skts[shared_vars['coordinator_id']].settimeout(15)
                        response = new_skts[shared_vars['coordinator_id']].recv(256).decode('ascii').strip().split(':')
                        new_skts[shared_vars['coordinator_id']].settimeout(None)
                        if response[0] != 'coordinator' or int(response[1]) != shared_vars['coordinator_id']:
                            print('ERROR lineno(' + str(getframeinfo(currentframe()).lineno) + \
                                '): got an invalid response or got a valid response but not from the coordinator\n', \
                                end='', flush=True, file=debug_file)
                            sys.exit(0)
                        elif response[0] == 'coordinator':
                            print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + \
                                '): received coordinator message from priority ' + str(shared_vars['coordinator_id']) + \
                                ' by priority ' + str(priority) + '\n', end='', flush=True, file=debug_file)
                    except socket.timeout:
                        new_skts[shared_vars['coordinator_id']].settimeout(None)
                        print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + \
                            '): did not receive coordinator message within time from priority ' + str(shared_vars['coordinator_id']) + \
                            ' by priority ' + str(priority) + '\n', end='', flush=True, file=debug_file)
            if count == 15:

                # wait for a coordinator msg from the initial coordinator

                while shared_vars['coordinator_id'] != len(shared_vars['ip_addresses_ports']):
                    report_status(
                        priority, "trabalhando", shared_vars['coordinator_id'],
                        internal_port, client_port, is_detector=is_detector
                    )
                    time.sleep(2)
                response = new_skts[shared_vars['coordinator_id']].recv(256).decode('ascii').strip().split(':')
                if response[0] != 'coordinator' or int(response[1]) != shared_vars['coordinator_id']:
                    print('ERROR lineno(' + str(getframeinfo(currentframe()).lineno) + \
                        '): got an invalid response or got a valid response but not from coordinator\n', \
                        end='', flush=True, file=debug_file)
                    sys.exit(0)
                print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + \
                    '): received coordinator message from priority ' + str(shared_vars['coordinator_id']) + \
                    ' by priority ' + str(priority) + '\n', end='', flush=True, file=debug_file)
            if count == 20:
                break
        if shared_vars['coordinator_id'] == priority and priority == len(shared_vars['ip_addresses_ports']) - 1:
            if count == 15:
                while shared_vars['coordinator_id'] != len(shared_vars['ip_addresses_ports']):
                    report_status(
                        priority, "trabalhando", shared_vars['coordinator_id'],
                        internal_port, client_port, is_detector=is_detector
                    )
                    time.sleep(2)
                response = new_skts[shared_vars['coordinator_id']].recv(256).decode('ascii').strip().split(':')
                if response[0] != 'coordinator' or int(response[1]) != shared_vars['coordinator_id']:
                    print('ERROR lineno(' + str(getframeinfo(currentframe()).lineno) + \
                        '): got an invalid response or got a valid response but not from coordinator\n', \
                        end='', flush=True, file=debug_file)
                    sys.exit(0)
                print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + \
                    '): received coordinator message from priority ' + str(shared_vars['coordinator_id']) + \
                    ' by priority ' + str(priority) + '\n', end='', flush=True, file=debug_file)
        if shared_vars['coordinator_id'] == priority and priority == len(shared_vars['ip_addresses_ports']):
            if count <= 5:
                request = new_skts[shared_vars['detector_id']].recv(256).decode('ascii').strip().split(':')
                if request[0] != 'heartbeat' or int(request[1]) != shared_vars['detector_id']:
                    print('ERROR lineno(' + str(getframeinfo(currentframe()).lineno) + \
                        '): got an invalid request or got a valid request but not from detector\n', \
                        end='', flush=True, file=debug_file)
                    sys.exit(0)
                print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + \
                    '): received heartbeat message from priority ' + str(shared_vars['detector_id']) + \
                    ' by priority ' + str(priority) + '\n', end='', flush=True, file=debug_file)
                while True:
                    try:
                        c_skts[shared_vars['detector_id']].sendall(('ack:' + str(priority)).encode('utf-8'))
                        print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + \
                            '): sent ack message to priority ' + str(shared_vars['detector_id']) + \
                            ' by priority ' + str(priority) + '\n', end='', flush=True, file=debug_file)
                        break
                    except ConnectionResetError:
                        pass
            if count == 6:
                print('failed:' + str(priority) + '\n', end='', flush=True, file=output_file)
                report_status(
                    priority, "falhou", -1,
                    internal_port, client_port, is_detector=False,
                    event=f"Líder inicial (ID {priority}) entrou em FALHA por 30s"
                )
                time.sleep(30)
                print('recovered:' + str(priority) + '\n', end='', flush=True, file=output_file)
                lock.acquire()
                shared_vars['coordinator_id'] = priority
                lock.release()
                coordinator = True
                report_status(
                    priority, "trabalhando", priority,
                    internal_port, client_port, is_detector=False,
                    event=f"Nó ID {priority} RECUPERADO e reassumiu como LÍDER"
                )
                for key in sorted(c_skts.keys()):
                    while True:
                        try:
                            c_skts[key].sendall(('coordinator:' + str(priority)).encode('utf-8'))
                            print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + \
                                '): sent coordinator message to priority ' + str(key) + \
                                ' by priority ' + str(priority) + '\n', end='', flush=True, file=debug_file)
                            break
                        except ConnectionResetError:
                            pass
            if count == 20:
                break