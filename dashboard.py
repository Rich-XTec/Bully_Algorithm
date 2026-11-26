from flask import Flask, request, jsonify, render_template_string
from werkzeug.serving import WSGIRequestHandler
import logging
import signal
import time
import subprocess
import os
import sys

class SuppressPollingFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        return '/status' not in msg and '/update' not in msg

class QuietRequestHandler(WSGIRequestHandler):
    def log_request(self, code='-', size='-'):
        # Suprime logs de requisições bem-sucedidas (2xx/3xx), mantendo apenas erros (4xx/5xx)
        if str(code).startswith(('4', '5')):
            self.log('error', '"%s" %s %s', self.requestline, code, size)

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
log.addFilter(SuppressPollingFilter())

app = Flask(__name__)

nodes_state = {}
events_log = []
MAX_EVENTS = 60
server_process = None

def add_event(message):
    timestamp = time.strftime('%H:%M:%S')
    events_log.append({'time': timestamp, 'message': message})
    if len(events_log) > MAX_EVENTS:
        events_log.pop(0)

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
        .input-group input, .input-group select { 
            width: 90%; padding: 8px; border-radius: 6px; border: none; 
            background: #313244; color: white; outline: none; font-family: inherit;
        }
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
            position: absolute; padding: 12px; border-radius: 50%; 
            width: 124px; height: 124px; display: flex; flex-direction: column; justify-content: center; align-items: center;
            background-color: #313244; box-shadow: 0 0 20px rgba(0,0,0,0.5); 
            transition: all 0.5s ease-out; transform: translate(-50%, -50%); 
        }
        .node h2 { margin: 0 0 5px 0; font-size: 20px; text-shadow: 0 2px 4px rgba(0,0,0,0.5);}
        .node p { margin: 2px 0; font-size: 12px; color: #bac2de; }
        .starting { background-color: #585b70; border: 2px dashed #89b4fa; color: #cdd6f4; }

        #info-panel {
            position: absolute;
            top: 20px;
            right: 20px;
            width: 360px;
            max-height: calc(100vh - 40px);
            display: flex;
            flex-direction: column;
            gap: 12px;
            z-index: 200;
            text-align: left;
        }
        .panel-card {
            background-color: #1e1e2e;
            padding: 15px;
            border-radius: 12px;
            border: 1px solid #313244;
            box-shadow: 0 4px 15px rgba(0,0,0,0.5);
        }
        .panel-card h3 {
            margin: 0 0 10px 0;
            color: #cdd6f4;
            font-size: 15px;
            border-bottom: 1px solid #313244;
            padding-bottom: 6px;
        }
        #servers-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
        }
        #servers-table th, #servers-table td {
            padding: 6px 4px;
            border-bottom: 1px solid #313244;
            text-align: center;
        }
        #servers-table th { color: #bac2de; font-weight: 600; }
        .port-cell { font-family: Consolas, monospace; color: #89dceb; }
        .badge {
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: bold;
            display: inline-block;
        }
        .badge-online { background-color: #a6e3a1; color: #11111b; }
        .badge-election { background-color: #fab387; color: #11111b; }
        .badge-dead { background-color: #f38ba8; color: #11111b; }
        .badge-starting { background-color: #89b4fa; color: #11111b; }

        #events-list {
            height: 230px;
            overflow-y: auto;
            font-family: Consolas, monospace;
            font-size: 11px;
            color: #cdd6f4;
            background-color: #11111b;
            border-radius: 6px;
            padding: 8px;
        }
        .event-item {
            margin-bottom: 5px;
            line-height: 1.35;
            border-bottom: 1px solid #1e1e2e;
            padding-bottom: 4px;
        }
        .event-time { color: #89b4fa; margin-right: 6px; }
        
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
        
        <!-- NOVO: Seleção do Sistema Operacional -->
        <div class="input-group">
            <label>Modelo do Servidor (SO)</label>
            <select id="os_type">
                <option value="linux">Linux</option>
                <option value="windows">Windows</option>
            </select>
        </div>
        
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

    <div id="info-panel">
        <div class="panel-card">
            <h3>Servidores Criados</h3>
            <table id="servers-table">
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Interna</th>
                        <th>Cliente</th>
                        <th>Papel</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody id="servers-tbody">
                    <tr><td colspan="5" style="color:#6c7086;">Nenhum servidor ativo</td></tr>
                </tbody>
            </table>
        </div>

        <div class="panel-card">
            <h3>Funcionamento (Eventos)</h3>
            <div id="events-list">
                <div style="color:#6c7086;">Aguardando inicialização...</div>
            </div>
        </div>
    </div>

    <div id="dashboard-area">
        <svg id="connections"></svg>
        <div id="nodes-container"></div>
    </div>

    <script>
        async function startCluster() {
            const os_type = document.getElementById('os_type').value;
            const numproc = document.getElementById('numproc').value;
            const detectproc = document.getElementById('detectproc').value;
            
            document.getElementById('start-btn').innerText = 'Iniciando...';
            document.getElementById('start-btn').disabled = true;

            const response = await fetch('/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    os_type: os_type, 
                    numproc: parseInt(numproc), 
                    detectproc: parseInt(detectproc) 
                })
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
            document.getElementById('servers-tbody').innerHTML =
                '<tr><td colspan="5" style="color:#6c7086;">Nenhum servidor ativo</td></tr>';
            document.getElementById('events-list').innerHTML =
                '<div style="color:#6c7086;">Aguardando inicialização...</div>';
        }

        async function fetchStatus() {
            try {
                const response = await fetch('/status');
                const payload = await response.json();
                const data = payload.nodes || {};
                const events = payload.events || [];

                const container = document.getElementById('nodes-container');
                const svg = document.getElementById('connections');
                const tbody = document.getElementById('servers-tbody');
                const eventsDiv = document.getElementById('events-list');

                let nodesHtml = '';
                let svgHtml = '';
                let tableHtml = '';

                const sortedIds = Object.keys(data).sort((a, b) => Number(a) - Number(b));
                const numNodes = sortedIds.length;

                // Centraliza o grafo no espaço útil entre os dois painéis laterais
                const leftOffset = 260;
                const rightOffset = 400;
                const availableWidth = Math.max(window.innerWidth - leftOffset - rightOffset, 320);
                const centerX = leftOffset + availableWidth / 2;
                const centerY = window.innerHeight / 2 + 20;
                const radius = Math.min(availableWidth / 2, window.innerHeight / 2 - 90) * 0.72;

                const positions = {};
                const statusLabels = {
                    'trabalhando': 'Online',
                    'eleicao': 'Eleição',
                    'falhou': 'Falhou',
                    'inicializando': 'Iniciando'
                };

                sortedIds.forEach((id, index) => {
                    const node = data[id];
                    const angle = (index / numNodes) * (2 * Math.PI) - (Math.PI / 2);
                    const x = centerX + radius * Math.cos(angle);
                    const y = centerY + radius * Math.sin(angle);
                    positions[id] = { x, y };

                    const isLeader = parseInt(id) === node.leader_id && node.status !== 'falhou';
                    let cssClass = 'node';
                    let badgeClass = 'badge badge-online';

                    if (node.status === 'falhou') {
                        cssClass += ' dead';
                        badgeClass = 'badge badge-dead';
                    } else if (node.status === 'eleicao') {
                        cssClass += ' election';
                        badgeClass = 'badge badge-election';
                    } else if (node.status === 'inicializando') {
                        cssClass += ' starting';
                        badgeClass = 'badge badge-starting';
                    } else if (isLeader) {
                        cssClass += ' leader';
                    }

                    const statusText = statusLabels[node.status] || node.status.toUpperCase();
                    const roleText = isLeader ? 'Líder' : (node.is_detector ? 'Detector' : 'Nó');

                    nodesHtml += `
                        <div class="${cssClass}" style="left: ${x}px; top: ${y}px;">
                            <h2>ID ${id}</h2>
                            <p>${statusText}</p>
                            <p style="font-size:10px;">Cli: ${node.client_port ?? '-'}</p>
                            ${isLeader ? '<p>LÍDER</p>' : `<p>Líder: ${node.leader_id === -1 ? '-' : node.leader_id}</p>`}
                        </div>
                    `;

                    tableHtml += `
                        <tr>
                            <td><strong>${id}</strong></td>
                            <td class="port-cell">${node.internal_port ?? '-'}</td>
                            <td class="port-cell">${node.client_port ?? '-'}</td>
                            <td>${roleText}</td>
                            <td><span class="${badgeClass}">${statusText}</span></td>
                        </tr>
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
                tbody.innerHTML = numNodes > 0
                    ? tableHtml
                    : '<tr><td colspan="5" style="color:#6c7086;">Nenhum servidor ativo</td></tr>';

                if (events.length > 0) {
                    eventsDiv.innerHTML = [...events].reverse().map(ev =>
                        `<div class="event-item"><span class="event-time">[${ev.time}]</span>${ev.message}</div>`
                    ).join('');
                }
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
    global server_process, nodes_state, events_log
    data = request.json

    os_type = data.get('os_type', 'linux')
    numproc = str(data.get('numproc', 5))
    detectproc = str(data.get('detectproc', 2))

    script_path = 'linux/main.py' if os_type == 'linux' else 'windows/main_win.py'
    python_exec = sys.executable

    if server_process is None or server_process.poll() is not None:
        nodes_state.clear()
        events_log.clear()
        add_event(f"Iniciando cluster ({os_type}) com {numproc} nós | Detector: ID {detectproc}")

        popen_kwargs = {}
        if os.name != 'nt':
            # Cria um novo grupo de processos para permitir encerrar o pai e todos os filhos
            popen_kwargs['start_new_session'] = True

        server_process = subprocess.Popen(
            [python_exec, script_path, '-numproc', numproc, '-detectproc', detectproc],
            **popen_kwargs
        )
        return jsonify({"status": "started", "path_used": script_path})

    return jsonify({"status": "already_running"})

@app.route('/stop', methods=['POST'])
def stop_server_route():
    global server_process, nodes_state, events_log
    if server_process and server_process.poll() is None:
        if os.name == 'nt':
            subprocess.run(
                ['taskkill', '/F', '/T', '/PID', str(server_process.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        else:
            try:
                os.killpg(os.getpgid(server_process.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
            server_process.wait()
    nodes_state.clear()
    events_log.clear()
    return jsonify({"status": "stopped"})

@app.route('/update', methods=['POST'])
def update():
    data = request.json
    node_id = str(data['id'])
    prev = nodes_state.get(node_id)

    new_status = data.get('status', 'trabalhando')
    if new_status in ('working', 'active'):
        new_status = 'trabalhando'

    leader_id = data.get('leader_id', -1)
    internal_port = data.get('internal_port', prev['internal_port'] if prev else '-')
    client_port = data.get('client_port', prev['client_port'] if prev else '-')
    is_detector = data.get('is_detector', prev['is_detector'] if prev else False)

    nodes_state[node_id] = {
        'status': new_status,
        'leader_id': leader_id,
        'internal_port': internal_port,
        'client_port': client_port,
        'is_detector': is_detector,
        'last_seen': time.time()
    }

    event_msg = data.get('event')
    if event_msg:
        add_event(event_msg)
    elif prev is None:
        add_event(f"Nó ID {node_id} criado | Interna: {internal_port} | Cliente: {client_port}")
    elif prev['status'] != new_status:
        add_event(f"Nó ID {node_id}: {prev['status']} -> {new_status}")

    return jsonify({"success": True})

@app.route('/status', methods=['GET'])
def status():
    now = time.time()
    for nid, info in nodes_state.items():
        if info['status'] != 'falhou' and (now - info['last_seen'] > 20):
            info['status'] = 'falhou'
            add_event(f"Nó ID {nid} sem resposta (> 20s): marcado como FALHOU")
    return jsonify({
        "nodes": nodes_state,
        "events": events_log
    })

if __name__ == '__main__':
    print("Dashboard em execução em http://127.0.0.1:5000")
    app.run(port=5000, debug=True, use_reloader=False, request_handler=QuietRequestHandler)