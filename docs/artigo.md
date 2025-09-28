# ThreadCenter: Chat Distribuído com Confiabilidade e Concorrência

## Resumo
Apresentamos uma aplicação cliente-servidor que implementa comunicação confiável com fragmentação e confirmação (ACK/NACK), suporte a múltiplos clientes simultâneos e broadcast das mensagens entre clientes. O servidor utiliza threads por cliente e um processo separado para logging (multiprocessing), ilustrando concorrência, paralelismo e comunicação entre processos. O protocolo inclui handshake de três vias, cabeçalho binário com checksum e janela deslizante.

## Introdução
Sistemas distribuídos exigem mecanismos de comunicação e confiabilidade para lidar com perdas, corrupção e atrasos. Este trabalho propõe uma solução prática baseada em TCP somada a um protocolo de aplicação simples com fragmentação, além de uma arquitetura que evidencia conceitos de concorrência e paralelismo.

## Metodologia
### Arquitetura
- Modelo: cliente-servidor.
- Concorrência no servidor: thread por conexão (worker) + lista de sessões protegida por Lock.
- Paralelismo/IPC: processo dedicado para logging consumindo mensagens via `multiprocessing.Queue`.
- Cliente: thread receptora para exibir broadcasts enquanto a thread principal envia mensagens.

### Protocolo de aplicação
- Handshake: SYN → SYN-ACK → ACK.
- Tipos de mensagem: DATA, ACK, NACK, DISCONNECT, ERROR_CODE (configuração de canal), SET_NICK (definir apelido), LIST_REQUEST/LIST_RESPONSE (listar clientes conectados).
- Cabeçalho: `length(4) | type(1) | seq(2) | checksum(4) | last(1)`.
- Fragmentação: mensagens são divididas em fragmentos de `max_fragment_size` e cada fragmento recebe ACK.
- Broadcast: ao receber DATA válido e reconstituir a mensagem completa (last=1), o servidor ACK e retransmite para os demais clientes (prefixando o remetente/nick quando possível).

### Sincronização e desligamento
- Mutex para tabela de clientes.
- Event para sinalizar encerramento e shutdown limpo.
- `try/finally` garantindo fechamento de sockets, join de threads e término do processo de logging.

## Resultados
- Mensagens enviadas por um cliente chegam aos demais conectados (broadcast).
- Confirmação por fragmento com ACK/NACK.
- Recepção assíncrona no cliente evita bloqueios na UI/entrada.
- Logs persistidos em `logs/server.log` pelo processo separado.

Figura 1 – Diagrama de arquitetura (também disponível no README):
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

## Como reproduzir
1) Servidor (por padrão escuta em 0.0.0.0:5000):
  - `python -m src.server`

2) Cliente (modo chat é o padrão e pergunta host/porta se omitidos):
  - `python -m src.client`
  - Opcionalmente, passe host/porta: `python -m src.client --host 127.0.0.1 --port 5000`
  - Modo UI opcional (menus): `python -m src.client --mode ui`

3) No chat, use:
  - Digite mensagens e pressione Enter (serão retransmitidas como `[BROADCAST] ...`).
  - Comandos: `/who` (lista usuários conectados) e `/nick <nome>` (define apelido exibido no broadcast).

Notas:
- Em máquinas diferentes na mesma rede, rode o servidor e informe no cliente o IP da máquina do servidor (ex.: `--host 192.168.1.123`).

## Discussão
A solução demonstra:
- Arquitetura distribuída (cliente-servidor)
- Concorrência (threads) e paralelismo (processo de logging)
- Sincronização (Lock/Event) e comunicação entre processos/threads (Queue, sockets)

Limitações: protocolo simplificado, sem autenticação, sem compressão, sem reordenação avançada além do básico. O controle de janela é mantido no cliente e o servidor apenas ACK e retransmite.

## Conclusão
O projeto atinge os objetivos pedagógicos de implementar uma solução distribuída funcional e reprodutível, incorporando concorrência, paralelismo e mecanismos de comunicação e sincronização. O código está organizado e documentado para facilitar testes e avaliação.

## Referências
- Tanenbaum, A. S., & Van Steen, M. Distributed Systems: Principles and Paradigms.
- Documentação Python: `socket`, `threading`, `multiprocessing`.
