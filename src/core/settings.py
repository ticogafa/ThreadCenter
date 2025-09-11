SYN_TYPE = 0x01            # Synchronization message
ACK_TYPE = 0x02            # Regular acknowledgment
HANDSHAKE_ACK_TYPE = 0x03  # Acknowledgment specific to handshake
DATA_TYPE = 0x04           # Data message
NACK_TYPE = 0x05           # Negative acknowledgment
DISCONNECT_TYPE = 0x06     # Disconnect message

GBN = 0  # Go-Back-N
SR = 1   # Selective Repeat
ERROR_CODE = 99

MAX_RETRIES = 5
DEFAULT_PORT = 5000 # se a porta padrao tiver ocupada mude pra outra da sua preferencia