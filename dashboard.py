from flask import Flask, request, jsonify, render_template_string
import time
import subprocess
import os

app = Flask(__name__)

nodes_state = {}
# Variável para guardar o processo do terminal que o Flask vai abrir
server_process = None 

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt">
<head>
    <meta charset="UTF-8">
    <title>Painel do Sistema Distribuído (Bully)</title>
    <style>
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            background-color: #11111b; 
            color: white; 
            text-align: center; 
            margin: 0;
            overflow: hidden; 
        }
        h1 { position: absolute; width: 100%; top: 20px; color: #cdd6f4; z-index: 100; text-shadow: 0 0 10px rgba(255,255,255,0.2); pointer-events: none;}
        
        /* NOVO: Painel de Controle de Inicialização */
        #control-panel {
            position: absolute;
            top: 20px;
            left: 20px;
            background-color: #1e1e2e;
            padding: 20px;
            border-radius: 12px;
            border: 1px solid #313244;
            box-shadow: 0 4px 15px rgba(0,0,0,0.5);
            z-index: 200;
            text-align: left;
            width: 220px;
        }
        #control-panel h3 { margin-top: 0; color: #cdd6f4; font-size: 16px; margin-bottom: 15px; }
        .input-group { margin-bottom: 10px; }
        .input-group label { display: block; font-size: 12px; color: #bac2de; margin-bottom: 5px; }
        .input-group input { width: 90%; padding: 8px; border-radius: 6px; border: none; background: #313244; color: white; outline: none; }
        button { 
            width: 100%; padding: 10px; border-radius: 6px; border: none; 
            background-color: #89b4fa; color: #11111b; font-weight: bold; 
            cursor: pointer; transition: 0.2s; margin-top: 10px;
        }
        button:hover { background-color: #74c7ec; }
        button:disabled { background-color: #45475a; color: #bac2de; cursor: not-allowed; }

        #dashboard-area {
            position: relative; width: 100vw; height: 100vh;
            display: flex; justify-content: center; align-items: center;
        }
        #connections { position: absolute; top: 0; left: 0; width: 100%; height: 100%; z-index: 1; pointer-events: none; }
        .line-heartbeat { stroke: rgba(255, 255, 255, 0.15); stroke-width: 2; stroke-dasharray: 8, 8; animation: dash 15s linear infinite; }
        .line-election { stroke: rgba(250, 179, 135, 0.4); stroke-width: 3; stroke-dasharray: 15, 5; animation: dash 5s linear infinite reverse; }
        @keyframes dash { to { stroke-dashoffset: 1000; } }

        #nodes-container { position: absolute; top: 0; left: 0; width: 100%; height: 100%; z-index: 10; }
        .node { 
            position: absolute; padding: 15px; border-radius: 50%; 
            width: 110px; height: 110px; display: flex; flex-direction: column; justify-content: center; align-items: center;
            background-color: #313244; box-shadow: 0 0 20px rgba(0,0,0,0.5); 
            transition: all 0.5s ease-out; transform: translate(-50%, -50%); 
        }
        .node h2 { margin: 0 0 5px 0; font-size: 20px; text-shadow: 0 2px 4px rgba(0,0,0,0.5);}
        .node p { margin: 2px 0; font-size: 12px; color: #bac2de; }
        
        .leader { 
            background-color: #a6e3a1; color: #11111b; border: 4px solid #f9e2af; 
            box-shadow: 0 0 30px rgba(166, 227, 161, 0.6); transform: translate(-50%, -50%) scale(1.15); z-index: 20;
        }
        .leader p, .leader h2 { color: #11111b; font-weight: bold; text-shadow: none;}
        .dead { background-color: #45475a; border: 2px solid #f38ba8; opacity: 0.5; color: #f38ba8; box-shadow: none; }
        .dead p, .dead h2 { color: #f38ba8; }
        .election { 
            background-color: #fab387; color: #11111b; box-shadow: 0 0 30px rgba(250, 179, 135, 0.8); animation: pulse 1s infinite; 
        }
        .election p, .election h2 { color: #11111b; text-shadow: none;}
        @keyframes pulse { 0% { transform: translate(-50%, -50%) scale(1); } 50% { transform: translate(-50%, -50%) scale(1.1); } 100% { transform: translate(-50%, -50%) scale(1); } }
    </style>
</head>
<body>
    <h1>Topologia da Rede - Algoritmo de Bully</h1>
    
    <!-- Painel Lateral -->
    <div id="control-panel">
        <h3>Controle do Cluster</h3>
        <div class="input-group">
            <label>Número de Nós (-numproc)</label>
            <input type="number" id="numproc" value="5" min="3" max="15">
        </div>
        <div class="input-group">
            <label>ID do Detector (-detectproc)</label>
            <input type="number" id="detectproc" value="2" min="1" max="15">
        </div>
        <button id="start-btn" onclick="startCluster()">Ligar Servidores</button>
        <button id="stop-btn" onclick="stopCluster()" style="background-color: #f38ba8; display: none;">Desligar Servidores</button>
    </div>

    <div id="dashboard-area">
        <svg id="connections"></svg>
        <div id="nodes-container"></div>
    </div>

    <script>
        async function startCluster() {
            const numproc = document.getElementById('numproc').value;
            const detectproc = document.getElementById('detectproc').value;
            
            document.getElementById('start-btn').innerText = 'Iniciando...';
            document.getElementById('start-btn').disabled = true;

            const response = await fetch('/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ numproc: parseInt(numproc), detectproc: parseInt(detectproc) })
            });
            const data = await response.json();
            
            if (data.status === 'started' || data.status === 'already_running') {
                document.getElementById('start-btn').style.display = 'none';
                document.getElementById('stop-btn').style.display = 'block';
            }
        }

        async function stopCluster() {
            await fetch('/stop', { method: 'POST' });
            document.getElementById('stop-btn').style.display = 'none';
            const startBtn = document.getElementById('start-btn');
            startBtn.style.display = 'block';
            startBtn.disabled = false;
            startBtn.innerText = 'Ligar Servidores';
            document.getElementById('nodes-container').innerHTML = '';
            document.getElementById('connections').innerHTML = '';
        }

        async function fetchStatus() {
            try {
                const response = await fetch('/status');
                const data = await response.json();
                
                const container = document.getElementById('nodes-container');
                const svg = document.getElementById('connections');
                
                let nodesHtml = '';
                let svgHtml = '';

                const sortedIds = Object.keys(data).sort((a, b) => a - b);
                const numNodes = sortedIds.length;

                const centerX = window.innerWidth / 2;
                const centerY = window.innerHeight / 2;
                const radius = Math.min(centerX, centerY) * 0.65;

                const positions = {}; 

                sortedIds.forEach((id, index) => {
                    const node = data[id];
                    const angle = (index / numNodes) * (2 * Math.PI) - (Math.PI / 2);
                    const x = centerX + radius * Math.cos(angle);
                    const y = centerY + radius * Math.sin(angle);
                    
                    positions[id] = { x, y };

                    let cssClass = 'node';
                    if (node.status === 'falhou') {
                        cssClass += ' dead';
                    } else if (node.status === 'eleicao') {
                        cssClass += ' election';
                    } else if (parseInt(id) === node.leader_id) {
                        cssClass += ' leader';
                    }

                    const status_text = node.status === 'trabalhando' ? 'Online' : node.status.toUpperCase();

                    nodesHtml += `
                        <div class="${cssClass}" style="left: ${x}px; top: ${y}px;">
                            <h2>ID ${id}</h2>
                            <p>${status_text}</p>
                            ${parseInt(id) === node.leader_id ? '<p>⭐ LÍDER</p>' : `<p>Líder: ${node.leader_id}</p>`}
                        </div>
                    `;
                });

                sortedIds.forEach(id => {
                    const node = data[id];
                    if (node.status === 'falhou') return; 
                    
                    if (node.status === 'trabalhando' && node.leader_id !== -1 && parseInt(id) !== node.leader_id) {
                        const targetId = String(node.leader_id);
                        if (positions[targetId] && data[targetId].status !== 'falhou') {
                            svgHtml += `<line x1="${positions[id].x}" y1="${positions[id].y}" x2="${positions[targetId].x}" y2="${positions[targetId].y}" class="line-heartbeat" />`;
                        }
                    }

                    if (node.status === 'eleicao') {
                        sortedIds.forEach(targetId => {
                            if (parseInt(targetId) > parseInt(id) && data[targetId].status !== 'falhou') {
                                svgHtml += `<line x1="${positions[id].x}" y1="${positions[id].y}" x2="${positions[targetId].x}" y2="${positions[targetId].y}" class="line-election" />`;
                            }
                        });
                    }
                });

                container.innerHTML = nodesHtml;
                svg.innerHTML = svgHtml;

            } catch (error) {
                console.error('Erro ao buscar status:', error);
            }
        }

        setInterval(fetchStatus, 1000);
        window.addEventListener('resize', fetchStatus);
        fetchStatus();
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/start', methods=['POST'])
def start_server_route():
    global server_process, nodes_state
    data = request.json
    numproc = str(data.get('numproc', 5))
    detectproc = str(data.get('detectproc', 2))
    
    # Se já existir um processo rodando, não inicia outro
    if server_process is None or server_process.poll() is not None:
        nodes_state.clear() # Limpa nós antigos da tela
        # Dispara o comando no terminal em background
        server_process = subprocess.Popen(['python3', 'main.py', '-numproc', numproc, '-detectproc', detectproc])
        return jsonify({"status": "started"})
    
    return jsonify({"status": "already_running"})

@app.route('/stop', methods=['POST'])
def stop_server_route():
    global server_process, nodes_state
    if server_process and server_process.poll() is None:
        server_process.terminate() # Mata o processo
        server_process.wait()
    nodes_state.clear()
    return jsonify({"status": "stopped"})

@app.route('/update', methods=['POST'])
def update():
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
    now = time.time()
    for nid, info in nodes_state.items():
        if info['status'] != 'falhou' and (now - info['last_seen'] > 10):
            info['status'] = 'falhou'
    return jsonify(nodes_state)

if __name__ == '__main__':
    app.run(port=5000, debug=True, use_reloader=False)