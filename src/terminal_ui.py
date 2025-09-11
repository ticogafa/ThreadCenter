import os
from src.client import Client
# Remove the direct import from server
from typing import TYPE_CHECKING
import json

from src.core import settings
from src.constants.constants_client import CLIENT_LOGS, CLIENT_ERRORS
# Use conditional imports to prevent circular dependencies
if TYPE_CHECKING:
    from src.server import Server

class TerminalUI:
    def __init__(self, client: Client):
        """Initialize the terminal UI with a reference to the client"""
        self.client = client

    def clear_screen(self):
        """Clear the terminal screen"""
        os.system('cls' if os.name == 'nt' else 'clear')

    def run_interactive_session(self):
        """Main entry point that orchestrates the user interface"""
        self.clear_screen()

        if not self.client.connect():
            print("[ERROR] Unable to establish connection. Exiting...")
            return
        self.clear_screen()
        while True:
            self.show_main_menu()
            choice = input("\nSelect an option (1-6): ").strip()

            if choice == '1':
                self.send_message_menu()
            elif choice == '2':
                self.configure_window_menu()
            elif choice == '3':
                self.configure_simulation_menu()
            elif choice == '4':
                self.show_status()
                input("\nPress Enter to continue...")
            elif choice == '5':
                self.reset_simulation()
                input("\nSimulation reset to normal mode. Press Enter to continue...")
            elif choice == '6':
                break
            else:
                print("[ERROR] Invalid option. Please try again.")
                input("\nPress Enter to continue...")

            self.clear_screen()

        print("[LOG] Interactive session ended. Disconnecting...")
        self.client.disconnect()  # type: ignore

    def show_main_menu(self):
        """Display the main menu options"""
        print("\n===== MAIN MENU =====")
        print("Your current protocol {}".format(self.client.protocol.upper()))
        print("1. Send Message")
        print("2. Configure Window Size (current: {})".format(self.client.window_size))
        print("3. Configure Simulation Mode (current: {})".format(self.client.simulation_mode.capitalize()))
        print("4. Show Status")
        print("5. Reset Simulation")
        print("6. Exit")

    def send_message_menu(self):
        """Menu for sending a message"""
        self.clear_screen()
        print("\n===== SEND MESSAGE =====")
        message = input("Enter message to send: ")

        if not message:
            print("[ERROR] Message cannot be empty.")
            input("\nPress Enter to continue...")
            return

        print("\nSending message in {} simulation mode...".format(self.client.simulation_mode.capitalize()))
        success = self.client.send_message(message)
        if success:
            print("[LOG] Message sent successfully!")
        else:
            print("[ERROR] Failed to send the message.")
        input("\nPress Enter to continue...")

    def configure_protocol_menu(self):
        """Menu for configuring the protocol type"""

        print("\n===== Configure Protocol Before Connection =====")

        while True:
            self.clear_screen()
            print("\n===== CONFIGURE PROTOCOL =====")
            print("1. Go-Back-N (GBN)")
            print("2. Selective Repeat (SR)")

            choice = input("\nSelect protocol (1-2): ").strip()

            if choice == '1':
                self.client.protocol = 'gbn'
                self.client.connection_params['protocol'] = 'gbn'
                print("[CONFIG] Protocol set to Go-Back-N (GBN)")
                break
            elif choice == '2':
                self.client.protocol = 'sr'
                self.client.connection_params['protocol'] = 'sr'
                print("[CONFIG] Protocol set to Selective Repeat (SR)")
                break
            else:
                print("[ERROR] Invalid option. Please select a valid protocol.")
                input("\nPress Enter to try again...")

        input("\nPress Enter to continue...")

    def configure_window_menu(self):
        """Menu for configuring the window size and timeout"""
        self.clear_screen()
        print("\n===== CONFIGURE WINDOW =====")
        print("Current window size: {}".format(self.client.window_size))
        print("Current timeout: {:.1f} seconds".format(self.client.timeout))

        try:
            new_size = input("\nEnter new window size (1-10, or Enter to keep current): ").strip()
            if new_size:
                new_size = int(new_size)
                if 1 <= new_size <= 10:
                    self.client.window_size = new_size
                    self.client.connection_params["window_size"] = new_size
                    print(f"[CONFIG] Window size set to {new_size}")
                else:
                    print("[ERROR] Window size must be between 1 and 10.")

            new_timeout = input("Enter new timeout in seconds (0.1-10.0, or Enter to keep current): ").strip()
            if new_timeout:
                new_timeout = float(new_timeout)
                if 0.1 <= new_timeout <= 10.0:
                    self.client.timeout = new_timeout
                    print(f"[CONFIG] Timeout set to {new_timeout} seconds")
                else:
                    print("[ERROR] Timeout must be between 0.1 and 10.0 seconds.")

        except ValueError:
            print("[ERROR] Invalid input. Values must be numbers.")

        input("\nPress Enter to continue...")

    def configure_simulation_menu(self):
        """Menu for configuring the simulation mode"""
        self.clear_screen()
        print("\n===== CONFIGURE SIMULATION MODE =====")
        print("1. Normal (reliable channel)")
        print("2. Packet Loss (100% loss probability)")
        print("3. Packet Corruption (100% corruption probability)")
        print("4. Network Delay (1 second delay)")
        print("5. Back to Main Menu")

        choice = input("\nSelect simulation mode (1-5): ").strip()

        # Default values
        loss_prob = corruption_prob = delay_prob = delay_time = 0.0
        mode = "normal"
        if choice == '1':
            mode = "normal"
        elif choice == '2':
            mode = "loss"
            loss_prob = 1.0
        elif choice == '3':
            mode = "corruption"
            corruption_prob = 1.0
        elif choice == '4':
            mode = "delay"
            delay_prob = delay_time = 1.0
        elif choice == '5':
            return
        else:
            print("[ERROR] Invalid option.")
            input("\nPress Enter to continue...")
            return

        # Update local simulation mode for UI only
        self.client.simulation_mode = mode
        self.client.update_simulation_params(loss_prob, corruption_prob, delay_prob, delay_time)
        print(f"[CONFIG] Simulation mode set to {mode.capitalize()}")

        # Send configuration packet to server
        try:
            config_data = {
                'type': 'channel_config',
                'loss_prob': loss_prob,
                'corruption_prob': corruption_prob,
                'delay_prob': delay_prob,
                'delay_time': delay_time
            }
            # Use a reserved message type, e.g., 99
            config_packet = self.client.create_packet(settings.ERROR_CODE, json.dumps(config_data))
            self.client._socket.sendall(config_packet)

            print("[CONFIG] Channel configuration sent to server.")
        except Exception as e:
            print(f"[ERROR] Failed to send channel config to server: {e}")
        input("\nPress Enter to continue...")

    def show_status(self):
        """Display current protocol and simulation status"""
        self.clear_screen()
        print("\n===== PROTOCOL STATUS =====")
        print(f"Protocol: {self.client.protocol.upper()}")
        print(f"Window size: {self.client.window_size} packets")
        print(f"Timeout: {self.client.timeout}s")
        print(f"Fragment size: {self.client.max_fragment_size} characters")
        print(f"Base sequence: {self.client.base_seq_num}")
        print(f"Next sequence: {self.client.next_seq_num}")

        print("\n===== SIMULATION STATUS =====")
        print(f"Simulation mode: {self.client.simulation_mode.capitalize()}")
        print(f"Loss probability: {self.client.loss_probability:.2f}")
        print(f"Corruption probability: {self.client.corruption_probability:.2f}")
        print(f"Delay probability: {self.client.delay_probability:.2f}")
        print(f"Delay time: {self.client.delay_time:.2f}s")

        print("\n===== CONNECTION STATUS =====")
        print(f"Connected: {'Yes' if self.client.is_connected else 'No'}")
        print(f"Server address: {self.client.server_addr}:{self.client.server_port}")
        print(f"Session ID: {self.client.session_id if self.client.session_id else 'N/A'}")

    def reset_simulation(self):
        """Reset simulation to normal mode"""
        self.client.simulation_mode = "normal"
        loss_prob = 0
        corruption_prob = 0
        delay_prob = 0
        delay_time = 0

        self.client.set_channel_conditions(loss_prob, corruption_prob, delay_prob, delay_time)
        self.client.update_simulation_params(loss_prob, corruption_prob, delay_prob, delay_time)
        self.client.connect()
        config_data = {
            'type': 'channel_config',
            'loss_prob': loss_prob,
            'corruption_prob': corruption_prob,
            'delay_prob': delay_prob,
            'delay_time': delay_time
        }
        # Use the reserved config message type, not DATA_TYPE, and do not set last_packet
        config_packet = self.client.create_packet(settings.ERROR_CODE, json.dumps(config_data))
        self.client._socket.sendall(config_packet)
        self.clear_screen()
        print("[CONFIG] Simulation reset to normal mode")


# Server Terminal UI class
class ServerTerminalUI:
    def __init__(self, server):
        """Initialize the terminal UI with a reference to the server"""
        self.server = server

    def clear_screen(self):
        """Clear the terminal screen"""
        os.system('cls' if os.name == 'nt' else 'clear')

    def show_server_status(self):
        """Display current server status"""
        self.clear_screen()
        print("\n===== SERVER STATUS =====")
        print(f"Server running at: {self.server.host}:{self.server.port}")
        print(f"Protocol: {self.server.protocol.upper()}")
        print(f"Max Fragment Size: {self.server.max_fragment_size} characters")
        print(f"Window Size: {self.server.window_size} packets")

        print("\n===== ACTIVE CONNECTIONS =====")
        if not self.server.client_sessions:
            print("No active connections")
        else:
            for addr, session in self.server.client_sessions.items():
                print(f"\nClient: {addr}")
                print(f"  Session ID: {session.get('session_id', 'N/A')}")
                print(f"  Protocol: {session.get('protocol', 'N/A')}")
                print(f"  Max Fragment Size: {session.get('max_fragment_size', 'N/A')}")
                print(f"  Handshake Complete: {'Yes' if session.get('handshake_complete', False) else 'No'}")
                print(f"  Expected Sequence: {session.get('expected_seq_num', 'N/A')}")