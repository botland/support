# Console — Nodes

The **Nodes** page is the inventory of every appliance unit (or the single unit in standalone).

## Information per node

- Identity: id, hostname, IP  
- Role: head (coordinator) vs worker  
- Status: online / offline / degraded  
- GPU inventory and utilization  
- Agent / connectivity health and last seen  
- Labels (for placement rules)  
- GPUs reserved for system (not available to model instances)  

## Actions

- Expand a node for detail  
- Edit labels and system GPU reservations  
- **Open node console** — jump to that unit’s management UI when networking allows  
- **Propose / migrate head** to another healthy node (when allowed)  
- **Join cluster** from a standalone appliance: enter the **coordinator address**  
- Monitor workers that become unreachable  

## Labels and placement

Labels help auto-placement (GPU class, location, etc.). On **distributed + federated inference**, manual placement on Models can pin instances to specific nodes and GPUs listed here.

## Join path (standalone → worker)

1. Ensure network reachability to the head.  
2. On Nodes, open join and enter the coordinator address.  
3. After join, manage cluster-wide Models from the **head** console.  

## Relation to Orchestration

Topology and inference backend live on **Orchestration**. Nodes is for inventory, join, labels, and head migration convenience — teach both pages together for multi-unit setups.
