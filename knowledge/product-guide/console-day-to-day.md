# Console — day-to-day admin workflows

Educational sequences the product guide should be able to teach end-to-end.

## First boot / single appliance

1. Place appliance on LAN; open console.  
2. **System** — hostname, IP, gateway, DNS.  
3. **Storage** — optional NFS/SMB for models.  
4. **Orchestration** — leave **Standalone** unless multi-unit is required.  
5. **Models** — add model (Hugging Face or local path), guided scale, validate, enable.  
6. **Overview** — wait until READY / healthy deployments.  
7. Point staff to **AI chat workspace** using the model display names.  

## Grow to multi-unit (distributed)

1. On the intended head: Orchestration → **Distributed**.  
2. Choose **Inference backend**:  
   - **Federated inference** for assignment-driven multi-model fleets (+ Replicated or Diverse layout).  
   - **Clustered inference** when models should span nodes and use multi-node instances.  
3. Set **Coordinator runs inference** on or off.  
4. On each extra unit: **Nodes → Join** with head address (they become workers).  
5. On the head: **Models** — redeploy/validate against expanded GPU inventory.  
6. Optionally **Storage** mounts for shared model libraries.  
7. Export **Configuration** after a stable setup.  

## Change inference style later

Orchestration → switch Federated ↔ Clustered (distributed required for clustered). Expect confirmation and multi-minute reconcile; models restart.

## Move the control plane

Orchestration or Nodes → select new **Head node** → migrate. Workers repoint. Open console on new head IP if needed.

## Detach a worker

On the worker: Orchestration → **Detach from cluster** → becomes standalone again.

## When something is wrong

1. **Overview** — state, degraded signals, events.  
2. **Nodes** — offline / last seen.  
3. **Models** — deployment status, re-validate sizing.  
4. **Support** — optional sanitized diagnostic report.  

## Product surfaces beyond the console

- **AI chat workspace** — end-user chat with deployed models.  
- **Document knowledge** — private Q&A over company files.  
- **Connectors** — approved tools for files / LAN / web.  
- **Training** — customize models, then deploy via Models.  

The console is the **control plane UI**; chat and knowledge are the **staff productivity** surfaces.
