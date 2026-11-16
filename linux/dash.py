from flask import Flask, request, jsonify, render_template_string
import time

app = Flask(__name__)

# Dicionário que guarda o estado de cada nó em tempo real
nodes_state = {}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt">
<head>
    <meta charset="UTF-8">
    <title>Painel do Sistema Distribuído (Bully)</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #1e1e2e; color: white; text-align: center; }
        h1 { margin-top: 30px; color: #cdd6f4; }
        .container { display: flex; justify-content: center; gap: 20px; flex-wrap: wrap; margin-top: 40px; padding: 20px; }
        .node { padding: 20px; border-radius: 12px; width: 180px; background-color: #313244; box-shadow: 0 4px 15px rgba(0,0,0,0.3); transition: 0.3s; }
        .node h2 { margin: 0 0 10px 0; font-size: 24px; }
        .node p { margin: 5px 0; font-size: 14px; color: #bac2de; }
        
        /* Cores de Status */
        .leader { background-color: #a6e3a1; color: #11111b; border: 4px solid #f9e2af; transform: scale(1.05); }
        .leader p { color: #11111b; font-weight: bold; }
        .dead { background-color: #f38ba8; opacity: 0.7; color: #11111b; }
        .dead p { color: #11111b; }
        .election { background-color: #fab387; color: #11111b; animation: pulse 1s infinite; }
        
        @keyframes pulse { 0% { transform: scale(1); } 50% { transform: scale(1.05); } 100% { transform: scale(1); } }
    </style>
</head>
<body>
    <h1>Painel de Eleição - Algoritmo de Bully</h1>
    <div class="container" id="nodes-container">
        <!-- Os nós serão renderizados aqui via JavaScript -->
    </div>

    <script>
        async function fetchStatus() {
            try {
                const response = await fetch('/status');
                const data = await response.json();
                const container = document.getElementById('nodes-container');
                container.innerHTML = ''; // Limpa a tela

                // Ordena os nós pelo ID decrescente
                const sortedIds = Object.keys(data).sort((a, b) => b - a);

                sortedIds.forEach(id => {
                    const node = data[id];
                    let cssClass = 'node';
                    
                    if (node.status === 'falhou') {
                        cssClass += ' dead';
                    } else if (node.status === 'eleicao') {
                        cssClass += ' election';
                    } else if (parseInt(id) === node.leader_id) {
                        cssClass += ' leader';
                    }

                    const status_text = node.status === 'trabalhando' ? 'Online' : node.status.toUpperCase();

                    const html = `
                        <div class="${cssClass}">
                            <h2>Nó ID ${id}</h2>
                            <p>Status: <strong>${status_text}</strong></p>
                            <p>Líder Atual: ID ${node.leader_id === -1 ? '?' : node.leader_id}</p>
                        </div>
                    `;
                    container.innerHTML += html;
                });
            } catch (error) {
                console.error('Erro ao buscar status:', error);
            }
        }

        // Atualiza a tela a cada 1 segundo
        setInterval(fetchStatus, 1000);
        fetchStatus();
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/update', methods=['POST'])
def update():
    # Recebe os dados de telemetria enviados pelos nós
    data = request.json
    node_id = str(data['id'])
    nodes_state[node_id] = {
        'status': data['status'],
        'leader_id': data['leader_id'],
        'last_seen': time.time()
    }
    return jsonify({"success": True})

@app.route('/status', methods=['GET'])
def status():
    # Marca como morto se não mandar sinal por mais de 10 segundos
    now = time.time()
    for nid, info in nodes_state.items():
        if info['status'] != 'falhou' and (now - info['last_seen'] > 10):
            info['status'] = 'falhou'
    return jsonify(nodes_state)

if __name__ == '__main__':
    # Roda o servidor web na porta 5000
    app.run(port=5000, debug=True, use_reloader=False)