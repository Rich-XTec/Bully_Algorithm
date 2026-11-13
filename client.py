import socket
import time

def request_service():
    print("--- Cliente Iniciado ---")
    # Como o nosso servidor usa portas aleatórias baseadas em um range, 
    # vamos pedir pro usuário digitar a porta de acesso de qualquer nó para iniciar.
    # Exemplo: Se no output do servidor a porta do nó 1 for 19123, a porta do cliente será 29123 (porta + 10000)
    
    start_port = int(input("Digite a porta cliente de um dos nós (ex: se o servidor iniciou na base 9000, digite algo como 19001): "))
    target_port = start_port

    while True:
        try:
            print(f"[*] Conectando à porta {target_port}...")
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3.0)
            s.connect(('127.0.0.1', target_port))
            
            # Envia a requisição do serviço
            s.sendall("SERVICE_REQUEST".encode('utf-8'))
            
            # Aguarda a resposta
            resp = s.recv(1024).decode('utf-8')
            s.close()
            
            if resp.startswith("SUCESSO"):
                print(f"\n[+] Resposta do Servidor: {resp}\n")
                break
            elif resp.startswith("NOT_LEADER"):
                partes = resp.split(":")
                leader_id = int(partes[1])
                porta_lider = int(partes[2]) # Lê a porta exata enviada pelo servidor
                
                print(f"[-] O nó conectado não é o líder. O líder atual é o ID {leader_id}.")
                print(f"[*] Redirecionando para o líder na porta {porta_lider}.")
                
                # Atualiza a porta alvo com a informação exata recebida
                target_port = porta_lider
                time.sleep(1)
                
        except ConnectionRefusedError:
            print(f"[!] Erro: Conexão recusada na porta {target_port}. O nó pode estar morto.")
            # Tenta pular para a próxima porta para tentar achar alguém vivo
            target_port = target_port - (target_port % 10) + ((target_port % 10) % 5) + 1
            time.sleep(1)
        except socket.timeout:
            print(f"[!] Erro: Timeout na porta {target_port}.")
            break

if __name__ == '__main__':
    request_service()