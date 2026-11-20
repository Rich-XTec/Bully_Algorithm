from flask import Flask, request, jsonify, render_template_string
import time

app = Flask(__name__)

nodes_state = {}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt">
<head>
    <meta charset="UTF-8">
    <title>Painel do Sistema Distribuído (Bully)</title>
    <style>
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            background-color: #11111b; /* Fundo mais escuro para destacar as luzes */
            color: white; 
            text-align: center; 
            margin: 0;
            overflow: hidden; /* Remove rolagem para parecer um radar */
        }
        h1 { position: absolute; width: 100%; top: 20px; color: #cdd6f4; z-index: 100; text-shadow: 0 0 10px rgba(255,255,255,0.2); }
        
        #dashboard-area {
            position: relative;
            width: 100vw;
            height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }

        /* SVG para desenhar as linhas */
        #connections {
            position: absolute;
            top: 0; left: 0;
            width: 100%; height: 100%;
            z-index: 1;
            pointer-events: none;
        }

        /* Linhas sutis brancas de Heartbeat */
        .line-heartbeat {
            stroke: rgba(255, 255, 255, 0.15);
            stroke-width: 2;
            stroke-dasharray: 8, 8;
            animation: dash 15s linear infinite;
        }

        /* Linhas de Eleição (Laranja) */
        .line-election {
            stroke: rgba(250, 179, 135, 0.4);
            stroke-width: 3;
            stroke-dasharray: 15, 5;
            animation: dash 5s linear infinite reverse;
        }

        @keyframes dash {
            to { stroke-dashoffset: 1000; }
        }

        #nodes-container {
            position: absolute;
            top: 0; left: 0;
            width: 100%; height: 100%;
            z-index: 10;
        }

        .node { 
            position: absolute;
            padding: 15px; 
            border-radius: 50%; /* Nós redondos para ficar mais espacial */
            width: 110px; height: 110px;
            display: flex; flex-direction: column; justify-content: center; align-items: center;
            background-color: #313244; 
            box-shadow: 0 0 20px rgba(0,0,0,0.5); 
            transition: all 0.5s ease-out; 
            transform: translate(-50%, -50%); /* Centraliza o nó exatamente na coordenada X,Y */
        }
        .node h2 { margin: 0 0 5px 0; font-size: 20px; text-shadow: 0 2px 4px rgba(0,0,0,0.5);}
        .node p { margin: 2px 0; font-size: 12px; color: #bac2de; }
        
        /* Cores de Status */
        .leader { 
            background-color: #a6e3a1; color: #11111b; 
            border: 4px solid #f9e2af; 
            box-shadow: 0 0 30px rgba(166, 227, 161, 0.6);
            transform: translate(-50%, -50%) scale(1.15); 
            z-index: 20;
        }
        .leader p, .leader h2 { color: #11111b; font-weight: bold; text-shadow: none;}
        
        .dead { 
            background-color: #45475a; 
            border: 2px solid #f38ba8;
            opacity: 0.5; color: #f38ba8; 
            box-shadow: none;
        }
        .dead p, .dead h2 { color: #f38ba8; }

        .election { 
            background-color: #fab387; color: #11111b; 
            box-shadow: 0 0 30px rgba(250, 179, 135, 0.8);
            animation: pulse 1s infinite; 
        }
        .election p, .election h2 { color: #11111b; text-shadow: none;}
        
        @keyframes pulse { 
            0% { transform: translate(-50%, -50%) scale(1); } 
            50% { transform: translate(-50%, -50%) scale(1.1); } 
            100% { transform: translate(-50%, -50%) scale(1); } 
        }
    </style>
</head>
<body>
    <h1>Topologia da Rede - Algoritmo de Bully</h1>
    <div id="dashboard-area">
        <svg id="connections"></svg>
        <div id="nodes-container"></div>
    </div>

    <script>
        async function fetchStatus() {
            try {
                const response = await fetch('/status');
                const data = await response.json();
                
                const container = document.getElementById('nodes-container');
                const svg = document.getElementById('connections');
                
                let nodesHtml = '';
                let svgHtml = '';

                // Pega os IDs em ordem crescente
                const sortedIds = Object.keys(data).sort((a, b) => a - b);
                const numNodes = sortedIds.length;

                // Centro da tela e cálculo do raio (depende do tamanho do navegador)
                const centerX = window.innerWidth / 2;
                const centerY = window.innerHeight / 2;
                const radius = Math.min(centerX, centerY) * 0.65; // Ocupa 65% do espaço

                const positions = {}; // Guarda as coordenadas para traçar as linhas depois

                // 1º Passo: Calcular posições e renderizar os nós no HTML
                sortedIds.forEach((id, index) => {
                    const node = data[id];
                    
                    // Matemática trigonométrica para distribuir num círculo
                    // Math.PI / 2 rotaciona para começar do topo da tela
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

                // 2º Passo: Renderizar as linhas sutis conectando as coordenadas
                sortedIds.forEach(id => {
                    const node = data[id];
                    if (node.status === 'falhou') return; // Nós mortos não têm conexões
                    
                    // Se estiver trabalhando, traça linha branca de heartbeat para o LÍDER
                    if (node.status === 'trabalhando' && node.leader_id !== -1 && parseInt(id) !== node.leader_id) {
                        const targetId = String(node.leader_id);
                        if (positions[targetId] && data[targetId].status !== 'falhou') {
                            svgHtml += `<line x1="${positions[id].x}" y1="${positions[id].y}" x2="${positions[targetId].x}" y2="${positions[targetId].y}" class="line-heartbeat" />`;
                        }
                    }

                    // Se estiver em eleição, traça linha laranja para IDs maiores
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

        // Atualiza a tela suavemente e lida com redimensionamento da janela
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