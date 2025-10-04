import socket
import hashlib
import argparse
import json
import threading
import multiprocessing as mp
import os
from typing import Dict, List, Tuple

from src.network_device import NetworkDevice
from src.core import settings
from src.constants.constants_server import SERVER_LOGS, SERVER_ERRORS
from src.core.settings import DEFAULT_PORT

def _log_worker(queue: "mp.Queue[str]", filepath: str):
    """Processo separado para registrar logs em arquivo (demonstra IPC)."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'a', encoding='utf-8') as f:
        while True:
            msg = queue.get()
            if msg == "__STOP__":
                break
            f.write(msg + "\n")
            f.flush()


class Server(NetworkDevice):
    def __init__(self, host='127.0.0.1', port=DEFAULT_PORT, protocol='gbn', max_fragment_size=3, window_size=4):
        super().__init__(host, port, protocol, max_fragment_size, window_size)
        self.host = host
        self.port = port
        self.client_sessions: Dict[str, dict] = {}
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.settimeout(1.0)

        self._clients_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._threads: List[threading.Thread] = []

        self._log_queue: mp.Queue = mp.Queue()
        self._log_process = mp.Process(target=_log_worker, args=(self._log_queue, os.path.abspath('logs/server.log')))
        self._log_process.daemon = True
        self._log_process.start()

    def handle_syn(self, client_socket: socket.socket, client_address:str, data:dict):
        """Process SYN request during handshake and negotiate connection parameters"""
        print(f'[LOG] Received SYN from {client_address}: {data}')
        
        client_protocol = data.get('protocol', self.protocol)
        requested_fragment_size = data.get('max_fragment_size', self.max_fragment_size)
        requested_window_size = data.get('window_size', self.window_size)
        
        max_fragment_size = min(requested_fragment_size, self.max_fragment_size)
        
        session_id = hashlib.md5(f"{client_address}{socket.gethostname()}".encode()).hexdigest()[:8]
        
        self.client_sessions[client_address] = {
            'protocol': client_protocol,
            'max_fragment_size': max_fragment_size,
            'window_size': requested_window_size,
            'session_id': session_id,
            'handshake_complete': False,
            'socket': client_socket,
            'expected_seq_num': 0,
            'nickname': None,
        }
        
        response = {
            'status': 'ok',
            'protocol': client_protocol,
            'max_fragment_size': max_fragment_size,
            'window_size': requested_window_size,
            'session_id': session_id,
            'message': 'SYN-ACK: Parameters accepted'
        }
        
        packet = self.create_packet(settings.ACK_TYPE, json.dumps(response))
        client_socket.sendall(packet)
        return session_id

    def handle_ack(self, client_address:str, data:dict):
        """Process final ACK to complete handshake"""
        print(f'[LOG] Received ACK from {client_address}: {data}')
        if client_address not in self.client_sessions:
            return False
            
        self.client_sessions[client_address]['handshake_complete'] = True
        print(f'[LOG] Handshake completed for client {client_address}')
        return True


    def process_handshake(self, client_socket: socket.socket, client_address: str):
        """Manage the complete three-way handshake process"""
        header = client_socket.recv(self.BUFFER_SIZE)
        if not header or len(header) < self.HEADER_SIZE:
            raise ValueError(SERVER_ERRORS.INVALID_HEADER.format(client_address=client_address))

        parsed = self.parse_packet(header)
        if not parsed:
            raise ValueError(SERVER_ERRORS.PARSE_PACKET.format(client_address=client_address))

        if parsed['type'] != settings.SYN_TYPE:
            raise ValueError(SERVER_ERRORS.EXPECTED_SYN.format(msg_type=parsed['type']))

        data = json.loads(parsed['payload'])
        client_protocol = data.get('protocol', 'gbn')
        print(f"[LOG] Client requesting protocol: {client_protocol}")
        self.handle_syn(client_socket, client_address, data)

        header = client_socket.recv(self.BUFFER_SIZE)
        parsed = self.parse_packet(header)
        if not parsed:
            raise ValueError(SERVER_ERRORS.FAILED_ACK.format(client_address=client_address))

        if parsed['type'] != settings.HANDSHAKE_ACK_TYPE:
            raise ValueError(SERVER_ERRORS.EXPECTED_ACK.format(msg_type=parsed['type']))

        data = json.loads(parsed['payload'])
        if not self.handle_ack(client_address, data):
            raise ValueError(SERVER_ERRORS.FAILED_ACK.format(client_address=client_address))

        print(SERVER_LOGS.HANDSHAKE_COMPLETE.format(client_address=client_address))
        return True

    def broadcast_to_others(self, from_address: str, payload: bytes):
        """Envia uma mensagem completa para todos os demais clientes conectados."""
        display = from_address
        with self._clients_lock:
            sess = self.client_sessions.get(from_address)
            if sess and sess.get('nickname'):
                display = sess['nickname']
        try:
            text = payload.decode('utf-8')
            payload_to_send = f"[{display}] {text}".encode('utf-8')
        except Exception:
            payload_to_send = payload

        packet = self.create_packet(settings.DATA_TYPE, payload_to_send, sequence_num=0, last_packet=True)

        with self._clients_lock:
            for addr, sess in list(self.client_sessions.items()):
                if addr == from_address:
                    continue
                sock: socket.socket = sess.get('socket')
                if not sock:
                    continue
                try:
                    sock.sendall(packet)
                except Exception as e:
                    print(f"[ERROR] Failed to send to {addr}: {e}")
        try:
            self._log_queue.put_nowait(f"BROADCAST from {from_address} full_message")
        except Exception:
            pass

    def set_nickname(self, client_address: str, nickname: str):
        with self._clients_lock:
            if client_address in self.client_sessions:
                self.client_sessions[client_address]['nickname'] = nickname

    def list_connected(self) -> List[str]:
        with self._clients_lock:
            result = []
            for addr, sess in self.client_sessions.items():
                name = sess.get('nickname') or addr
                result.append(name)
            return result

    def _client_worker(self, client_socket: socket.socket, addr_tuple: Tuple[str, int]):
        client_address = f"{addr_tuple[0]}:{addr_tuple[1]}"
        print(SERVER_LOGS.NEW_CONNECTION.format(client_address=client_address))
        try:
            if self.process_handshake(client_socket, client_address):
                with self._clients_lock:
                    if client_address in self.client_sessions:
                        self.client_sessions[client_address]['handshake_complete'] = True
                self.handle_client_messages(client_socket, client_address)
        except (ConnectionError, ValueError) as e:
            print(e)
        except Exception as e:
            print(e)
        finally:
            try:
                client_socket.close()
            except Exception:
                pass
            with self._clients_lock:
                if client_address in self.client_sessions:
                    del self.client_sessions[client_address]
            print(SERVER_LOGS.CONNECTION_CLOSED.format(client_address=client_address))

    def start(self):
        """Initialize the server, bind to socket, and begin listening for connections (multi-cliente)."""
        try:
            self._socket.bind((self.host, self.port))
            try:
                self.port = self._socket.getsockname()[1]
            except Exception:
                pass
            self._socket.listen(20)
            print(SERVER_LOGS.START.format(host=self.host, port=self.port))
            print(SERVER_LOGS.PROTOCOL.format(protocol=self.protocol, max_fragment_size=self.max_fragment_size))
            print(SERVER_LOGS.WINDOW.format(window_size=self.window_size))

            while not self._stop_event.is_set():
                try:
                    client_socket, addr = self._socket.accept()
                except socket.timeout:
                    continue
                except KeyboardInterrupt:
                    print("[LOG] Server shutting down gracefully...")
                    break
                except Exception as e:
                    print(f"[ERROR] Error accepting new connection: {e}")
                    continue

                client_address = f"{addr[0]}:{addr[1]}"
                with self._clients_lock:
                    self.client_sessions.setdefault(client_address, {'socket': client_socket})
                t = threading.Thread(target=self._client_worker, args=(client_socket, addr), daemon=True)
                t.start()
                self._threads.append(t)
        finally:
            self._stop_event.set()
            try:
                self._socket.close()
            except Exception:
                pass
                if t.is_alive():
                    t.join(timeout=1.0)
            try:
                self._log_queue.put("__STOP__")
                self._log_process.join(timeout=2.0)
            except Exception:
                pass
            print(SERVER_LOGS.SOCKET_CLOSED)

    def stop(self):
        """Signal the server to stop accepting and shutdown gracefully."""
        self._stop_event.set()
        try:
            self._socket.close()
        except Exception:
            pass


if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser(description='Custom Protocol Server')
        parser.add_argument('--host', default='0.0.0.0', help='Host address to bind')
        parser.add_argument('--port', type=int, default=DEFAULT_PORT, help='Port to listen on')
        parser.add_argument('--max-fragment-size', type=int, default=3, help='Maximum fragment size')
        parser.add_argument('--protocol', choices=['gbn', 'sr'], default='gbn',
                            help='Reliable transfer protocol (Go-Back-N or Selective Repeat)')
        parser.add_argument('--window-size', type=int, default=4,
                            help='Sliding window size (number of packets in flight)')
    
        args = parser.parse_args()
    
        server = Server(
            host=args.host,
            port=args.port,
            max_fragment_size=args.max_fragment_size,
            protocol=args.protocol,
            window_size=args.window_size
        )
        
        server.start()
    
    except Exception as e:
        print(f"[ERROR] An error occurred: {e}")
