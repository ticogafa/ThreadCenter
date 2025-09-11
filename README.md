ThreadCenter — Arquitetura distribuída com concorrência e paralelismo
=====================================================================

Este projeto demonstra uma solução distribuída no modelo cliente-servidor, incluindo:

- Threads: servidor usa threads para atender clientes e o cliente usa múltiplas threads para gerar carga concorrente.
- Processos: servidor utiliza processos (multiprocessing) para tarefas CPU-bound.
- Sincronização: uso de `Lock` para mapear respostas a conexões e coordenar acesso compartilhado.
- Comunicação entre processos/threads: filas (`multiprocessing.Queue`) e socket TCP com enquadramento por comprimento.

Tecnologia
----------

- Python 3.9+
- Sockets TCP com framing (4 bytes big-endian + JSON)
- `threading`, `selectors`, `concurrent.futures.ThreadPoolExecutor`
- `multiprocessing.Process`, `Queue`, `Event`

Estrutura
---------

- `server.py`: servidor multithread com pool de processos para computação.
- `client.py`: cliente multithread para envio de requisições concorrentes.

Como executar (Windows PowerShell)
----------------------------------

Abra dois terminais na pasta do projeto.

1. Inicie o servidor:

```powershell
python .\server.py --host 127.0.0.1 --port 5050 --workers 4
```

1. Em outro terminal, rode o cliente (exemplo com 4 threads, 5 requisições cada e carga de 500k passos):

```powershell
python .\client.py --host 127.0.0.1 --port 5050 --concurrency 4 --requests 5 --size 500000
```

Você deverá ver o servidor aceitando conexões e enviando respostas, e o cliente reportando o total de respostas e tempo.

Protocolo
---------

- Mensagens são JSON enquadradas por um prefixo de 4 bytes (uint32 big-endian) indicando o tamanho do payload.
- Requisição de computação do cliente:

```json
{"id": "<uuid>", "cmd": "compute", "n": <int>}
```

- Resposta do servidor:

```json
{"id": "<uuid>", "result": <int>}
```

Testes rápidos
--------------

- Ping simples (sem carga):

Você pode alterar o cliente para enviar `cmd: ping` ou usar `netcat`/script externo para validar o framing.

Parâmetros de desempenho
------------------------

- `--workers`: número de processos (pool de trabalhadores CPU-bound).
- `--concurrency`: número de threads do cliente.
- `--requests`: requisições por thread no cliente.
- `--size`: carga da função CPU-bound (maior = mais lento, mais CPU).

Notas
-----

- Em Windows, `multiprocessing` inicia novos processos via spawn; por isso, toda a lógica de inicialização de processos está protegida sob `if __name__ == "__main__":` nos módulos executáveis.
- O servidor mantém um dicionário protegido por `Lock` para mapear `id -> conexão` enquanto o resultado é processado em processos separados e despachado por uma thread dedicada.
