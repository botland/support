from __future__ import annotations

import re
from collections.abc import AsyncIterator

# Forbidden stack names (tests assert we never echo these as product tech).
BANNED_STACK = re.compile(
    r"\b("
    r"openwebui|open-?webui|vllm|litellm|traefik|"
    r"\bray\b|kubernetes|k8s|inferedge|grok|"
    r"\bmcp\b|\brag\b"
    r")\b",
    re.IGNORECASE,
)

LEAK_PROBE = re.compile(
    r"\b(openwebui|open[\s-]?webui|vllm|litellm|\bray\b|traefik|"
    r"mcp|rag framework|what stack|which software|under the hood|"
    r"powered by|based on)\b",
    re.IGNORECASE,
)

FOLLOW_UP = re.compile(
    r"^\s*("
    r"what do you mean|what does that mean|can you explain|explain( that| more| again)?"
    r"|why(\s+is that)?|how so|go on|continue|tell me more|more detail|elaborate"
    r"|i don'?t understand|huh\??|and\??|so\??"
    r")\s*[.?!]?\s*$",
    re.IGNORECASE,
)

GREETING = re.compile(
    r"^\s*(hi|hello|hey|bonjour|salut|good\s+(morning|afternoon|evening)|yo|hiya)\s*[!.]*\s*$",
    re.I,
)


def _rx(*parts: str) -> re.Pattern[str]:
    """Word-boundary match for any of the parts (already regex fragments)."""
    return re.compile(r"(?i)\b(?:" + "|".join(parts) + r")\b")


# Topic id → (match pattern, educational answer).
# Patterns use stems so "clustering" matches cluster, "deployed" matches deploy, etc.
# Answers are plain text only (no markdown) for the chat UI.
_TOPICS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "capabilities",
        _rx(
            r"possibilit(?:y|ies)",
            r"capabilit(?:y|ies)",
            r"features?",
            r"what can (?:it|i|we|you|the appliance|ownedge)",
            r"what does (?:it|ownedge|the appliance) do",
            r"what (?:is|are) (?:included|available|possible)",
            r"overview of (?:the )?product",
            r"what can (?:people|staff|teams) do",
            r"use cases?",
            r"workloads?",
        ),
        """What you can do with an OwnEdge appliance

OwnEdge is private AI hardware you own and run on your network. In practice, teams use it for:

1. Run models on your premises
   Deploy open models (from Hugging Face or local files) in the console Models section, size them to your GPUs, and enable them for users and applications.

2. Team AI chat
   Staff use the AI chat workspace to talk to those models for writing, review, analysis, and everyday assistance — without sending conversations to a public multi-tenant chat service.

3. Private document Q&A
   Point the appliance at your own files (local storage, mounts, or approved connectors) so people can ask questions over contracts, policies, and internal knowledge while content stays on-site.

4. Connectors (approved tools)
   When you allow it, assistants can use tools against specific files, local network services, or approved web sources — under least-privilege rules.

5. Grow capacity as a private cluster
   Start with one appliance (standalone), or link several units: one coordinator (head) administers the fleet; workers add GPUs and capacity.

6. Train or customize models
   Adapt models on your own hardware, then deploy the result like any other model.

7. Operate without a specialist AI ops team
   The console covers health (Overview), Models, Orchestration, Nodes, Storage, System identity, Support diagnostics, and configuration backup.

8. Optional care
   Managed Care and SecureVault Backup are monthly add-ons from the B2B site when you want extra operational cover.

Tiers: Edge (desk-side / small team), Studio (shared team capacity), Forge (department / multi-unit scale).

What would you like a walkthrough of first — deploying a model, clustering, chat, or document Q&A?""",
    ),
    (
        "deploy_models",
        _rx(
            r"models?",
            r"deploy(?:ment|ments|ing|ed|s)?",
            r"inference",
            r"hugging\s*face",
            r"huggingface",
            r"\bhf\b",
            r"weights?",
            r"repo(?:sitory)?",
        ),
        """How to deploy a model (console → Models)

A “deployment” is one model you make available for chat and apps on the appliance.

Step by step:
1. Open the console and go to Models (on a standalone unit, or on the cluster coordinator).
2. Add a new deployment.
3. Choose the model source:
   • Hugging Face Hub — enter the repository ID. You need your own Hugging Face account; gated models also need a token for download.
   • Local path — use weights already on the appliance disk or on a network mount (for example under /models/…).
4. Set a display name — the name clients and the chat workspace use when calling the model.
5. Size it: number of copies (instances), GPUs per copy, whether it spans several nodes, context length (max tokens), automatic vs manual GPU placement.
6. Save — the console checks that the plan fits free GPUs. Fix any validation errors before enabling.
7. Enable the deployment when you are ready for users.

On a multi-unit cluster, only the coordinator (head) authors cluster-wide model plans. A worker mainly shows workloads assigned to that box.

Ask next if you want: “What is a worker?”, Hugging Face details, or how clustering affects models.""",
    ),
    (
        "cluster",
        _rx(
            r"cluster(?:ing|ed|s)?",
            r"orchestrat(?:e|es|ed|ing|ion)?",
            r"standalone",
            r"distributed",
            r"topolog(?:y|ies)",
            r"join(?:ing|ed|s)?",
            r"detach(?:ing|ed|es)?",
            r"migrat(?:e|es|ed|ing|ion)?",
            r"multi[-\s]?node",
            r"multi[-\s]?unit",
            r"fleet",
        ),
        """How clustering works (console → Orchestration)

An OwnEdge appliance can run alone or as part of a private multi-unit cluster.

Two serving modes:
• Standalone — everything runs on this one appliance. Simpler; capacity is limited to its GPUs.
• Distributed — several appliances form one cluster. Model instances can use GPUs across nodes when you configure them that way.

Roles in a distributed cluster:
• Coordinator (head) — the control plane. You manage Models, Orchestration, Storage mounts, and Configuration from here. Cluster status is aggregated on the head.
• Worker — a unit that contributes GPUs and capacity. It joins using the coordinator’s address. You do not rewrite the whole cluster plan on the worker; it participates and can show local workloads.

Common operations:
• Switch standalone ↔ distributed (confirm, then wait until the appliance settles).
• Join — from a standalone unit, enter the coordinator address to become a worker.
• Detach — leave the cluster and return toward standalone.
• Migrate head — move the coordinator role to another healthy node so the cluster keeps a control plane.

Mental model: the head is where you administer the fleet; workers are extra capacity that follow the head’s plan.

Ask next: “What is a worker?”, “What is the coordinator?”, or “How do I deploy a model on a cluster?”""",
    ),
    (
        "worker",
        _rx(r"workers?"),
        """What is a worker?

In a distributed OwnEdge cluster, a worker is an appliance unit that is not the coordinator (head).

What a worker does:
• Adds GPUs and capacity so models can run with more throughput or larger footprints.
• Follows the cluster plan defined on the head.
• Can show workloads assigned to that local unit in the console.

What a worker does not do:
• It is not where you rewrite the whole cluster’s model catalog or orchestration.
• Cluster-wide model authoring, mounts, and config export/import stay on the coordinator.

How a unit becomes a worker:
1. Start as (or return to) standalone if needed.
2. In Orchestration / Nodes, join the cluster by pointing at the coordinator’s address.
3. The head then schedules work across the expanded capacity.

If you only have one appliance, you usually stay in standalone mode — there is no separate worker role until you add another unit.

Ask next: “What is the coordinator?”, “How do I join a cluster?”, or “How do I deploy a model?”""",
    ),
    (
        "coordinator",
        _rx(r"coordinators?", r"heads?", r"head\s*nodes?", r"control\s*planes?"),
        """What is the coordinator (head)?

The coordinator — often called the head — is the control plane of a distributed OwnEdge cluster.

On the head you:
• Create and change model deployments for the cluster
• Change orchestration (topology, layouts, head migration)
• Manage shared storage mounts
• Export/import configuration for backup and recovery

Other units (workers) connect to the head and follow that plan. If you migrate the head to another node, workers repoint and the cluster continues under the new coordinator.

In standalone mode there is no multi-unit head/worker split: that single appliance is the whole system.

Ask next: “What is a worker?”, “How does clustering work?”, or “What is head migration?”""",
    ),
    (
        "nodes",
        _rx(r"nodes?", r"gpus?", r"labels?", r"inventor(?:y|ies)"),
        """Nodes and GPUs (console → Nodes)

The Nodes page lists every appliance unit in the cluster (or the single unit in standalone).

For each node you can see:
• Identity — hostname, IP, role (head vs worker)
• GPUs — count, utilization, and how many are reserved for the system
• Health — reachability and last-seen time
• Labels — tags used for placement rules

Useful actions:
• Edit labels so placement can prefer certain hardware
• Reserve GPUs for system use
• Open another node’s console when networking allows
• Start join or head-migration flows when your role allows

Automatic placement lets the appliance choose free capacity; manual placement pins models to specific nodes and GPUs.

Ask next: “How do I deploy a model?”, “What is a worker?”, or “How does storage work?”""",
    ),
    (
        "storage",
        _rx(r"storage", r"disks?", r"nfs", r"mounts?", r"caches?", r"volumes?"),
        """Storage (console → Storage)

Storage is where model files and related data live on the appliance.

You can:
• See total and used disk
• Browse areas such as the model download cache
• Add network mounts (for example NFS): remote share + local path on the appliance

Shared mounts help several units see the same model library. Mount management is available on standalone units and on the cluster coordinator.

Models can download from Hugging Face into the local cache, or load from a path on a mount you prepared.

Ask next: “How do I deploy a model?” or “How does Hugging Face download work?”""",
    ),
    (
        "system",
        _rx(r"system\s*settings?", r"hostnames?", r"dns", r"gateways?", r"ip\s*address(?:es)?"),
        """System identity (console → System)

System settings place the appliance on your LAN:

• Hostname (required)
• IP address
• Gateway
• DNS servers

After you change IP or hostname, open the console again at the new address. This does not replace corporate DHCP/DNS — it only configures how this appliance presents itself on the network.

Ask next: “How do I join a cluster?” or “Where do I manage models?”""",
    ),
    (
        "chat",
        _rx(r"chats?", r"workspaces?", r"assistants?", r"conversations?"),
        """AI chat workspace

The AI chat workspace is where staff talk to models running on your appliance — private assistants for writing, review, and analysis.

How the pieces fit:
• Console Models deploys and sizes the models (capacity, GPUs, enable/disable).
• The chat workspace is where people pick those models and hold conversations.
• Traffic stays on your network with the hardware you own.

How many people can use it at once depends on the tier (Edge / Studio / Forge) and which models you keep enabled.

Ask next: “How do I deploy a model?”, “How does document Q&A work?”, or “What are connectors?”""",
    ),
    (
        "documents",
        _rx(
            r"documents?",
            r"knowledge",
            r"q\s*&\s*a",
            r"q&a",
            r"\bqa\b",
            r"corpora?",
            r"file\s+search",
            r"private\s+document",
        ),
        """Private document knowledge (document Q&A)

Document knowledge lets people ask questions over your own files without uploading the corpus to a public AI provider.

How it works:
1. Make documents available to the appliance (local storage, mounts, or approved connectors).
2. Users ask questions in the chat workspace or knowledge tools.
3. Answers draw from that private material using models you deployed on the appliance.

Typical uses: internal knowledge, contracts, reports, and policies that must stay on-premises. Larger tiers generally support more concurrent users and larger libraries.

Ask next: “What are connectors?”, “How do I deploy a model?”, or “How is data kept private?”""",
    ),
    (
        "connectors",
        _rx(r"connectors?", r"tools?", r"samba", r"shares?"),
        """Connectors and tools

Connectors let the assistant go beyond plain chat by using tools you approve.

Typical uses:
• Read files and folders you authorized
• Query local network services your policy allows
• Reach approved web sources when you enable them

Safety posture:
• Prefer least privilege — specific shares and services, not the whole network
• Tools should help retrieve and analyze; they must not silently delete, rename, or rewrite production content
• Treat any write path as exceptional and controlled by your process

Ask next: “How does document Q&A work?” or “How is data kept private?”""",
    ),
    (
        "training",
        _rx(r"train(?:ing|s|ed)?", r"fine[-\s]?tun(?:e|es|ed|ing)?", r"customi[sz](?:e|es|ed|ing|ation)?"),
        """Model training and customization

You can adapt models on hardware you own so domain data need not leave for a public training service.

Practical flow:
1. Prepare training data under your policies.
2. Run training/customization on the appliance (more GPU time and disk than normal chat).
3. Deploy the result from console Models — often via a local path.
4. Enable it for the chat workspace and applications like any other deployment.

Studio and Forge suit serious training better than a small Edge unit. Validate the new model after deploy.

Ask next: “How do I deploy a model?” or “Which tier do I need?”""",
    ),
    (
        "tiers",
        _rx(r"edge", r"studio", r"forge", r"tiers?", r"capacity", r"concurrent\s+users?"),
        """Choosing Edge, Studio, or Forge

These are capacity classes of the same OwnEdge product family (model sizes are typical fit, not hard limits).

• Edge — desk-side, about 1–5 concurrent users, typical models ≈7B–13B. Solo, labs, small businesses.
• Studio — team capacity, about 10–30 concurrent users, models up to ≈70B class. Agencies and growing companies.
• Forge — department/enterprise scale, multi-model and multi-unit ready. Research and large teams.

All tiers share the same console ideas. Larger tiers give more headroom for users, larger models, clustering, and training.

Ask next: “How do I deploy a model?”, “How does clustering work?”, or “What is in the console?”""",
    ),
    (
        "console",
        _rx(r"consoles?", r"overview", r"admin\s*ui", r"management\s*ui", r"sections?"),
        """The OwnEdge console — map of the sections

The console is the browser management UI. Existing staff can operate it without a specialist AI ops team.

• Overview — health, topology mode, active models, GPU summary, which unit is head
• Models — add, size, validate, enable/disable, delete inference deployments
• Orchestration — standalone vs distributed, head/workers, join/detach, head migration
• Nodes — inventory, labels, GPU reservations, open another node’s console
• Storage — disk usage, model cache, network mounts
• System — hostname, IP, gateway, DNS
• Support — optional sanitized diagnostic report and history
• Configuration — export/import conf.json and USB recovery notes

Standalone units and the cluster coordinator manage cluster-wide settings; workers focus on local participation.

Ask next: “How do I deploy a model?”, “How does clustering work?”, or “Where is Support?”""",
    ),
    (
        "support",
        _rx(
            r"diagnostics?",
            r"tickets?",
            r"managed\s*care",
            r"securevault",
            r"expert\s+help",
            r"product\s+guide",
            # "support" alone is common — still match but lower priority via ordering
            r"supports?",
        ),
        """Support and optional care

Three layers of help:
1. This product guide — learn how appliances and the console work (what you are using now).
2. Automatic diagnostics — from the on-appliance console Support page, an admin can send a sanitized report for analysis (optional).
3. Expert assistance — OwnEdge engineers can review diagnostics you chose to share when automation is not enough.

Optional monthly services (per appliance, from the B2B site):
• Managed Care — proactive checks, guided updates, European support priority
• SecureVault Backup — encrypted configuration backups and restore paths

Ask next: “What is in the console?” or “How do I deploy a model?”""",
    ),
    (
        "config",
        _rx(r"configs?", r"configuration", r"exports?", r"imports?", r"usb", r"dongles?", r"conf\.json"),
        """Configuration backup and recovery (console → Configuration)

• Export — download conf.json (cluster and deployment settings, including head identity).
• Import — restore from a configuration document (invalid JSON is rejected).
• USB recovery — place conf.json on a recovery dongle so the appliance can reload settings in the field.

Export before major topology changes so you can roll back.

Ask next: “How does clustering work?” or “What is head migration?”""",
    ),
    (
        "privacy",
        _rx(
            r"privacy",
            r"private",
            r"secur(?:e|ity)?",
            r"sovereign(?:ty)?",
            r"on[-\s]?prem(?:ise)?s?",
            r"data\s+leav(?:e|es|ing)?",
            r"gdpr",
            r"residen(?:cy|t)",
        ),
        """Privacy and data residency

OwnEdge is built so models and data stay under your custody on hardware you own.

• Day-to-day chat, document Q&A, and inference run on your local network.
• You do not need a permanent public cloud control plane for routine operations.
• Optional diagnostic sharing with OwnEdge is opt-in from the console Support page (sanitized).
• Hugging Face is only involved when you choose to download Hub models — that uses your Hugging Face account.

Ask next: “How does document Q&A work?” or “What are connectors?”""",
    ),
    (
        "huggingface",
        _rx(r"hugging\s*face", r"huggingface", r"\bhf\b"),
        """Using Hugging Face with OwnEdge

Hugging Face Hub is a third-party catalog of model weights. OwnEdge does not replace your Hugging Face account.

To load a Hub model:
1. Use your Hugging Face account.
2. For gated models, accept the model terms and prepare an access token.
3. In console Models, choose Hugging Face as the source and enter the repository ID.
4. Configure size/placement, validate against free GPUs, then enable.

Alternatively, put weights on appliance storage or an NFS mount and choose “local path” — no Hub call at deploy time.

Ask next: “How do I deploy a model?” or “Where is the model cache?”""",
    ),
]

# Prefer specific topics when several patterns match.
_PRIORITY = (
    "worker",
    "coordinator",
    "huggingface",
    "capabilities",
    "deploy_models",
    "cluster",
    "nodes",
    "storage",
    "system",
    "chat",
    "documents",
    "connectors",
    "training",
    "tiers",
    "console",
    "config",
    "privacy",
    "support",  # last — word "support" is easy to false-positive
)


def _last_user_and_assistant(history: list[dict]) -> tuple[str, str]:
    last_user = ""
    last_assistant = ""
    for item in history:
        role = (item.get("role") or "").lower()
        content = (item.get("content") or "").strip()
        if role == "user" and content:
            last_user = content
        elif role == "assistant" and content:
            last_assistant = content
    return last_user, last_assistant


def _topic_scores(text: str) -> dict[str, int]:
    scores: dict[str, int] = {}
    if not text:
        return scores
    for topic_id, pattern, _ in _TOPICS:
        matches = pattern.findall(text)
        if matches:
            # Weight by number of distinct match hits
            scores[topic_id] = len(matches)
    return scores


def _topic_from_text(text: str) -> str | None:
    scores = _topic_scores(text)
    if not scores:
        return None
    best = max(scores.values())
    candidates = [t for t, s in scores.items() if s == best]
    if len(candidates) == 1:
        return candidates[0]
    for p in _PRIORITY:
        if p in candidates:
            return p
    return candidates[0]


def _answer_for_topic(topic_id: str) -> str | None:
    for tid, _, answer in _TOPICS:
        if tid == topic_id:
            return answer
    return None


class StubGuideAdapter:
    """Educational product-guide replies — curated topics only (no raw doc dumps)."""

    async def chat(
        self,
        *,
        user_message: str,
        history: list[dict],
        locale: str = "en",
        session_id: str = "",
    ) -> str:
        return self._reply(user_message, history)

    async def chat_stream(
        self,
        *,
        user_message: str,
        history: list[dict],
        locale: str = "en",
        session_id: str = "",
    ) -> AsyncIterator[str]:
        text = self._reply(user_message, history)
        buf = ""
        for ch in text:
            buf += ch
            if ch in " \n" and len(buf) >= 12:
                yield buf
                buf = ""
        if buf:
            yield buf

    def _reply(self, user_message: str, history: list[dict] | None = None) -> str:
        history = history or []
        msg = (user_message or "").strip()

        if not msg:
            return self._welcome()

        if LEAK_PROBE.search(msg) or BANNED_STACK.search(msg):
            return (
                "OwnEdge appliances are turnkey private AI systems: hardware you own, "
                "a management console for models and capacity, an AI chat workspace for your team, "
                "private document knowledge, and connectors for approved files, local network services, "
                "and web sources.\n\n"
                "I explain how the product works for your staff — not third-party component brands "
                "or internal engineering stacks.\n\n"
                "What would you like to learn next: deploying a model, the chat workspace, "
                "document Q&A, or clustering?"
            )

        if GREETING.match(msg):
            return self._welcome()

        # Explicit follow-ups only (not every short message)
        if FOLLOW_UP.match(msg):
            last_user, last_assistant = _last_user_and_assistant(history)
            topic = _topic_from_text(last_user) or _topic_from_text(last_assistant)
            if topic:
                answer = _answer_for_topic(topic)
                if answer:
                    return (
                        "Happy to go deeper — here is the full walkthrough of what we were discussing:\n\n"
                        + answer
                    )
            if last_assistant:
                return (
                    "Sure — restating the last explanation:\n\n"
                    + last_assistant
                    + "\n\nAsk a specific follow-up (for example “What is a worker?” or "
                    "“Show me the steps to deploy a model”) and I will expand that part."
                )

        topic = _topic_from_text(msg)
        if topic:
            answer = _answer_for_topic(topic)
            if answer:
                return answer

        return self._clarify(msg)

    def _welcome(self) -> str:
        return (
            "Hello — I am the OwnEdge product guide. I help you understand how OwnEdge private AI "
            "appliances work for your team: the console, models, clustering, chat, documents, "
            "connectors, and training.\n\n"
            "You can ask in plain language, for example:\n"
            "• What can the appliance do?\n"
            "• How do I deploy a model?\n"
            "• How does clustering work?\n"
            "• What is a worker?\n"
            "• How does private document Q&A work?\n"
            "• What is Edge vs Studio vs Forge?\n\n"
            "What would you like to explore?"
        )

    def _clarify(self, msg: str) -> str:
        return (
            "I want to answer the right thing. I did not confidently match that to one topic yet.\n\n"
            f"You asked: “{msg[:200]}”\n\n"
            "I can walk you through:\n"
            "• What the appliance can do overall\n"
            "• Deploying models (including Hugging Face)\n"
            "• Clustering — standalone vs distributed, coordinator and workers\n"
            "• Nodes, GPUs, and storage\n"
            "• AI chat workspace and document Q&A\n"
            "• Connectors, training, and tiers (Edge / Studio / Forge)\n"
            "• Support, care services, and configuration backup\n\n"
            "Try a concrete question such as “What can the appliance do?” or “How does clustering work?”"
        )
