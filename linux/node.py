import sys
import time
import socket
import threading
import requests # Dashboard
from inspect import currentframe, getframeinfo

from network import setup_skt
from service import client_listener


def run_proc(priority, shared_vars, lock, is_detector):
    internal_port = shared_vars['ip_addresses_ports'][priority][1]
    client_port = internal_port + 10000

    # --- FUNÇÃO DE TELEMETRIA PARA O DASHBOARD ---
    def notificar_painel(status, event=None):
        lider_atual = shared_vars['coordinator_id']
        payload = {
            "id": priority,
            "status": status,
            "leader_id": lider_atual,
            "internal_port": internal_port,
            "client_port": client_port,
            "is_detector": is_detector
        }
        if event:
            payload["event"] = event

        def enviar():
            try:
                requests.post('http://127.0.0.1:5000/update', json=payload, timeout=0.5)
            except requests.RequestException:
                pass

        threading.Thread(target=enviar, daemon=True).start()
    # ---------------------------------------------

    # Arquivos de log precisam ser abertos no processo para não dar conflito
    debug_file = open('debug.txt', 'a')
    output_file = open('output.txt', 'a')

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
    # Inicia a thread que fica rodando em paralelo ao Bully
    t = threading.Thread(target=client_listener, args=(priority, shared_vars, client_port), daemon=True)
    t.start()

    print(f"[*] Processo do Nó ID {priority} rodando. Aguardando eventos...")
    notificar_painel('trabalhando', event=f"Nó ID {priority} online (Porta Cliente: {client_port})")

    # -- LOOP PRINCIPAL DO BULLY --
    while True:
        if shared_vars['coordinator_id'] == priority and coordinator:
            print('coordinator:' + str(priority) + '\n', end='', flush=True, file=output_file)
            coordinator = False

        # trabalho realizado por cada processo
        print('work:' + str(priority) + '\n', end='', flush=True, file=output_file)

        notificar_painel('trabalhando')

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
                    notificar_painel('trabalhando')
                except socket.timeout:
                    new_skts[shared_vars['coordinator_id']].settimeout(None)
                    print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + \
                        '): did not receive ack message within time from priority ' + str(shared_vars['coordinator_id']) + \
                        ' by priority ' + str(priority) + '\n', end='', flush=True, file=debug_file)
                    timeout = True
                    notificar_painel('eleicao', event=f"Detector ID {priority} detectou falha do líder e iniciou ELEIÇÃO")

                    time.sleep(3)

                    if priority == len(shared_vars['ip_addresses_ports']) - 1:
                        lock.acquire()
                        shared_vars['coordinator_id'] = priority
                        lock.release()
                        notificar_painel('trabalhando', event=f"Detector ID {priority} assumiu diretamente como LÍDER")
                        time.sleep(2)

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
                        time.sleep(2)

                        # envia uma mensagem de eleição para todas as prioridades acima e aguarda suas respostas
                        # aguarda uma mensagem alive de pelo menos uma prioridade acima dela dentro de um determinado período
                        # aguarda uma mensagem de coordenador dentro de um determinado período

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
                                    notificar_painel('trabalhando', event=f"Nó ID {priority} reconheceu ID {key} como novo LÍDER")
                                except socket.timeout:
                                    new_skts[key].settimeout(None)
                                    print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + \
                                        '): did not receive coordinator message within time from priority ' + str(key) + \
                                        ' by priority ' + str(priority) + '\n', end='', flush=True, file=debug_file)
                        else:
                            lock.acquire()
                            shared_vars['coordinator_id'] = priority
                            lock.release()
                            notificar_painel('trabalhando', event=f"Detector ID {priority} venceu a eleição e assumiu como LÍDER")

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

                # aguarda uma mensagem de coordenador do coordenador inicial

                while shared_vars['coordinator_id'] != len(shared_vars['ip_addresses_ports']):
                    notificar_painel('trabalhando')
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

                # aguarda uma mensagem de eleição do detector e envia uma resposta (somente processos com prioridades maiores precisam aguardar)
                # em seguida, envia uma mensagem alive ao detector (somente processos com prioridades maiores precisam enviar)
                # o processo com a maior prioridade atual enviará uma mensagem de coordenador a todos os processos
                # caso contrário, aguarda uma mensagem de coordenador se o detector for o novo coordenador (todos os processos precisam aguardar)

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
                            notificar_painel('eleicao', event=f"Nó ID {priority} recebeu ELEIÇÃO e enviou ALIVE")
                            time.sleep(3)

                        elif response[0] == 'coordinator':
                            # também deveria ser possível usar shared_vars['coordinator_id'] aqui
                            print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + \
                                '): received coordinator message from priority ' + str(shared_vars['detector_id']) + \
                                ' by priority ' + str(priority) + '\n', end='', flush=True, file=debug_file)
                    except socket.timeout:
                        new_skts[shared_vars['detector_id']].settimeout(None)
                        print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + \
                            '): did not receive election or coordinator message within time from priority ' + \
                            str(shared_vars['detector_id']) + ' by priority ' + str(priority) + '\n', \
                            end='', flush=True, file=debug_file)
                    # TODO: aqui, o processo com a maior prioridade atual envia uma mensagem de coordenador a todos os processos
                    # com prioridade menor que a sua após enviar uma mensagem alive ao detector. Porém, os processos com prioridade
                    # maior que a do detector apenas enviam a mensagem alive ao detector; depois disso, devem repetir todo o
                    # algoritmo até receberem uma mensagem de coordenador do processo com a maior prioridade, devido à eleição
                    # inicial iniciada pelo detector.
                    if response and response[0] == 'election':
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
                            notificar_painel('trabalhando', event=f"Nó ID {priority} venceu a eleição e assumiu como novo LÍDER")
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
                            # também deveria ser possível usar shared_vars['coordinator_id'] aqui
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
                        new_skts[shared_vars['detector_id']].settimeout(None)
                        print('DEBUG lineno(' + str(getframeinfo(currentframe()).lineno) + \
                            '): did not receive coordinator message within time from priority ' + str(shared_vars['coordinator_id']) + \
                            ' by priority ' + str(priority) + '\n', end='', flush=True, file=debug_file)
            if count == 15:

                # aguarda uma mensagem de coordenador do coordenador inicial

                while shared_vars['coordinator_id'] != len(shared_vars['ip_addresses_ports']):
                    notificar_painel('trabalhando')
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
                    notificar_painel('trabalhando')
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
                notificar_painel('falhou', event=f"Líder inicial (ID {priority}) entrou em FALHA por 120s")

                time.sleep(120)

                print('recovered:' + str(priority) + '\n', end='', flush=True, file=output_file)
                lock.acquire()
                shared_vars['coordinator_id'] = priority
                lock.release()
                coordinator = True
                notificar_painel('trabalhando', event=f"Nó ID {priority} RECUPERADO e reassumiu como LÍDER")
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

