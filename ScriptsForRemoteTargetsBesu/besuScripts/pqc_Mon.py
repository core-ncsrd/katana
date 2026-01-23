import pyshark
import sys
import datetime
import json
import struct
import binascii
import socket
import time
import argparse
import threading

# --- CONFIGURATION ---
FILTER_IP = ""
UDP_TARGET_PORT = 5005
BURST_TIMEOUT = 0.5  # If no packets for 0.5s, send the report immediately

# --- SHARED STATE ---
session_db = {}          # Tracks the CURRENT active burst of packets
request_end_times = {}   # Tracks latency context (Persistent across bursts)
db_lock = threading.Lock() # Protects access to the shared data

# --- PROTOCOL MAPPING ---
CHARON_EXCHANGE_MAP = {
    34: 'IKE_SA_INIT',
    35: 'IKE_AUTH',
    36: 'CREATE_CHILD_SA',
    37: 'INFORMATIONAL',
    43: 'IKE_INTERMEDIATE',
    44: 'IKE_FOLLOWUP_KE',
    53: 'ENCRYPTED_FRAGMENT' 
}

def parse_raw_ike_header(udp_payload_hex):
    """
    Manually extracts SPI, Message ID, and Exchange Type from raw bytes.
    This fixes the 'Unknown Direction' issue on fragments.
    """
    try:
        if not udp_payload_hex: return None
        data = binascii.unhexlify(udp_payload_hex.replace(':', ''))
        
        # Check for Non-ESP Marker (4 bytes of zeros)
        if len(data) < 28 or data[0:4] != b'\x00\x00\x00\x00': return None 

        # Extract Fields based on RFC 7383 / IKEv2
        # Bytes 4-12: Initiator SPI (8 bytes)
        # Bytes 22: Exchange Type
        # Bytes 24-28: Message ID
        
        spi_bytes = data[4:12]
        spi_hex = binascii.hexlify(spi_bytes).decode('utf-8')
        
        exch_type = data[22]
        msg_id = struct.unpack('>I', data[24:28])[0]
        
        return {
            "spi": spi_hex,
            "msg_id": msg_id,
            "exch_type": exch_type,
            "exch_name": CHARON_EXCHANGE_MAP.get(exch_type, f"Type_{exch_type}")
        }
    except Exception:
        return None

def get_pqc_algo_name(msg_id, frag_count, total_bytes):
    if total_bytes > 30000: return "FRODO_KEM / McEliece (Heavy)"
    if msg_id == 6 and frag_count >= 10: return "FRODO_KEM (12 Frags)"
    if msg_id == 4: return "Kyber/BIKE + Dilithium"
    if msg_id == 3: return "BIKE/HQC (Key Exchange)"
    return "Standard/Unknown"

# --- REPORTER THREAD ---
def reporter_loop(target_ip):
    """Checks every 0.1s for completed bursts and sends them instantly."""
    print("--- BACKGROUND REPORTER STARTED ---")
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    while True:
        time.sleep(0.1) # High-speed polling
        current_time = time.time()
        
        with db_lock:
            # Identify completed flows
            completed_keys = []
            for key, data in session_db.items():
                if current_time - data["last_packet_time"] > BURST_TIMEOUT:
                    completed_keys.append(key)
            
            # Process and Send
            for key in completed_keys:
                data = session_db.pop(key) # Remove from DB immediately
                
                meta = data["meta"]
                stats = data["stats"]
                
                algo = get_pqc_algo_name(meta["msg_id"], stats["fragment_count"], stats["total_bytes"])
                
                # Format Packet List
                packet_list = []
                for p in data["packets"]:
                    packet_list.append({
                        "timestamp": p["timestamp"],
                        "packet_size": p["size"],
                        "fragment_index": p["frag_seq"],
                        "correlation_tag": f"{meta['exchange']} {meta['direction']} {meta['msg_id']} [ EF({p['frag_seq']}/{stats['fragment_count']}) ]"
                    })

                report = {
                    "timestamp": datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3],
                    "burst_summary": {
                        "exchange_type": meta["exchange"],
                        "message_id": meta["msg_id"],
                        "packet_count": stats["fragment_count"],
                        "total_key_size": f"{stats['total_bytes']}",
                        "is_fragmented": stats["fragment_count"] > 1,
                        "processing_latency_ms": data.get("latency_ms", "N/A")
                    },
                    "identified_pqc_algorithm": algo,
                    "connection_info": { 
                        "src_ip": meta["src"], 
                        "dst_ip": meta["dst"],
                        "direction": meta["direction"] 
                    },
                    "charon_log_correlation": {
                        "log_event_match": f"{meta['direction']} {meta['exchange']} {meta['msg_id']}",
                        "log_note": f"Size: {stats['total_bytes']} bytes | Latency: {data.get('latency_ms', 'N/A')} ms"
                    },
                    "packets": packet_list
                }
                
                # Send (Non-blocking call to socket)
                try:
                    payload = json.dumps(report).encode('utf-8')
                    sock.sendto(payload, (target_ip, UDP_TARGET_PORT))
                    print(f"\n[>>] SENT: {meta['exchange']} ({stats['fragment_count']} pkts)")
                except Exception as e:
                    print(f"[!] Send Error: {e}")

# --- MAIN CAPTURE LOOP ---
def start_monitor(interface, target_ip):
    print(f"--- REAL-TIME PQC MONITOR ON: {interface} ---")
    print(f"--- LATENCY TRACKING: ACTIVE ---")
    print(f"--- TARGET: {target_ip}:{UDP_TARGET_PORT} ---")

    # Start Reporter Thread
    t = threading.Thread(target=reporter_loop, args=(target_ip,), daemon=True)
    t.start()

    initiators = {}
    
    bpf_filter = f'(udp.port==500 or udp.port==4500) and ip.addr != {FILTER_IP}'
    capture = pyshark.LiveCapture(interface=interface, display_filter=bpf_filter)

    try:
        for pkt in capture.sniff_continuously():
            if 'ip' not in pkt: continue
            
            src = pkt.ip.src
            dst = pkt.ip.dst
            length = int(pkt.length)
            pkt_timestamp = float(pkt.sniff_timestamp)
            time_str = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]

            # 1. PARSE HEADER
            msg_id = -1
            exch_name = "Unknown"
            spi = "Unknown"
            
            # Try Pyshark
            if hasattr(pkt, 'isakmp'):
                spi = getattr(pkt.isakmp, 'ispis', getattr(pkt.isakmp, 'spi', '0'))
                try:
                    msg_id = int(getattr(pkt.isakmp, 'msgid', -1))
                    exch_type = int(getattr(pkt.isakmp, 'exch_type', 0))
                    exch_name = CHARON_EXCHANGE_MAP.get(exch_type, f"Type_{exch_type}")
                except: pass

            # Try Manual (For Fragments) - Gets SPI correctly now
            if (msg_id <= 0 or exch_name == "Type_0") and hasattr(pkt, 'udp') and hasattr(pkt.udp, 'payload'):
                raw = parse_raw_ike_header(pkt.udp.payload)
                if raw:
                    msg_id = raw['msg_id']
                    exch_name = raw['exch_name']
                    spi = raw['spi'] # <--- CRITICAL FIX

            if msg_id < 0: continue

            # 2. DETERMINE DIRECTION
            if spi and spi != '0' and spi != 'Unknown':
                if spi not in initiators: initiators[spi] = src
                direction = "request" if src == initiators[spi] else "response"
            else:
                direction = "unknown"

            # 3. LATENCY & STATE MANAGEMENT (Thread Safe)
            with db_lock:
                tracker_key = f"{spi}_{msg_id}"
                latency_val = "N/A"

                # A. Update Latency Tracker
                if direction == "request":
                    request_end_times[tracker_key] = pkt_timestamp
                
                # B. Calculate Latency on Response
                elif direction == "response" and tracker_key in request_end_times:
                    start_response = pkt_timestamp
                    end_request = request_end_times[tracker_key]
                    delta_ms = (start_response - end_request) * 1000.0
                    latency_val = round(delta_ms, 2)
                    # Clean up tracker immediately to prevent reuse
                    del request_end_times[tracker_key] 

                # C. Update Session DB
                flow_key = f"{spi}_{msg_id}_{direction}"
                
                if flow_key not in session_db:
                    session_db[flow_key] = {
                        "meta": { "msg_id": msg_id, "exchange": exch_name, "direction": direction, "src": src, "dst": dst },
                        "stats": { "fragment_count": 0, "total_bytes": 0 },
                        "packets": [],
                        "last_packet_time": 0,
                        "latency_ms": "N/A"
                    }
                
                # If we found latency, attach it to the flow
                if latency_val != "N/A":
                    session_db[flow_key]["latency_ms"] = latency_val
                    print(f"\n[★] LATENCY CAPTURED: {latency_val} ms")

                # Add Packet Data
                entry = session_db[flow_key]
                entry["stats"]["fragment_count"] += 1
                entry["stats"]["total_bytes"] += length
                entry["last_packet_time"] = time.time()
                
                frag_num = entry["stats"]["fragment_count"]
                
                entry["packets"].append({
                    "timestamp": time_str,
                    "size": length,
                    "frag_seq": frag_num
                })

                # Print simplified status
                print(f"\r[+] {exch_name} ID:{msg_id} Frag:{frag_num:<2} (Lat: {entry.get('latency_ms', 'N/A')})   ", end="")

    except KeyboardInterrupt:
        print("\nStopping...")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("interface")
    parser.add_argument("target_ip")
    args = parser.parse_args()
    start_monitor(args.interface, args.target_ip)
