import socket
import hashlib
import argparse
import json
from src.network_device import NetworkDevice
from src.core import settings
from src.constants.constants_server import SERVER_LOGS, SERVER_ERRORS
from src.core.settings import DEFAULT_PORT

# We'll remove the direct import of ServerTerminalUI to avoid circular dependencies


class Server(NetworkDevice):
    def __init__(self, host='127.0.0.1', port=DEFAULT_PORT, protocol='gbn', max_fragment_size=3, window_size=4):
        super().__init__(host, port, protocol, max_fragment_size, window_size)
        self.host = host
        self.port = port
        self.client_sessions = {}
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def handle_syn(self, client_socket: socket.socket, client_address:str, data:dict):
        """Process SYN request during handshake and negotiate connection parameters"""
        print(f'[LOG] Received SYN from {client_address}: {data}')
        
        # Extract and validate connection parameters
        client_protocol = data.get('protocol', self.protocol)
        requested_fragment_size = data.get('max_fragment_size', self.max_fragment_size)
        requested_window_size = data.get('window_size', self.window_size)
        
        # Apply server-side limits if needed
        max_fragment_size = min(requested_fragment_size, self.max_fragment_size)
        
        # Generate a unique session ID
        session_id = hashlib.md5(f"{client_address}{socket.gethostname()}".encode()).hexdigest()[:8]
        
        # Store session information
        self.client_sessions[client_address] = {
            'protocol': client_protocol,
            'max_fragment_size': max_fragment_size,
            'window_size': requested_window_size,
            'session_id': session_id,'127.0.0.1'
            'handshake_complete': False,
            'socket': client_socket,
            'expected_seq_num': 0,  # For GBN
        }
        
        # Prepare SYN-ACK response with negotiated parameters
        response = {
            'status': 'ok',
            'protocol': client_protocol,
            'max_fragment_size': max_fragment_size,
            'window_size': requested_window_size,
            'session_id': session_id,
            'message': 'SYN-ACK: Parameters accepted'
        }
        
        # Send SYN-ACK
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
        # Let exceptions bubble up, handle/log in main loop
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

        # Wait for final ACK
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

    def start(self):
        """Initialize the server, bind to socket, and begin listening for connections"""
        try:
            self._socket.bind((self.host, self.port))
            self._socket.listen(5)
            print(SERVER_LOGS.START.format(host=self.host, port=self.port))
            print(SERVER_LOGS.PROTOCOL.format(protocol=self.protocol, max_fragment_size=self.max_fragment_size))
            print(SERVER_LOGS.WINDOW.format(window_size=self.window_size))

            while True:
                try:
                    client_socket, addr = self._socket.accept()
                    client_address = f"{addr[0]}:{addr[1]}"
                    print(SERVER_LOGS.NEW_CONNECTION.format(client_address=client_address))
                    try:
                        if self.process_handshake(client_socket, client_address):
                            self.handle_client_messages(client_socket, client_address)
                    except (ConnectionError, ValueError) as e:
                        print(e)
                    except Exception as e:
                        print(e)
                    finally:
                        client_socket.close()
                except KeyboardInterrupt:
                    print("[LOG] Server shutting down gracefully...")
                    break
                except Exception as e:
                    print(f"[ERROR] Error accepting new connection: {e}")
        finally:
            self._socket.close()
            print(SERVER_LOGS.SOCKET_CLOSED)


if __name__ == '__main__':
    try:
        # Parse command line arguments
        parser = argparse.ArgumentParser(description='Custom Protocol Server')
        parser.add_argument('--host', default='0.0.0.0', help='Host address to bind')
        parser.add_argument('--port', type=int, default=DEFAULT_PORT, help='Port to listen on')
        parser.add_argument('--max-fragment-size', type=int, default=3, help='Maximum fragment size')
        parser.add_argument('--protocol', choices=['gbn', 'sr'], default='gbn',
                            help='Reliable transfer protocol (Go-Back-N or Selective Repeat)')
        parser.add_argument('--window-size', type=int, default=4,
                            help='Sliding window size (number of packets in flight)')
    
        args = parser.parse_args()
    
        # Start server with provided arguments
        server = Server(
            host=args.host,
            port=args.port,
            max_fragment_size=args.max_fragment_size,
            protocol=args.protocol,
            window_size=args.window_size
        )
        
        # Use lazy loading for ServerTerminalUI to avoid circular imports
        # Only import and use it when we actually need it
        from src.terminal_ui import ServerTerminalUI
        
        # Create server terminal UI
        server_ui = ServerTerminalUI(server)
        
        # Display server status
        server_ui.show_server_status()
        
        # Start the server
        server.start()
    
    except Exception as e:
        print(f"[ERROR] An error occurred: {e}")
