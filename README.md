# ThreadCenter — Chat distribuído com janela deslizante

Este projeto implementa uma arquitetura cliente-servidor com suporte a múltiplos clientes simultâneos. Mensagens enviadas por um cliente são recebidas pelo servidor e retransmitidas (broadcast) para todos os demais clientes conectados.

Conceitos aplicados:
- Arquitetura distribuída: cliente-servidor TCP
- Concorrência: threads por cliente no servidor e thread receptora no cliente
- Paralelismo e IPC: processo separado para logging consumindo fila multiprocessing.Queue
- Sincronização: mutex (Lock) para acesso à tabela de sessões e Event para shutdown
- Comunicação entre processos/threads: Queue (processos), sockets TCP e comunicação entre threads via eventos

## Estrutura
- `src/server.py`: servidor multi-cliente com broadcast e processo de logging
- `src/client.py`: cliente com handshake, envio fragmentado e recepção assíncrona
- `src/network_device.py`: protocolo, cabeçalho, checksum, fragmentação, ACK/NACK
- `src/terminal_ui.py`: UI de terminal opcional (modo UI)
- `src/core/settings.py`: tipos de mensagem e configurações

## Diagrama de arquitetura
```mermaid
flowchart LR
  subgraph Clients
    C1[Client A]\n(send/recv threads)
    C2[Client B]\n(send/recv threads)
    C3[Client C]\n(send/recv threads)
  end
  C1 <-- TCP --> S(Server) 
  C2 <-- TCP --> S
  C3 <-- TCP --> S
  subgraph Server
    S[Server]\n(threads por cliente)
    Q[(mp.Queue)]
    L[[Log Process]]
  end
  S -- broadcast DATA --> C1
  S -- broadcast DATA --> C2
  S -- broadcast DATA --> C3
  S -- logs --> Q --> L
```

## Requisitos
- Python 3.10+

Instale dependências (se houver) listadas em `requirements.txt`.

## Como executar (fish shell)
Recomendado executar como módulo (-m) para que os imports `src.*` funcionem sem configurar PYTHONPATH.

Servidor (escuta por padrão em 0.0.0.0:5000):
```fish
python -m src.server
```

Cliente (modo chat é o padrão e pergunta host/porta se você não passar flags):
```fish
python -m src.client
```

Você pode passar host/porta explicitamente se quiser:
```fish
python -m src.client --host 127.0.0.1 --port 5000
```

Modo UI opcional (menus):
```fish
python -m src.client --mode ui
```

Alternativa (rodar os arquivos diretamente): exporte o PYTHONPATH com a raiz do projeto antes:
```fish
set -x PYTHONPATH (pwd)
python src/server.py
python src/client.py
```

Uso em máquinas diferentes (mesma rede):
- Rode o servidor na máquina “servidor” (ele já escuta em todas as interfaces: 0.0.0.0).
- No cliente, informe o IP da máquina do servidor (ex.: `--host 192.168.1.123`). Para descobrir o IP no Linux:
  ```fish
  hostname -I | awk '{print $1}'
  # ou
  ip -4 -brief addr show
  ```

No cliente (chat), digite mensagens e pressione Enter. As mensagens são retransmitidas aos demais clientes. Comandos úteis no chat:
- `/who` — lista usuários conectados (apelido ou IP:porta)
- `/nick <nome>` — define seu apelido (exibido no broadcast)

## Notas de protocolo
- Handshake de 3 vias (SYN, SYN-ACK, ACK)
- Pacotes DATA possuem cabeçalho com tamanho, tipo, sequência, checksum e last_packet
- ACK/NACK por fragmento; cliente mantém janela e controla reenvios
- Servidor reconhece DATA com ACK e realiza broadcast aos outros clientes

## Logs
- Servidor escreve logs em `logs/server.log` usando um processo dedicado (multiprocessing). A pasta `logs/` já existe no projeto.

## Troubleshooting
- Porta em uso: altere `--port`
- Mensagens não chegam: verifique firewall, IP/porta e se o server está ativo

---
Para o artigo completo e prints, veja `docs/artigo.md` (exporte para PDF para entrega).

## Dependências
O projeto utiliza apenas biblioteca padrão do Python. O `requirements.txt` está vazio por intenção.