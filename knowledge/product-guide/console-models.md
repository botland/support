# Console — Models (deployments)

The **Models** page manages inference deployments. The form and which fields appear **depend on Orchestration** (standalone/distributed and federated/clustered inference).

Page title in the UI: **Models** (API concept: deployments).

---

## Who can manage what

| Role | Models experience |
|------|-------------------|
| **Standalone** | Full create/edit/enable/disable/delete |
| **Distributed coordinator (head)** | Full cluster-wide model authoring |
| **Distributed worker** | Focus on workloads **assigned to this appliance**; not full cluster catalog editing |

Hardware **validation** runs before save/enable: the plan is checked against free GPUs and inventory. Invalid plans show clear errors.

---

## Creating / editing a deployment

### Identity & source

- **Display name (API model ID)** — name clients and the chat workspace use; can differ from the Hugging Face repo name.
- **Source type**
  - **Hugging Face Hub** — repo ID; customer needs a Hugging Face account (and token for gated models).
  - **Local path / NFS / SMB** — absolute path on appliance storage or a mount (e.g. `/models/...`).

### Guided settings

- **Performance goal:** Balanced · Max throughput · Low latency · High availability  
- **Scale:** Small · Medium · Large · **Auto (match cluster GPU slots)**  
- Console may show a **Recommended** card (instances, GPUs per instance, optional nodes per instance, context length) with **Apply recommendation**.

### Placement (when shown)

Placement UI appears for **distributed + federated inference**:

| Mode | Behavior |
|------|----------|
| **Auto (cluster planner)** | Planner assigns nodes/GPUs using federation layout (Replicated vs Diverse). |
| **Manual (choose node & GPU)** | Admin picks targets per replica; may include nodes not yet online. Multiple models can share a GPU if combined **GPU memory utilization** stays ≤ 1.0. |

Under **clustered inference**, spanning and replica placement use the clustered planner path; the federation placement dropdown is not the primary control.

### Advanced settings (common)

- **Instances** — replica count (or auto-sized).
- **GPUs per instance** — how many GPUs cooperate on one replica (standalone: limited by one node).
- **Nodes per instance** — shown when **distributed + clustered inference**: how many nodes one replica spans.
- **Context length** — max sequence length in tokens.
- **GPU memory utilization** — fraction of GPU memory budgeted for this process (share GPUs carefully).
- **Autoscaling** — min/max replicas and target concurrent requests; available when backend supports it (**clustered inference**). Prefer product language: **autoscaling replicas**, not vendor product names.
- **Enabled** — whether the deployment is active.
- **Quantization** — determined by the model package (e.g. pre-quantized Hub repos).

### Lifecycle actions on the list

- Enable / disable without deleting  
- Edit and re-validate  
- Delete (with confirmation)  
- Status badges: healthy, reconciling, degraded, stopped, error  

---

## How Orchestration changes the Models form

| Orchestration | What Models emphasizes |
|---------------|------------------------|
| Standalone | Local capacity; no multi-node span; simpler placement |
| Distributed + Federated | Auto/manual placement; layout (Replicated/Diverse) affects auto plan |
| Distributed + Clustered | Nodes-per-instance; autoscaling; multi-node instances |

Always mention that **changing Orchestration restarts models**, so admins set topology/backend first when possible, then deploy models.

---

## Validation & inventory

Before enable, validation reports free GPUs and online node count. Admins should fix GPU over-subscription, offline nodes, or impossible span (nodes per instance larger than available nodes) before expecting healthy status.

---

## Relation to chat workspace

Deployed **enabled** models become available for the **AI chat workspace** and applications using the appliance model API under the **display name**.
