import socket
import pickle
import argparse
import time

# Constants
MSS = 1400  # Maximum Segment Size
INITIAL_CWND = 1 * MSS  # Initial congestion window size (in bytes)
THRESHOLD_CWND = 16 * MSS  # Initial slow start threshold (in bytes)
INITIAL_TIMEOUT = 1.0  # Default timeout for waiting for ACKs
RTO_MAX = 2.0
ALPHA = 0.125  # Weight for Estimated RTT
BETA = 0.25  # Weight for RTT deviation
FILENAME = "file.txt"

def send_file(server_ip, server_port):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind((server_ip, server_port))

    print(f"Server listening on {server_ip}:{server_port}")

    client_address = None

    # Initialize RTT and Timeout values
    srtt = INITIAL_TIMEOUT  # Smoothed RTT
    rttvar = 0.0  # RTT variance
    retransmit_timeout = INITIAL_TIMEOUT  # Timeout to start with

    with open(FILENAME, 'rb') as file:
        seq_num = 0  # Track the current sequence number
        cwnd = INITIAL_CWND  # Congestion window size in bytes
        threshold = THRESHOLD_CWND  # Slow start threshold
        unacked_packets = {}
        duplicate_ack_count = 0
        last_ack_received = -1
        end_signal_sent = False  # Flag to indicate if END signal was sent
        state = 0  # Congestion control state: 0 = Slow Start, 1 = Congestion Avoidance, 2 = Fast Recovery

        while True:
            # Determine how many packets to send in the current window
            window_size = cwnd // MSS  # Number of packets that fit in the window
            print(f"Current cwnd: {cwnd} bytes, sending {window_size} packets")
            while len(unacked_packets) < window_size:
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
                    duplicate_ack_count = 0

                    # Congestion control logic
                    if state == 0:  # Slow start
                        cwnd += MSS
                        print(f"cwnd increased to {cwnd} bytes (slow start)")
                        if cwnd >= threshold:
                            state = 1  # Switch to congestion avoidance

                    elif state == 1:  # Congestion avoidance
                        cwnd += MSS * (MSS / cwnd)
                        print(f"cwnd increased to {cwnd} bytes (congestion avoidance)")

                    elif state == 2:  # Fast recovery
                        cwnd = threshold
                        state = 1
                        print(f"Exiting fast recovery, cwnd set to {cwnd} bytes")

                    # Update RTT and retransmit timeout
                    if ack_seq_num in unacked_packets:
                        _, sent_time = unacked_packets[ack_seq_num]
                        rtt = time.time() - sent_time
                        print(f"RTT for packet {ack_seq_num}: {rtt}")
                        rttvar = (1 - BETA) * rttvar + BETA * abs(srtt - rtt)
                        srtt = (1 - ALPHA) * srtt + ALPHA * rtt
                        retransmit_timeout = srtt + 4 * rttvar  # Calculate new timeout
                        retransmit_timeout = max(INITIAL_TIMEOUT, min(retransmit_timeout, RTO_MAX))

                    # Remove acknowledged packets
                    for seq in list(unacked_packets.keys()):
                        if seq < ack_seq_num:
                            del unacked_packets[seq]
                else:
                    duplicate_ack_count += 1
                    print(f"Received duplicate ACK for packet {ack_seq_num}, count={duplicate_ack_count}")

                    if duplicate_ack_count >= 3 and state != 2:
                        print("3 duplicate ACKs detected! Entering fast recovery.")
                        threshold = max(cwnd // 2, MSS)
                        cwnd = threshold + 3 * MSS
                        state = 2  # Enter fast recovery
                        fast_recovery(server_socket, client_address, unacked_packets)
                        print(f"Threshold set to {threshold} bytes, cwnd set to {cwnd} bytes")
                    elif state == 2:
                        # During fast recovery
                        cwnd += MSS
                        print(f"In fast recovery, cwnd incremented to {cwnd} bytes")

            except socket.timeout:
                if unacked_packets:
                    print("Timeout occurred, initiating slow start.")
                    threshold = max(cwnd // 2, MSS)
                    cwnd = INITIAL_CWND
                    state = 0
                    retransmit_unacked_packets(server_socket, client_address, unacked_packets)
                else:
                    print("No unacked packets, transmitting new packets.")


def create_packet(seq_num, data):
    packet = {
        'seq_num': seq_num,
        'data_len': len(data),
        'data': data
    }
    print("done")
    return pickle.dumps(packet)

def retransmit_unacked_packets(server_socket, client_address, unacked_packets):
    for seq_num, (packet, _) in sorted(unacked_packets.items()):
        print(f"Retransmitting packet {seq_num}")
        server_socket.sendto(packet, client_address)
        unacked_packets[seq_num] = (packet, time.time())

def fast_recovery(server_socket, client_address, unacked_packets):
    if unacked_packets:
        earliest_seq_num = min(unacked_packets.keys())
        packet, _ = unacked_packets[earliest_seq_num]
        print(f"Fast recovery: Retransmitting packet {earliest_seq_num}")
        server_socket.sendto(packet, client_address)
        unacked_packets[earliest_seq_num] = (packet, time.time())

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Reliable UDP file server with window-based congestion control.')
    parser.add_argument('ip', help='IP address for the server to bind to')
    parser.add_argument('port', type=int, help='Port number of the server to listen on')

    args = parser.parse_args()
    send_file(args.ip, args.port)
