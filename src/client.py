import socket
import json
import argparse
import time
from src.network_device import NetworkDevice
from src.core import settings
from src.constants.constants_client import CLIENT_LOGS, CLIENT_ERRORS
from src.core.settings import DEFAULT_PORT

#ultimo teste de vez
class Client(NetworkDevice):
    def __init__(self, server_addr='127.0.0.1', server_port=DEFAULT_PORT, protocol='gbn', max_fragment_size=3, window_size=4):
        # Call parent constructor with the new parameter name
        super().__init__(server_addr, server_port, protocol, max_fragment_size, window_size)
        
        # Client-specific attributes
        self.handshake_complete = False
        self.session_id = None
        self.is_connected = False
        # Sliding window buffers
        self.packet_buffer = {}  # Store packets that have been sent but not acknowledged
        self.ack_received = set()  # Keep track of which packets have been acknowledged
        self.last_timeout = 0  # Track when the last timeout occurred
        self.retry_count = 0    # Track retry attempts
        self.max_retries = 5    # Maximum number of retries before giving up
        
        # Simulation mode - for deterministic outcomes
        self.simulation_mode = "normal"  # Options: normal, loss, corruption, delay
        
        # For SR, window also includes base and window size
        window_start = self.base_seq_num
        window_end = window_start + self.window_size - 1
        print(CLIENT_LOGS.WINDOW_SR.format(window_start=window_start, window_end=window_end))
        # For SR, show which packets have been acked within the window
        acked_in_window = [seq for seq in self.ack_received if window_start <= seq <= window_end]
        if acked_in_window:
            print(CLIENT_LOGS.WINDOW_ACKED.format(acked_in_window=sorted(acked_in_window)))
        
        # Show packets that haven't been acked yet
        unacked = [seq for seq in range(window_start, min(self.next_seq_num, window_end + 1))
                    if seq not in self.ack_received]
        if unacked:
            print(CLIENT_LOGS.WINDOW_WAITING_ACK.format(unacked=unacked))
    
    def connect(self):
        """Establish a connection with the server using the three-way handshake protocol"""
        # No try/except here; let errors bubble up
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.connect((self.server_addr, self.server_port))

        # STEP 1: SYN - Client → Server
        print(CLIENT_LOGS.CONNECTED.format(server_addr=self.server_addr, server_port=self.server_port))
        print(CLIENT_LOGS.SENDING_SYN.format(protocol=self.protocol, max_fragment_size=self.max_fragment_size, window_size=self.window_size))
        self.handle_packet(settings.SYN_TYPE, json.dumps(self.connection_params))

        # STEP 2: Wait for SYN-ACK from Server
        print(CLIENT_LOGS.WAIT_SYNACK)
        response_packet = self._socket.recv(self.BUFFER_SIZE)
        if not response_packet:
            raise ConnectionError(CLIENT_ERRORS.NO_RESPONSE)

        parsed = self.parse_packet(response_packet)
        if not parsed:
            raise ValueError(CLIENT_ERRORS.INVALID_RESPONSE)

        # Process SYN-ACK
        syn_ack_data = json.loads(parsed['payload'])
        print(CLIENT_LOGS.RECEIVED_SYNACK.format(syn_ack_data=syn_ack_data))

        if syn_ack_data.get('status') != 'ok':
            raise ConnectionError(CLIENT_ERRORS.HANDSHAKE_FAILED.format(message=syn_ack_data.get('message', 'Unknown error')))

        # Store session information
        self.session_id = syn_ack_data.get('session_id')
        self.max_fragment_size = syn_ack_data.get('max_fragment_size', self.max_fragment_size)
        self.protocol = syn_ack_data.get('protocol', self.protocol)
        self.window_size = syn_ack_data.get('window_size', self.window_size)
        self.connection_params['max_fragment_size'] = self.max_fragment_size
        self.connection_params['protocol'] = self.protocol
        self.connection_params['window_size'] = self.window_size

        # STEP 3: ACK - Client → Server
        print(CLIENT_LOGS.SENDING_ACK)
        ack_data = {'session_id': self.session_id, 'message': 'Connection established'}
        self.handle_packet(settings.HANDSHAKE_ACK_TYPE, json.dumps(ack_data))

        self.handshake_complete = True
        self.is_connected = True
        print(CLIENT_LOGS.HANDSHAKE_SUCCESS)
        print(CLIENT_LOGS.CONNECTION_ESTABLISHED.format(protocol=self.protocol, max_fragment_size=self.max_fragment_size, window_size=self.window_size))
        return True

    def send_message(self, message):
        """Fragment and send a message using sliding window protocol with simulation modes"""
        if not self.handshake_complete or not self._socket:
            raise ConnectionError(CLIENT_ERRORS.FAILED_CONNECT.format(error='Not connected'))
        if not isinstance(message, str):
            raise ValueError(CLIENT_ERRORS.INVALID_INPUT)
        self.reset_parameters()
        fragments = self.fragment_message(message)
        print(CLIENT_LOGS.MESSAGE_FRAGMENTED.format(num_chunks=len(fragments), max_fragment_size=self.max_fragment_size))
        for seq_num, fragment in enumerate(fragments):
            self._send_fragment_with_ack(seq_num, fragment, len(fragments))
        print(CLIENT_LOGS.MESSAGE_SENT.format(num_fragments=len(fragments)))
        return True

    def _send_fragment_with_ack(self, seq_num, fragment, total_fragments):
        """Send a single fragment and wait for ACK/NACK, retrying as needed."""
        while True:
            encoded_message = fragment.encode('utf-8')
            last_packet = (seq_num == total_fragments - 1)
            data_packet = self.create_packet(settings.DATA_TYPE, encoded_message, sequence_num=seq_num, last_packet=last_packet)
            print(CLIENT_LOGS.SENDING_FRAGMENT.format(current=seq_num+1, total=total_fragments, fragment=fragment, seq_num=seq_num))
            self._socket.sendall(data_packet)
            response_packet = self._socket.recv(self.BUFFER_SIZE)
            if not response_packet:
                raise ConnectionError(CLIENT_ERRORS.NO_RESPONSE)
            parsed = self.parse_packet(response_packet)
            if not parsed:
                raise ValueError(CLIENT_ERRORS.INVALID_RESPONSE)
            if parsed['type'] == settings.ACK_TYPE and parsed['sequence'] == seq_num:
                print(CLIENT_LOGS.SERVER_ACK.format(seq_num=seq_num))
                break
            elif parsed['type'] == settings.NACK_TYPE and parsed['sequence'] == seq_num:
                print(CLIENT_LOGS.SERVER_NACK.format(seq_num=seq_num))
            else:
                raise ValueError(CLIENT_ERRORS.UNEXPECTED_RESPONSE.format(parsed=parsed))

    def reset_parameters(self):
        # Reset sequence numbers for this message
        self.base_seq_num = 0
        self.next_seq_num = 0
        self.packet_buffer.clear()
        self.ack_received.clear()
        self.last_timeout = 0
        self.retry_count = 0  # Reset retry counter for new message

    def fragment_message(self, message):
        """Fragment the message into smaller chunks based on max_fragment_size"""
        fragments = []
        for i in range(0, len(message), self.max_fragment_size):
            fragment = message[i:i + self.max_fragment_size]
            fragments.append(fragment)
        return fragments


    def process_acks(self):
        """Helper method to process acknowledgments"""
        # Let errors bubble up
        while True:
            response_packet = self._socket.recv(self.BUFFER_SIZE)
            if not response_packet:
                break
            parsed = self.parse_packet(response_packet)
            if not parsed:
                continue
            if parsed['type'] == settings.ACK_TYPE:
                self.handle_ack(parsed)
            elif parsed['type'] == settings.NACK_TYPE:
                self.handle_nack(parsed)

    def handle_ack(self, parsed):
        """Process an acknowledgment packet"""
        ack_seq = parsed.get('sequence', 0)
        
        if self.protocol == 'gbn':
            # Go-Back-N: Move the base forward
            print(CLIENT_LOGS.RECEIVED_ACK.format(ack_seq=ack_seq))
            
            if ack_seq < self.base_seq_num:
                # Duplicate or old ACK, ignore
                return
                
            # Update the base sequence number
            old_base = self.base_seq_num
            self.base_seq_num = ack_seq + 1
            
            # Clean up the buffer for acknowledged packets
            for seq in range(old_base, self.base_seq_num):
                if seq in self.packet_buffer:
                    del self.packet_buffer[seq]
            
            # Display window update
            print(CLIENT_LOGS.WINDOW_MOVED.format(old_base=old_base, old_end=old_base + self.window_size - 1, new_base=self.base_seq_num, new_end=self.base_seq_num + self.window_size - 1))
            return
            
        # Selective Repeat: Mark the specific packet as acknowledged
        print(CLIENT_LOGS.RECEIVED_ACK.format(ack_seq=ack_seq))
        
        # Mark this packet as acknowledged
        self.ack_received.add(ack_seq)
        
        # Move the base if possible
        old_base = self.base_seq_num
        while self.base_seq_num in self.ack_received:
            # Clean up the buffer for the base packet
            if self.base_seq_num in self.packet_buffer:
                del self.packet_buffer[self.base_seq_num]
            
            self.base_seq_num += 1
        
        # Display window update if it moved
        if old_base != self.base_seq_num:
            print(CLIENT_LOGS.WINDOW_MOVED.format(old_base=old_base, old_end=old_base + self.window_size - 1, new_base=self.base_seq_num, new_end=self.base_seq_num + self.window_size - 1))

    def handle_nack(self, parsed):
        """Process a negative acknowledgment packet"""
        nack_seq = parsed.get('sequence', 0)
        
        if self.protocol == 'gbn':
            # Go-Back-N: Resend all packets from base to next_seq_num - 1
            print(CLIENT_LOGS.RECEIVED_NACK.format(nack_seq=nack_seq))
            for seq in range(self.base_seq_num, self.next_seq_num):
                if seq in self.packet_buffer:
                    print(CLIENT_LOGS.RESENDING_PACKET.format(seq=seq))
                    self._socket.sendall(self.packet_buffer[seq])
            return
            
        # Selective Repeat: Resend only the NACKed packet
        print(CLIENT_LOGS.RECEIVED_NACK.format(nack_seq=nack_seq))
        
        if nack_seq in self.packet_buffer:
            print(CLIENT_LOGS.RESENDING_PACKET.format(seq=nack_seq))
            self._socket.sendall(self.packet_buffer[nack_seq])

    def disconnect(self):
        """Terminate the connection with the server gracefully"""
        if not self._socket:
            return
        print(CLIENT_LOGS.INIT_DISCONNECT)
        disconnect_packet = self.create_packet(settings.DISCONNECT_TYPE, "Disconnect")
        self._socket.sendall(disconnect_packet)
        print(CLIENT_LOGS.WAIT_DISCONNECT_ACK)
        self._socket.settimeout(2.0)
        response_packet = self._socket.recv(self.BUFFER_SIZE)
        if not response_packet:
            raise ConnectionError(CLIENT_ERRORS.NO_RESPONSE)
        print(CLIENT_LOGS.SERVER_DISCONNECT_ACK)
        self._socket.close()
        self.handshake_complete = False
        print(CLIENT_LOGS.DISCONNECTED)

if __name__ == '__main__':
    try:
        # Parse command line arguments
        parser = argparse.ArgumentParser(description='Custom Protocol Client')
        parser.add_argument('--host', default='127.0.0.1', help='Server address')
        parser.add_argument('--port', type=int, default=DEFAULT_PORT, help='Server port')
        parser.add_argument('--max-fragment-size', type=int, default=3, help='Maximum fragment size')
        parser.add_argument('--protocol', choices=['gbn', 'sr'], default='gbn', 
                           help='Reliable transfer protocol (Go-Back-N or Selective Repeat)')
        parser.add_argument('--window-size', type=int, default=4,
                           help='Sliding window size (number of packets in flight)')

        args = parser.parse_args()

        # Create client with provided arguments
        client = Client(
            server_addr=args.host,
            server_port=args.port,
            max_fragment_size=args.max_fragment_size,
            protocol=args.protocol,
            window_size=args.window_size
        )

        # Create terminal UI and run interactive session
        from src.terminal_ui import TerminalUI
        terminal = TerminalUI(client)
        terminal.configure_protocol_menu()
        while True:
            try:
                terminal.run_interactive_session()
                break  # Exit after session ends normally
            except (ConnectionError, ValueError) as e:
                print(e)
                input("\nPress Enter to retry or Ctrl+C to exit...")
            except KeyboardInterrupt:
                print("\n[LOG] Keyboard interrupt detected. Terminating client safely...")
                break
            except Exception as e:
                print(e)
                input("\nPress Enter to retry or Ctrl+C to exit...")
    except KeyboardInterrupt:
        print("\n[LOG] Keyboard interrupt detected. Terminating client safely...")
    except Exception as e:
        print(f"[ERROR] An error occurred: {e}")
