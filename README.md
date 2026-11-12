# Trabalho Prático de Sistemas Distribuídos: Algoritmo de Bully e Cliente-Servidor

## 1. Proposta do Trabalho
Este trabalho consiste na implementação de um sistema distribuído baseado na arquitetura **Cliente-Servidor**, utilizando o **Algoritmo de Bully** para **Eleição de Líder**. 
O sistema é composto por múltiplos processos servidores (nós) e um cliente. O cliente envia requisições de serviço para o sistema. Caso o servidor líder (coordenador) falhe, os nós restantes detectam a falha e iniciam o algoritmo de Bully para eleger um novo líder com base no maior número de identificação (ID) de processo, garantindo a disponibilidade do serviço.

## 2. Requisitos Funcionais

*   **Identificação dos Processos:** Cada servidor rodando na máquina recebe um ID único (ex: 1, 2, 3, 4, 5) e uma porta TCP correspondente (ex: 5001, 5002, etc.). O nó com o maior ID sempre será o líder natural.
*   **Servidor:** 
    *   Deve escutar conexões de clientes e de outros servidores.
    *   Deve responder a mensagens de eleição (`ELECTION`), responder que está vivo (`ALIVE`) e declarar vitória (`COORDINATOR`).
    *   O servidor que atua como líder processa a requisição do cliente.
*   **Cliente:**
    *   O tipo de requisição enviada é uma string de comando (ex: `GET_TIME` ou `STATUS`).
    *   Se o cliente tentar se conectar a um servidor que caiu, ele tenta o próximo até encontrar o novo líder.

## 3. Comunicação entre Cliente e Servidor
A comunicação é feita via **Sockets TCP**, garantindo a entrega confiável das mensagens. As mensagens trafegadas são strings codificadas em UTF-8. 
Quando o cliente faz uma requisição, ele abre uma conexão socket com o líder, envia o comando, aguarda o processamento, recebe a resposta e encerra a conexão.


## Como testar tudo junto:

### Abra um terminal e inicie os servidores (nós) do projeto original:

Bash
python3 bully.py -numproc 5 -detectproc 2

(Observe o arquivo debug.txt gerado. Lá vai aparecer as portas que ele escolheu, por exemplo: priority 1 has port 9561. Isso significa que a porta de cliente do nó 1 será 19561).

Abra um SEGUNDO terminal na mesma pasta.

Rode o cliente:

Bash
python3 client.py

Ele vai pedir uma porta. Digite a porta cliente de um dos nós que NÃO é o líder (ex: o líder é o 5, então digite a porta cliente correspondente ao ID 1 ou 2).

Você verá a mágica acontecer: O nó vai recusar o processamento, avisar o cliente que o líder é o ID 5, o cliente vai redirecionar a conexão automaticamente para a porta do ID 5 e receberá a hora do sistema processada pelo Líder!


### Diagrama de Sequência (Eleição e Requisição)
*O GitHub renderiza o código Mermaid abaixo automaticamente como uma imagem no repositório.*

```mermaid
sequenceDiagram
    participant C as Cliente
    participant S1 as Servidor (ID 1)
    participant S2 as Servidor (ID 2)
    participant S3 as Servidor (ID 3 - Líder Morto)

    Note over S1, S3: S3 era o líder, mas caiu.
    S1->>S2: Envia ELECTION (ID 1)
    S1->>S3: Envia ELECTION (ID 1)
    Note over S3: Sem resposta (Timeout)
    S2->>S1: Responde ALIVE (ID 2 é maior)
    S2->>S3: Envia ELECTION (ID 2)
    Note over S3: Sem resposta (Timeout)
    S2->>S1: Envia COORDINATOR (S2 agora é o líder)
    
    Note over C: Cliente faz requisição ao novo líder
    C->>S2: Conecta e envia "GET_TIME"
    S2->>C: Responde "14:30:00"



4. Descrição do Serviço e Execução
O serviço implementado é um simples "Servidor de Hora/Status". O líder eleito é o único autorizado a responder às requisições do cliente.

Como executar o projeto localmente (em terminais separados):

Inicie o servidor 1: python server.py --id 1 --port 5001

Inicie o servidor 2: python server.py --id 2 --port 5002

Inicie o servidor 3 (Líder inicial): python server.py --id 3 --port 5003

Inicie o cliente: python client.py

Derrube o servidor 3 (Ctrl+C) para observar o Algoritmo de Bully acontecendo entre 1 e 2.

5. Trechos de Código Relevantes
Conforme exigido, abaixo estão os blocos de código demonstrando os principais conceitos de comunicação em rede utilizando Python socket.

Definição da Identificação do Processo:

Python
# A identificação do processo é passada via argumento de linha de comando
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--id', type=int, required=True, help="ID único do processo")
parser.add_argument('--port', type=int, required=True, help="Porta TCP do servidor")
args = parser.parse_args()

MEU_ID = args.id
MINHA_PORTA = args.port
Recepção de Mensagens no Servidor (Escuta):

Python
import socket

def iniciar_servidor():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(('localhost', MINHA_PORTA))
    server_socket.listen(5)
    print(f"Servidor [ID: {MEU_ID}] escutando na porta {MINHA_PORTA}...")

    while True:
        client_conn, addr = server_socket.accept()
        mensagem_recebida = client_conn.recv(1024).decode('utf-8')
        
        if mensagem_recebida == "ELECTION":
            # Lógica do Bully...
            client_conn.sendall("ALIVE".encode('utf-8'))
        elif mensagem_recebida == "GET_TIME":
            # Lógica de serviço para o cliente
            client_conn.sendall("Serviço processado pelo Líder!".encode('utf-8'))
        
        client_conn.close()
Envio de Mensagens (Comunicação Cliente -> Servidor ou Servidor -> Servidor):

Python
def enviar_mensagem(porta_destino, mensagem):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.0) # Timeout para detectar se o nó caiu
        s.connect(('localhost', porta_destino))
        s.sendall(mensagem.encode('utf-8'))
        
        resposta = s.recv(1024).decode('utf-8')
        s.close()
        return resposta
    except (socket.timeout, ConnectionRefusedError):
        return None # Indica que o processo na porta_destino está morto