$TTL 60000
@ IN SOA dns.com. root.dns.com. (
    AAAAMMGGNN ; serial
    28800 ;  refresh
    14400 ; retry
    3600000 ; expire
    0 ; negative cache ttl
)

@               	IN	NS	dns.com.

dns.com.        	IN	A	10.0.2.3
www             	IN	A	10.0.1.80
web             	IN	CNAME	www
@               	IN	NS	dns.com.
dns.com.        	IN	A	10.0.2.3
