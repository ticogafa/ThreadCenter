import socket
import struct
import hashlib
import random
import time
import struct   
from src.core import settings
import json

class NetworkDevice:
    def __init__(self, server_addr:str, server_port:int, protocol='gbn', max_fragment_size=3, window_size=4):

        # Minimum buffer size for receiving packets (header + max payload)
        self.BUFFER_SIZE = 1024
        
        # Header size is fixed at 11 bytes
        self.HEADER_SIZE = 11
        
        # Connection parameters
        self.connection_params = {
            "protocol": protocol,
            "max_fragment_size": max_fragment_size,
            "window_size": window_size
        }
        
        self.server_addr = server_addr
        self.server_port = server_port
        self.max_fragment_size = max_fragment_size
        self.protocol = protocol
        self.window_size = window_size
        
        # Sliding window parameters
        self.base_seq_num = 0
        self.next_seq_num = 0
        self.timeout = 1.0  # Timeout in seconds
        
        # Channel simulation parameters (default: normal channel)
        self.loss_probability = 0.0
        self.corruption_probability = 0.0
        self.delay_probability = 0.0
        self.delay_time = 0.0
        
        self._socket:socket.socket #DO NOT ASSIGN HERE, IT WILL BE ASSIGNED IN THE CONNECT METHOD
    def create_packet(self, message_type, payload, sequence_num=0, last_packet=False):
        """Create a packet with header and payload, including last_packet flag as 1 byte."""
        # Ensure payload is bytes
        if isinstance(payload, str):
            payload = payload.encode('utf-8')
        payload_length = len(payload)
        # Always calculate checksum here
        
        checksum = self.calculate_checksum(payload)

        # Pack header: length (4 bytes) + type (1 byte) + seq (2 bytes) + checksum (4 bytes) + last_packet (1 byte)
        header = struct.pack('!IBH4sB', payload_length, message_type, sequence_num, checksum, int(last_packet))
        return header + payload

    def calculate_checksum(self, data):
        """Calculate a checksum for the given data (used only for received packets)."""
        if isinstance(data, str):
            data = data.encode('utf-8')
        return hashlib.md5(data).digest()[:4]
    
    def handle_packet(self, data_type, payload: str):
        """Create and send a packet with the given data type and payload"""
        data_packet = self.create_packet(data_type, payload)
        self._socket.sendall(data_packet)


    def simulate_channel(self, data, packet_index=0):
        """
        Simulate channel conditions (loss, corruption, delay) based on probabilities.
        """
        # Simulate packet loss
        if self.loss_probability == 1.0 or (self.loss_probability > 0.0 and random.random() < self.loss_probability):
            print(f"[CHANNEL] Packet lost in transmission (seq={packet_index})!")
            return None

        # Simulate packet corruption
        if self.corruption_probability == 1.0 or (self.corruption_probability > 0.0 and random.random() < self.corruption_probability):
            print(f"[CHANNEL] Packet corrupted during transmission (seq={packet_index})!")
            data = bytearray(data)
            index = random.randint(0, len(data) - 1) if len(data) > 0 else 0
            data[index] = (data[index] + 1) % 256  # Corrupt a byte
            return bytes(data)

        # Simulate network delay
        if self.delay_probability == 1.0 or (self.delay_probability > 0.0 and random.random() < self.delay_probability):
            delay = self.delay_time
            print(f"[CHANNEL] Packet delayed by {delay:.2f} seconds (seq={packet_index})")
            time.sleep(delay)

        return data

    def handle_client_messages(self, client_socket: socket.socket, client_address: str):
        """Continuously receive and process messages from a connected client."""
        received_fragments = []  # Store received fragments for message reconstruction
        attempts = 0
        while client_address in self.client_sessions:
            try:

                if attempts > settings.MAX_RETRIES:
                    print("[ERROR] Max attempts number reached, ending program execution...")
                    break

                # Receive header
                header = client_socket.recv(self.HEADER_SIZE + 1)  # header is now 12 bytes
                if not header or len(header) < self.HEADER_SIZE + 1:
                    print(f"[ERROR] Incomplete or missing header from {client_address}")
                    break

                # Parse header
                try:
                    payload_length, message_type, sequence_num, checksum, last_packet = struct.unpack('!IBH4sB', header)
                except struct.error     as e:
                    print(f"[ERROR] Failed to unpack header from {client_address}: {e}")
                    break

                # Receive payload
                payload = client_socket.recv(payload_length)
                if len(payload) < payload_length:
                    print(f"[ERROR] Incomplete payload received from {client_address}")
                    break

            # Handle special channel config packet (message_type 99)
                try:
                    config = json.loads(payload.decode('utf-8'))
                    print(f"[CONFIG] Received channel config from client: {config}")
                    self.set_channel_conditions(
                        loss_prob=float(config.get('loss_prob', 0.0)),
                        corruption_prob=float(config.get('corruption_prob', 0.0)),
                        delay_prob=float(config.get('delay_prob', 0.0)),
                        delay_time=float(config.get('delay_time', 0.0))
                    )
                    print("[CONFIG] Channel conditions updated on server.")
                except Exception as e:
                    print(f"[ERROR] Failed to parse channel config: {e}")

                if message_type == settings.ERROR_CODE:
                    continue

                # Simulate channel conditions
                processed_payload = self.simulate_channel(payload, sequence_num)
                
                if processed_payload is None:
                    print(f"[CHANNEL] Packet from {client_address} lost in simulated channel.")
                    if hasattr(self, 'simulate_loss_and_nack'):
                        self.simulate_loss_and_nack(client_socket, sequence_num)
                        attempts+=1
                    continue

                # Verify checksum
                calculated_checksum = self.calculate_checksum(processed_payload)
                if calculated_checksum != checksum:
                    print(f"[ERROR] Checksum mismatch for packet {sequence_num} from {client_address}")
                    if hasattr(self, 'simulate_corruption_and_nack'):
                        self.simulate_corruption_and_nack(client_socket, sequence_num, payload)
                        attempts+=1
                    continue

                # Process message based on type
                if message_type == settings.DATA_TYPE:
                    try:
                        decoded_message = self.simulate_channel(payload, sequence_num).decode('utf-8')
                        print(f"[LOG] Received message fragment from {client_address}: {decoded_message}")
                        received_fragments.append(decoded_message)
                    except Exception:
                        print(f"[LOG] Received binary data from {client_address}: {len(payload)} bytes")
                        received_fragments.append(payload)
                    ack_packet = self.create_packet(settings.ACK_TYPE, f"ACK for seq {sequence_num}", sequence_num=sequence_num)
                    client_socket.sendall(ack_packet)
                    print(f"[LOG] Sent ACK for sequence {sequence_num}")
                    attempts = 0

                    if last_packet:
                        if all(isinstance(frag, str) for frag in received_fragments):
                            full_message = ''.join(received_fragments)
                            print(f"[RECONSTRUCTED] Full message from {client_address}: {full_message}")
                        else:
                            print(f"[RECONSTRUCTED] Received binary fragments from {client_address} (not shown as text)")

                        received_fragments = []

                elif message_type == settings.DISCONNECT_TYPE:
                    if self.handle_disconnect(client_socket, client_address):
                        print(f"[LOG] Client {client_address} disconnected successfully.")
                        break

                else:
                    print(f"[ERROR] Unknown message type {message_type} from {client_address}")

                if hasattr(self, 'simulate_delay'):
                    self.simulate_delay()

            except Exception as e:
                print(f"[ERROR] Error handling messages from {client_address}: {e}")
                break



        # Clean up session
        if client_address in self.client_sessions:
            del self.client_sessions[client_address]

        try:
            client_socket.close()
            print(f"[LOG] Connection with {client_address} closed.")
        except Exception as e:
            print(f"[ERROR] Failed to close connection with {client_address}: {e}")
        
    def parse_packet(self, packet):
        """Parse a received packet into its components"""
        # Check if packet is at least as long as the header (now 12 bytes)
        header_size = self.HEADER_SIZE + 1  # 11 + 1 for last_packet
        if len(packet) < header_size:
            print(f"[ERROR] Received packet too small: {len(packet)} bytes, expected at least {header_size} bytes")
            return None
        
        # Extract header (12 bytes total)
        header = packet[:header_size]
        
        payload_length, message_type, sequence_num, checksum, last_packet = struct.unpack('!IBH4sB', header)
        
        # Check if we have enough data for the payload
        if len(packet) < header_size + payload_length:
            print(f"[ERROR] Incomplete packet: expected {header_size + payload_length} bytes, got {len(packet)} bytes")
            return None
        
        # Extract payload
        payload = packet[header_size:header_size+payload_length]
        
        # Verify checksum
        calculated_checksum = self.calculate_checksum(payload)
        if calculated_checksum != checksum:
            print("[ERROR] Checksum verification failed!")
            return None
            
        return {
            'type': message_type,
            'sequence': sequence_num,
            'payload': payload,
            'length': payload_length,
            'last_packet': bool(last_packet)
        }

    def set_channel_conditions(self, loss_prob=0.0, corruption_prob=0.0, delay_prob=0.0, delay_time=0.0):
        """Set the channel conditions for simulation"""
        self.loss_probability = max(0.0, min(1.0, loss_prob))
        self.corruption_probability = max(0.0, min(1.0, corruption_prob))
        self.delay_probability = max(0.0, min(1.0, delay_prob))
        self.delay_time = max(0.0, delay_time)
        
        # Determine simulation mode based on probabilities
        if self.loss_probability == 1.0:
            mode = "Packet Loss"
            print("[CONFIG] Simulating 100% packet loss. All packets will be dropped.")
            
            # Simulate packet loss and send NACK
            def simulate_loss_and_nack(client_socket, sequence_num):
                print(f"[CHANNEL] Simulating packet loss for sequence {sequence_num}")
                nack_packet = self.create_packet(settings.NACK_TYPE, f"NACK for seq {sequence_num}", sequence_num=sequence_num)
                client_socket.sendall(nack_packet)
                print(f"[LOG] Sent NACK for sequence {sequence_num}")
            
            self.simulate_loss_and_nack = simulate_loss_and_nack  # Attach function dynamically

        elif self.corruption_probability == 1.0:
            mode = "Packet Corruption"
            print("[CONFIG] Simulating 100% packet corruption. All packets will be corrupted.")
            
            # Simulate packet corruption and send NACK
            def simulate_corruption_and_nack(client_socket, sequence_num, payload):
                print(f"[CHANNEL] Simulating packet corruption for sequence {sequence_num}")
                corrupted_payload = bytearray(payload)
                if len(corrupted_payload) > 0:
                    corrupted_payload[0] = (corrupted_payload[0] + 1) % 256  # Corrupt the first byte
                nack_packet = self.create_packet(settings.NACK_TYPE, f"NACK for seq {sequence_num}", sequence_num=sequence_num)
                client_socket.sendall(nack_packet)
                print(f"[LOG] Sent NACK for sequence {sequence_num}")
            
            self.simulate_corruption_and_nack = simulate_corruption_and_nack  # Attach function dynamically

        elif self.delay_probability == 1.0:
            mode = "Network Delay"
            print(f"[CONFIG] Simulating 100% network delay. All packets will be delayed by {self.delay_time:.2f} seconds.")
            
            # Simulate delay
            def simulate_delay():
                print(f"[CHANNEL] Simulating network delay of {self.delay_time:.2f} seconds.")
                time.sleep(self.delay_time)
            
            self.simulate_delay = simulate_delay  # Attach function dynamically

        elif self.loss_probability == 0.0 and self.corruption_probability == 0.0 and self.delay_probability == 0.0:
            mode = "Normal"
            print("[CONFIG] Normal mode. No packet loss, corruption, or delay.")
        else:
            mode = "Custom"
            print(f"[CONFIG] Custom mode: loss={self.loss_probability}, corruption={self.corruption_probability}, delay={self.delay_probability}, delay_time={self.delay_time}s")
        
        print(f"[CONFIG] Channel set to {mode} mode.")

    def update_simulation_params(self, loss_prob=0.0, corruption_prob=0.0, delay_prob=0.0, delay_time=0.0):
        """Update local simulation parameters for status display (client-side only)."""
        self.loss_probability = loss_prob
        self.corruption_probability = corruption_prob
        self.delay_probability = delay_prob
        self.delay_time = delay_time

# Example usage of the NetworkDevice class
device = NetworkDevice("127.0.0.1", 8080)
device.set_channel_conditions(loss_prob=1.0)  # Simula 100% de perda de pacotes
device.set_channel_conditions(corruption_prob=1.0)  # Simula 100% de corrupção
device.set_channel_conditions(delay_prob=1.0, delay_time=2.0)  # Simula 100% de atraso com 2 segundos