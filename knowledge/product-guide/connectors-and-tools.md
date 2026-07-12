# Connectors and tools

Appliances can expose **connectors** (tools) so the AI can interact with approved resources — not only free-form chat text.

## What connectors can do (functional)

- Read from **files and folders** the admin authorized
- Query **local network services** the customer allows
- Reach **approved web sources** when policy permits
- Work with backend data sources exposed for assistants

## Safety expectations

Connectors are meant to **help retrieve and analyze**, not to silently destroy customer data. Even when a tool is authorized, the product posture is: **do not delete, modify, or rename** customer content through assistant tools unless the customer’s process explicitly requires a controlled write path. Prefer read-only and human-approved changes for production documents.

## Admin responsibility

- Only enable tools that match corporate policy
- Prefer least privilege (specific shares, not entire networks)
- Combine with private document knowledge for on-prem RAG-style workflows without naming vendor stacks
