import socket
import argparse
import json
import pickle

# Constants
MSS = 1400  # Maximum Segment Size

def receive_file(server_ip, server_port):
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_socket.settimeout(2)

    server_address = (server_ip, server_port)
    expected_seq_num = 0
    output_file_path = "received_file.txt"
    buffer = {}

    with open(output_file_path, 'wb') as file:
        connection_established = False

        while True:
            try:
                if not connection_established:
                    print("Sending START signal...")
                    client_socket.sendto(b"START", server_address)
                    connection_established = True
                    continue

                packet, _ = client_socket.recvfrom(MSS + 100)

                if packet == b"END":
                    print("Received END signal from server, sending END_ACK")
                    client_socket.sendto(b"END_ACK", server_address)  # Acknowledge the END signal
                    break
                
                seq_num, data_len, data = parse_packet(packet)

                if seq_num == expected_seq_num:
                    file.write(data)
                    print(f"Received packet {seq_num}, writing to file")
                    expected_seq_num += data_len

                    # Write any buffered packets in order
                    while expected_seq_num in buffer:
                        file.write(buffer[expected_seq_num])
                        print(f"Writing buffered packet {expected_seq_num}")
                        length = len(buffer[expected_seq_num])
                        del buffer[expected_seq_num]  # Safe deletion, key exists
                        expected_seq_num += length
                    # Send ACK for the last correctly received packet
                    send_ack(client_socket, server_address, expected_seq_num)
                
                else:
                    # Only store out-of-order packets in the buffer
                    if seq_num not in buffer:
                        buffer[seq_num] = data
                        print(f"Out of order packet {seq_num} buffered")
                    # Send ACK for the last correctly received packet
                    send_ack(client_socket, server_address, expected_seq_num)
            
            except socket.timeout:
                print("Timeout waiting for data")
                # Retransmit the ACK for the last correctly received packet
                send_ack(client_socket, server_address, expected_seq_num)

def parse_packet(packet_bytes):
    try:
        # Deserialize the received packet bytes back into a dictionary
        packet_data = pickle.loads(packet_bytes)
        
        # Extract the fields from the packet dictionary
        seq_num = packet_data['seq_num']
        data_len = packet_data['data_len']
        data = packet_data['data']
        
        # Return the packet fields
        return seq_num, data_len, data
    
    except (pickle.UnpicklingError, KeyError) as e:
        print(f"Failed to parse packet: {e}")
        return None, None, None              # Return all fields
    
def send_ack(client_socket, server_address, seq_num):
    # Send ACK for the received sequence number
    ack_packet = str(seq_num).encode()  # Just the expected sequence number
    client_socket.sendto(ack_packet, server_address)
    print(f"Sent ACK for expected packet {seq_num}")

if __name__ == "__main__":
    print("Starting client")
    parser = argparse.ArgumentParser(description='Reliable file receiver over UDP.')
    parser.add_argument('server_ip', help='IP address of the server')
    parser.add_argument('server_port', type=int, help='Port number of the server')

    args = parser.parse_args()

    receive_file(args.server_ip, args.server_port)