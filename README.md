ThreadCenter — Arquitetura distribuída com concorrência e paralelismo
=====================================================================

Resumo
------

- Modelo cliente-servidor com threads (I/O) + pool de processos (CPU-bound).
- Comunicação via TCP com framing (4 bytes big-endian + JSON).
- Ferramenta para estudar throughput/latência e escalabilidade em Python.

Sumário
-------

- [Instalação](#instalação)
- [Como executar (Quickstart)](#como-executar-quickstart)
- [Arquitetura](#arquitetura)
- [Protocolo](#protocolo)
- [Parâmetros e tuning](#parâmetros-e-tuning)
- [Exemplos de uso](#exemplos-de-uso)
- [Troubleshooting](#troubleshooting)
- [Configuração e constantes](#configuração-e-constantes)
- [Testes](#testes)
- [Como estender](#como-estender)
- [Notas de desenvolvimento](#notas-de-desenvolvimento)
- [Roadmap](#roadmap)
- [Licença](#licença)

Instalação
----------

Pré-requisitos:
- Python 3.9+

Passos recomendados:

Windows PowerShell:
```powershell
# Na raiz do projeto
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Linux/macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Como executar (Quickstart)
--------------------------

Abra dois terminais na raiz do projeto.

Servidor:

Windows PowerShell:
```powershell
python .\src\server.py --host 127.0.0.1 --port 5050 --workers 4
```

Linux/macOS:
```bash
python3 src/server.py --host 127.0.0.1 --port 5050 --workers 4
```

Cliente (ex.: 4 threads, 5 requisições por thread, carga 500k passos):

Windows PowerShell:
```powershell
python .\src\client.py --host 127.0.0.1 --port 5050 --concurrency 4 --requests 5 --size 500000
```

Linux/macOS:
```bash
python3 src/client.py --host 127.0.0.1 --port 5050 --concurrency 4 --requests 5 --size 500000
```

Arquitetura
-----------

- Threads no cliente para concorrência de I/O, simulando múltiplos emissores.
- Servidor multiplexa conexões e delega tarefas CPU-bound a processos.
- IPC/sincronização: `Lock`, `Queue`, `Event`.
- Transporte: TCP com framing de mensagens.

Diagrama (alto nível):
```
[Client Threads] --TCP/JSON--> [Server (accept + dispatcher)] --Queue--> [Process Pool]
        ^                            |                                       |
        |                            v                                       v
   métricas/logs               framing + parse                          compute(n)
```

Protocolo
---------

Enquadramento (framing):
- 4 bytes prefixados (uint32 big-endian) indicando o tamanho do payload JSON.
- Em seguida, o payload em UTF-8.

Mensagens:

- Requisição:
```json
{"id": "<uuid>", "cmd": "compute", "n": <int>}
```

- Resposta (sucesso):
```json
{"id": "<uuid>", "result": <int>}
```

- Resposta (erro – recomendado):
```json
{"id": "<uuid>", "error": {"code": "BAD_REQUEST", "message": "detalhes"}}
```

Exemplo de framing (envio em Python):
```python
import json, socket, struct

msg = json.dumps({"id":"123","cmd":"compute","n":500000}).encode()
frame = struct.pack(">I", len(msg)) + msg
sock.sendall(frame)
```

Parâmetros e tuning
-------------------

- `--workers` (servidor): processos CPU-bound. Regra prática: ~ núm. de cores físicos/virtuais (teste).
- `--concurrency` (cliente): threads gerando requisições (I/O). Aumente para saturar o servidor.
- `--requests` (cliente): requisições por thread.
- `--size` (cliente): custo da função CPU-bound. Maior ⇒ mais lento/mais CPU.

Dicas:
- Aumente `--workers` até ver utilização de CPU próxima a 100% sem degradar latência de forma excessiva.
- Use cargas (`--size`) crescentes para observar o ponto de saturação.
- Mantenha cliente e servidor na mesma máquina para medir CPU; use máquinas separadas para medir rede.

Exemplos de uso
---------------

- Baixa carga e baixa latência (teste rápido):
```bash
python3 src/server.py --workers 2
python3 src/client.py --concurrency 2 --requests 5 --size 10000
```

- Carga média para ver escalonamento:
```bash
python3 src/server.py --workers 4
python3 src/client.py --concurrency 8 --requests 10 --size 200000
```

- Estresse (pode aquecer a CPU):
```bash
python3 src/server.py --workers 8
python3 src/client.py --concurrency 32 --requests 20 --size 800000
```

Troubleshooting
---------------

- Porta em uso (OSError: Address already in use):
  - Ajuste `--port` ou finalize processo que ocupa a porta.
- Conexão recusada:
  - Confirme host/porta, firewall e se o servidor está ativo.
- Windows + multiprocessing (spawn):
  - Garanta que a criação de processos esteja sob `if __name__ == "__main__":` nos executáveis.
- Mensagens truncadas/invalid JSON:
  - Verifique o framing (4 bytes big-endian corretos) e `sendall/recv` em laços até completar o payload.
- Performance aquém do esperado:
  - Reduza/ajuste `--workers` (evitar over-subscription), feche apps pesados e desative modo economia de energia.

Configuração e constantes
-------------------------

- Ajustes gerais em:
  - `src/core/settings.py`
  - `src/constants/constants_server.py`
  - `src/constants/constants_client.py`
- Centralize host/porta/comportamentos ali para manter o código do servidor/cliente enxuto.

Testes
------

- Se houver testes:
```bash
pytest -q
```
- Sugestão: testes de protocolo (framing), de concorrência (ordem de respostas irrelevante) e de carga (limiar de tempo).

Como estender
-------------

- Novos comandos (ex.: `cmd: "stats"`):
  - No servidor: adicione um branch/dispatcher para o novo `cmd` e implemente a rotina (CPU-bound ⇒ pool; I/O-bound ⇒ thread).
  - No cliente: gere a mensagem com o novo `cmd` e trate o retorno.
  - Mantenha o contrato JSON e o framing de 4 bytes.
- Novas métricas:
  - Instrumente tempos de fila, de processamento e de I/O; agregue por requisição/worker.

Notas de desenvolvimento
------------------------

- Em Windows, `multiprocessing` usa spawn; a inicialização de processos fica sob `if __name__ == "__main__":`.
- A camada de rede e framing está em `src/network_device.py` — útil para testes isolados.

Roadmap
-------

- Métricas e exportação (CSV/Prometheus).
- Suporte a TLS opcional.
- Testes de carga automatizados.
- Dockerfile e compose para cenários distribuídos.

Licença
-------

- Definir licença (ex.: MIT, Apache-2.0).