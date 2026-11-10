"""
src/core/templates.py
Template statici per configurazioni FRR, BIND, Web server, Startup e Regex comuni.
"""
import re

DAEMONS_TMPL = """zebra={zebra} 
ripd={ripd}
ospfd={ospfd}
bgpd={bgpd}

ospf6d=no
ripngd=no
isisd=no
pimd=no
ldpd=no
nhrpd=no
eigrpd=no
babeld=no
sharpd=no
staticd=no
pbrd=no
bfdd=no
fabricd=no

######

vtysh_enable=yes
zebra_options=" -s 90000000 --daemon -A 127.0.0.1"
bgpd_options="   --daemon -A 127.0.0.1"
ospfd_options="  --daemon -A 127.0.0.1"
ospf6d_options=" --daemon -A ::1"
ripd_options="   --daemon -A 127.0.0.1"
ripngd_options=" --daemon -A ::1"
isisd_options="  --daemon -A 127.0.0.1"
pimd_options="  --daemon -A 127.0.0.1"
ldpd_options="  --daemon -A 127.0.0.1"
nhrpd_options="  --daemon -A 127.0.0.1"
eigrpd_options="  --daemon -A 127.0.0.1"
babeld_options="  --daemon -A 127.0.0.1"
sharpd_options="  --daemon -A 127.0.0.1"
staticd_options="  --daemon -A 127.0.0.1"
pbrd_options="  --daemon -A 127.0.0.1"
bfdd_options="  --daemon -A 127.0.0.1"
fabricd_options="  --daemon -A 127.0.0.1"
"""

VTYSH_TMPL = """service integrated-vtysh-config
hostname {hostname}
"""

FRR_HEADER = """password zebra
enable password zebra

log file /var/log/frr/frr.log
"""

STARTUP_ROUTER_TMPL = """{ip_config}

systemctl start frr
"""

STARTUP_HOST_TMPL = """{ip_config}
ip route add default via {gateway} dev eth0
"""

STARTUP_WWW_TMPL = """ip address add {ip} dev eth0
ip route add default via {gateway} dev eth0
systemctl start apache2 
"""

WWW_INDEX = """<html><head><title>www</title></head><body><h1>Server WWW</h1></body></html>"""

LAB_CONF_HEADER = ""

# Espressioni regolari condivise
_RE_IP_ADD = re.compile(r'\s*ip\s+a(?:ddr(?:ess)?)?\s+add\s+(\S+)\s+dev\s+(\S+)')
_RE_GW = re.compile(r'\s*(?:ip\s+route\s+add\s+default\s+via\s+(\S+)|route\s+add\s+default\s+gw\s+(\S+))')
_RE_APACHE = re.compile(r'(systemctl\s+start\s+apache2|/etc/init\.d/apache2\s+start|service\s+apache2\s+start)')
_RE_TOKEN_IP = re.compile(r'(?<![\w.])(\d{1,3}(?:\.\d{1,3}){3})(?:/(\d{1,2}))?(?![\w.])')
_FRR_GLOBALI = re.compile(
    r'(router|interface|route-map|ip\s+prefix-list|ipv6\s+prefix-list|ip\s+route|'
    r'access-list|ip\s+access-list|bgp\s+as-path|bgp\s+community-list|ip\s+community-list|'
    r'log|debug|hostname|password|enable|line|service|frr|vrf|agentx|end)\b'
)