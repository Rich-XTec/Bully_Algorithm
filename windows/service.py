import socket
import datetime

def client_listener(priority, shared_vars, client_port):
        # Cria um socket para escutar apenas os clientes
        c_skt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        c_skt.bind(('', client_port))
        c_skt.listen(5)
        
        while True:
            try:
                conn, addr = c_skt.accept()
                req = conn.recv(1024).decode('utf-8')
                
                if req == "SERVICE_REQUEST":
                    # Verifica se este processo é o Coordenador atual
                    if shared_vars['coordinator_id'] == priority:
                        # O SERVIÇO: Retornar a data/hora e confirmar quem processou
                        agora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        resposta = f"SUCESSO: Serviço processado pelo Líder (ID: {priority}) as {agora}"
                        conn.sendall(resposta.encode('utf-8'))
                    else:
                        lider_atual = shared_vars['coordinator_id']
                        # Pega a porta interna do líder e soma 10000 para achar a porta de cliente dele
                        porta_lider = shared_vars['ip_addresses_ports'][lider_atual][1] + 10000
                    
                        # Agora envia o ID e a PORTA do líder
                        resposta = f"NOT_LEADER:{lider_atual}:{porta_lider}"
                        conn.sendall(resposta.encode('utf-8'))
                conn.close()
            except Exception:
                pass