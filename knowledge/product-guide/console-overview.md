# Console — full map of sections

The **console** is the browser management UI for OwnEdge appliances. Staff operate it without a specialist AI ops team for routine work.

## Navigation (always-on areas)

| Section | Purpose |
|---------|---------|
| **Overview** | Health at a glance: appliance state (READY / RECONCILING / DEGRADED / BOOT), topology mode, active models, GPU summary, head node, runtime warnings |
| **Models** | Create, size, validate, enable/disable, delete inference deployments |
| **Orchestration** | Topology (standalone/distributed), inference backend (federated/clustered), federation layout, head GPU, head migration, detach worker |
| **Nodes** | Per-unit inventory, labels, reserved GPUs, join cluster, open peer consoles, head candidate |
| **Storage** | Disk usage, model cache browser, mounts (NFS / SMB / S3) |
| **System** | Hostname, IP, gateway, DNS (and related identity) |
| **Support** | Entitlement, sanitized diagnostic report, ticket history |
| **Configuration** | Export/import conf.json, USB recovery notes |

**Models** and **Configuration** appear when this unit is allowed to manage cluster-wide settings (standalone or distributed coordinator). Workers may see a reduced set focused on local participation.

## Live updates

The console receives live status (health, metrics, head changes, events). After Orchestration switches, Overview may show reconciling for minutes — that is expected.

## Role-based experience

| Context | Experience |
|---------|------------|
| Standalone | Full management on this unit |
| Distributed coordinator | Full cluster control plane |
| Distributed worker | Local workloads; detach; open coordinator console for cluster edits |

## Mental model for support answers

When explaining “how OwnEdge / the console works,” cover in order:

1. **What the product is** (private appliance, chat, documents, connectors)  
2. **Console map** (sections above)  
3. **Orchestration two axes** — topology **and** federated vs clustered inference  
4. **Models** how-to under the current mode  
5. **Nodes / Storage / System** for day-2 ops  
6. **Support** only if they ask about diagnostics  

Do not stop at “standalone vs distributed” alone when the user asks about clustering or multi-node — always include **Federated inference** vs **Clustered inference** and layouts when relevant.
