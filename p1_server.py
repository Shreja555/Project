import socket
import time
import argparse
import pickle

# Constants
MSS = 1400  # Maximum Segment Size for each packet
WINDOW_SIZE = 5  # Number of packets in flight
DUP_ACK_THRESHOLD = 3  # Threshold for duplicate ACKs to trigger fast recovery
FILE_PATH = "file.txt"  # Set your file path here
TIMEOUT = 1.0  # Initialize timeout to some value
MAX_RTO = 2.0
ALPHA = 0.125  # Factor for updating SRTT
BETA = 0.25  # Factor for updating RTTVAR

def send_file(server_ip, server_port, enable_fast_recovery):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind((server_ip, server_port))

    print(f"Server listening on {server_ip}:{server_port}")

    client_address = None

    # Initialize RTT and Timeout values
    srtt = TIMEOUT  # Smoothed RTT
    rttvar = 0.0  # RTT variance
    retransmit_timeout = TIMEOUT  # Timeout to start with

    with open(FILE_PATH, 'rb') as file:
        seq_num = 0
        window_base = 0
        unacked_packets = {}
        duplicate_ack_count = 0
        last_ack_received = -1
        end_signal_sent = False  # Flag to indicate if END signal was sent

        while True:
            # Send packets while within the window size
            while len(unacked_packets) < WINDOW_SIZE:
                chunk = file.read(MSS)
                if not chunk:
                    # End of file
                    if not end_signal_sent and len(unacked_packets) == 0:
                        server_socket.sendto(b"END", client_address)
                        end_signal_sent = True
                        print("Sent END signal")
                    break

                packet = create_packet(seq_num, chunk)
                if client_address:
                    server_socket.sendto(packet, client_address)
                    print(f"Sending packet {seq_num}")
                else:
                    data, client_address = server_socket.recvfrom(1024)
                    if data == b"START":
                        print(f"Connection established with client {client_address}")
                        server_socket.sendto(packet, client_address)
                        print(f"Sending packet {seq_num}")

                unacked_packets[seq_num] = (packet, time.time())
                seq_num += len(chunk)

            try:
                server_socket.settimeout(retransmit_timeout)
                ack_packet, _ = server_socket.recvfrom(1024)
                ack_packet_decoded = ack_packet.decode()

                # Check if the received packet is a valid ACK or a control message
                if ack_packet_decoded == "START":
                    print("Received START signal from client, continuing...")
                    continue  # Just ignore the START message

                if ack_packet_decoded == "END_ACK":
                    print("Received END acknowledgment from client")
                    break  # Exit the loop on END_ACK

                ack_seq_num = int(ack_packet_decoded)  # Expecting the next expected sequence number

                if ack_seq_num > last_ack_received:
                    print(f"Received cumulative ACK for packet {ack_seq_num}")
                    last_ack_received = ack_seq_num

                    if ack_seq_num in unacked_packets:
                        _, sent_time = unacked_packets[ack_seq_num]
                        rtt = time.time() - sent_time
                        print(f"RTT for packet {ack_seq_num}: {rtt}")
                        rttvar = (1 - BETA) * rttvar + BETA * abs(srtt - rtt)
                        srtt = (1 - ALPHA) * srtt + ALPHA * rtt
                        retransmit_timeout = srtt + 4 * rttvar  # Calculate new timeout
                        # Cap retransmit_timeout at the maximum threshold
                        retransmit_timeout = max(TIMEOUT, min(retransmit_timeout, MAX_RTO))
                        print(retransmit_timeout)

                    # Delete all packets with seq_num < ack_seq_num from unacked_packets
                    for seq in list(unacked_packets.keys()):
                        if seq < ack_seq_num:
                            del unacked_packets[seq]  # Remove acknowledged packet
                    
                    window_base = ack_seq_num  # Update the window base to the acknowledged sequence number
                    duplicate_ack_count = 0 
                else:
                    duplicate_ack_count += 1
                    print(f"Received duplicate ACK for packet {ack_seq_num}, count={duplicate_ack_count}")
                    if enable_fast_recovery and duplicate_ack_count >= DUP_ACK_THRESHOLD:
                        print("Entering fast recovery mode")
                        fast_recovery(server_socket, client_address, unacked_packets)
                        duplicate_ack_count = 0  # Reset after fast recovery retransmission

            except socket.timeout:
                print("Timeout occurred, retransmitting unacknowledged packets")
                duplicate_ack_count = 0
                retransmit_unacked_packets(server_socket, client_address, unacked_packets)
                if end_signal_sent:
                    server_socket.sendto(b"END", client_address)
                    print("Retransmitting END signal")

def create_packet(seq_num, data):
    # Create a dictionary representing the packet
    packet = {
        'seq_num': seq_num,           # Sequence number of the first byte
        'data_len': len(data),        # Length of the data in bytes
        'data': data                  # Actual data as bytes
    }
    
    # Serialize the dictionary using pickle to prepare it for sending over UDP
    return pickle.dumps(packet)

def retransmit_unacked_packets(server_socket, client_address, unacked_packets):
    for seq_num, (packet, _) in sorted(unacked_packets.items()):
        print(f"Retransmitting packet {seq_num}")
        server_socket.sendto(packet, client_address)
        # Optionally update the timestamp for this packet
        unacked_packets[seq_num] = (packet, time.time())

def fast_recovery(server_socket, client_address, unacked_packets):           
    """
    Retransmit the earliest unacknowledged packet (fast recovery).
    """
    if unacked_packets:
        # Find the earliest unacknowledged packet
        earliest_seq_num = min(unacked_packets.keys())
        packet, _ = unacked_packets[earliest_seq_num]
        
        # Retransmit the packet
        print(f"Fast recovery: Retransmitting earliest unacknowledged packet {earliest_seq_num}")
        server_socket.sendto(packet, client_address)
        
        # Optionally update the timestamp for this packet
        unacked_packets[earliest_seq_num] = (packet, time.time())


if __name__ == "__main__":
    print("Starting server")

    parser = argparse.ArgumentParser(description='Reliable file transfer server over UDP.')
    parser.add_argument('server_ip', help='IP address of the server')
    parser.add_argument('server_port', type=int, help='Port number of the server')
    parser.add_argument('fast_recovery', type=int, help='Enable fast recovery (1 for true, 0 for false)')

    args = parser.parse_args()

    send_file(args.server_ip, args.server_port, args.fast_recovery)