# Console — Orchestration (topology & inference)

The **Orchestration** page is where admins choose **how** the appliance serves models: one box vs multi-unit cluster, and which **inference style** to use.

Important: “Distributed” alone is not the whole story. In the console there are **two independent axes**:

1. **Serving topology** — standalone vs distributed  
2. **Inference backend** — federated inference vs clustered inference  

Both appear as labeled choices on Orchestration (with confirmation when switching).

---

## Axis 1 — Serving topology

| Choice in UI | Meaning |
|--------------|---------|
| **Standalone** | This appliance is the whole system. Parallelism stays on this node. Simpler. |
| **Distributed** | Multi-node private cluster. Model instances can use capacity across units when configured. |

### Roles in distributed mode

| Role | Product language | What the admin does there |
|------|------------------|---------------------------|
| **Coordinator (head)** | Control plane | Status aggregation, cluster-wide Models authoring, mounts, config export/import, orchestration changes |
| **Worker** | Capacity unit | Joins the head’s address; contributes GPUs; console mainly shows **local** workloads |

### Defaults (functional)

- Standalone appliances use **federated inference** style for single-box serving (clustered backend is not offered until topology is distributed).
- Distributed appliances often default toward **clustered inference** for multi-node placement, but the admin can choose federated inference on a multi-unit cluster too.

### Disruptive switches

Changing topology (or backend, or federation layout, or head GPU) **stops and reschedules** running models. The console shows a confirmation, then a blocking wait while the appliance reconciling — this can take several minutes. Overview may show RECONCILING / BOOT / DEGRADED until READY.

---

## Axis 2 — Inference backend (critical)

Shown on Orchestration as **Inference backend**:

### Federated inference

UI title: **Federated inference**  
UI hint: **Assignment-driven workers**

Functional meaning for admins:

- Work is planned as **assignments** of model replicas to nodes/GPUs.
- Best mental model: each replica is a complete serving unit placed on chosen hardware.
- On **distributed + federated**, the admin also picks a **federation layout** (see below).
- **Placement** on the Models form can be **Auto (cluster planner)** or **Manual (choose node & GPU)** when topology is distributed and backend is federated.
- Autoscaling controls and “nodes per instance” advanced fields behave differently than in clustered mode (see Models knowledge).

### Clustered inference

UI title: **Clustered inference**  
UI hint (product-facing): **Placement across nodes**

Functional meaning for admins:

- Designed for **distributed** multi-node serving where a single model instance can **span multiple nodes** (pipeline-style width via **nodes per instance**).
- Requires **distributed** topology — the console **disables** clustered inference while topology is standalone (“Requires distributed topology”).
- Models form shows **nodes per instance** and **autoscaling** options appropriate to this backend.
- Placement is handled by the cluster planner under this backend (not the same manual federation placement UI).

**Never** describe this to customers as named third-party engines — only as **Clustered inference** vs **Federated inference**.

---

## Federated layouts (only when: Distributed + Federated)

UI label: **Federated inference layout**

| Choice in UI | Meaning |
|--------------|---------|
| **Replicated (throughput)** | Spread **each model’s replicas** across nodes for more throughput / capacity of the same model. |
| **Diverse (spread)** | Prefer **different models on different nodes** — multi-model spread across the fleet. |

Notes from the console:

- You can still enable **multiple models** in either layout when GPUs and VRAM allow.
- Layout only changes **auto-placement preference**, not whether multi-model is allowed.
- Switching layout replans instance placement and restarts active deployments.

---

## Coordinator runs inference (head GPU)

Checkbox on Orchestration: **Coordinator runs inference (head GPU)**

- **On (default in many setups):** the head may run model workloads on its own GPUs.
- **Off:** the coordinator focuses on control plane; **workers** should carry inference. Use when you want the head dedicated to management or its GPUs are not for serving.

In **standalone**, head GPU is effectively always on for local serving (standalone always serves on the local appliance).

---

## Head node selection & migration

On Orchestration (when the admin can edit topology):

- **Head node** dropdown lists cluster nodes (hostname, IP, online/offline).
- Changing the head triggers **head migration**: control plane moves; workers repoint; model schedules adjust.
- Console shows a **head epoch** counter that advances when the head changes.
- After migration, if the browser was on the old head IP, the admin may need to open the new head’s console URL.

Head migration is also reachable from the **Nodes** page when the admin has permission.

---

## Global autoscaling default

Orchestration includes a cluster-wide default: **autoscale enabled** under global defaults. Individual model deployments can still configure min/max replicas in Advanced settings when the backend supports autoscaling (primarily **clustered inference**).

---

## Worker view of Orchestration

If this appliance is a **distributed worker** (not head):

- Orchestration focuses on **Detach from cluster** — leave the registry, restart as **standalone**.
- Detach restarts inference on this unit; the coordinator will no longer treat this node as a member until it **re-joins** from Nodes.
- Manage the remaining cluster from the **coordinator** console (Nodes → Open console on the head).

---

## Join / detach (related pages)

| Action | Where | Effect |
|--------|--------|--------|
| **Join cluster** | Nodes (standalone) | Enter coordinator address → become worker in distributed cluster |
| **Detach** | Orchestration (worker) | Leave cluster → standalone |
| **Migrate head** | Orchestration or Nodes | New coordinator identity |

---

## Choosing a combination (guidance)

| Goal | Typical console choices |
|------|-------------------------|
| Single appliance, simplest ops | **Standalone** (+ federated inference automatically) |
| Multiple boxes, assignment-style placement, multi-model spread | **Distributed** + **Federated inference** + **Diverse** or **Replicated** layout |
| Multiple boxes, large models spanning nodes, autoscaling replicas | **Distributed** + **Clustered inference** |
| Head only manages; workers serve | **Distributed** + uncheck **Coordinator runs inference** |

Always teach **both** topology and inference backend when the user asks about “distributed,” “cluster,” “federation,” or “how multi-node works.”
