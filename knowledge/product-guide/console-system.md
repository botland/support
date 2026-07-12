# Console — System

**System** configures **network identity** for the local appliance unit.

## Fields

- Hostname (required)  
- IP address  
- Gateway  
- DNS servers  

Related settings may include time/NTP and whether an API token is set (security), depending on the appliance build.

## Guidance

- After changing hostname or IP, reconnect to the console at the new address.  
- These settings fit the appliance onto the customer LAN; they do not replace corporate DHCP/DNS policy.  
- Head IP in cluster configs should stay consistent with real addressing after changes; prefer changing identity carefully on a live cluster.

## Relation to clustering

Workers join a **coordinator address**. If the head’s IP changes, update join targets and open the correct console URL. Head migration also changes which IP is the control plane.
