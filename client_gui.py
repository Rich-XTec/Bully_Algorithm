import socket
import tkinter as tk
from tkinter import scrolledtext
import threading
import time

def enviar_requisicao():
    porta_inicial = porta_entry.get()
    if not porta_inicial:
        log_area.insert(tk.END, "[!] Digite uma porta válida.\n")
        return
    
    # Roda em uma thread separada para não travar a tela
    threading.Thread(target=processar_conexao, args=(int(porta_inicial),), daemon=True).start()

def processar_conexao(target_port):
    log_area.insert(tk.END, f"\n[*] Iniciando conexão na porta {target_port}...\n")
    log_area.see(tk.END)

    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3.0)
            s.connect(('127.0.0.1', target_port))
            s.sendall("SERVICE_REQUEST".encode('utf-8'))
            resp = s.recv(1024).decode('utf-8')
            s.close()
            
            if resp.startswith("SUCESSO"):
                log_area.insert(tk.END, f"[+] {resp}\n")
                break
            elif resp.startswith("NOT_LEADER"):
                partes = resp.split(":")
                leader_id, porta_lider = int(partes[1]), int(partes[2])
                
                log_area.insert(tk.END, f"[-] Nó não é o líder (Líder é o ID {leader_id}).\n")
                log_area.insert(tk.END, f"[*] Redirecionando para a porta {porta_lider}...\n")
                target_port = porta_lider
                time.sleep(1)
        except Exception as e:
            log_area.insert(tk.END, f"[!] Erro na porta {target_port}: {e}\n")
            break
    log_area.see(tk.END)

# Configuração da Janela
root = tk.Tk()
root.title("Cliente - Sistema Distribuído")
root.geometry("500x350")

tk.Label(root, text="Porta do Nó (Cliente):").pack(pady=5)
porta_entry = tk.Entry(root)
porta_entry.pack(pady=5)

tk.Button(root, text="Enviar Requisição", command=enviar_requisicao, bg="lightblue").pack(pady=10)

log_area = scrolledtext.ScrolledText(root, width=55, height=12)
log_area.pack(pady=10)

root.mainloop()