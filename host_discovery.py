from pox.core import core
import pox.openflow.libopenflow_01 as of
import time
import threading

log = core.getLogger()

# Host database: MAC -> (switch, port, last_seen)
host_db = {}

# MAC learning table
mac_to_port = {}

TIMEOUT = 20  # seconds


def _handle_ConnectionUp(event):
    log.info("Switch %s connected", event.dpid)


def _handle_PacketIn(event):
    packet = event.parsed
    if not packet.parsed:
        return

    src = str(packet.src)
    dst = str(packet.dst)
    dpid = event.dpid
    in_port = event.port
    now = time.time()

    # Initialize table for switch
    if dpid not in mac_to_port:
        mac_to_port[dpid] = {}

    # Learn MAC address
    mac_to_port[dpid][src] = in_port

    # 🔥 Host discovery logic
    if src not in host_db:
        log.info("New Host Joined → MAC: %s | Switch: %s | Port: %s",
                 src, dpid, in_port)
    else:
        old_dpid, old_port, _ = host_db[src]
        if old_dpid != dpid or old_port != in_port:
            log.info("Host Moved → MAC: %s", src)

    # Update host table
    host_db[src] = (dpid, in_port, now)

    # Print host table
    print("\nCurrent Host Table:")
    for mac in host_db:
        d, p, _ = host_db[mac]
        print(mac, "-> Switch:", d, "Port:", p)
    print("------------------------")

    # Forwarding logic
    if dst in mac_to_port[dpid]:
        out_port = mac_to_port[dpid][dst]
    else:
        out_port = of.OFPP_FLOOD

    # Send packet immediately
    msg = of.ofp_packet_out()
    msg.data = event.ofp
    msg.actions.append(of.ofp_action_output(port=out_port))
    event.connection.send(msg)

    # Install flow rule for future packets
    if dst in mac_to_port[dpid]:
        flow = of.ofp_flow_mod()
        flow.match.dl_dst = packet.dst
        flow.actions.append(of.ofp_action_output(port=out_port))
        event.connection.send(flow)


def _remove_inactive_hosts():
    while True:
        time.sleep(5)
        now = time.time()
        remove_list = []

        for mac in host_db:
            _, _, last_seen = host_db[mac]
            if now - last_seen > TIMEOUT:
                remove_list.append(mac)

        for mac in remove_list:
            log.info("Host Removed (timeout) → MAC: %s", mac)
            del host_db[mac]


def launch():
    log.info("🔥 Host Discovery Service Started")

    core.openflow.addListenerByName("ConnectionUp", _handle_ConnectionUp)
    core.openflow.addListenerByName("PacketIn", _handle_PacketIn)

    # Start cleanup thread
    threading.Thread(target=_remove_inactive_hosts, daemon=True).start()
    