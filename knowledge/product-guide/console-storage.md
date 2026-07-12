# Console — Storage

**Storage** manages disk used for models and related data.

## Disk usage

Shows total vs used capacity so admins know when to free cache or attach more space.

## Browse paths

Common areas include the **model cache** (including Hugging Face download cache) and other appliance data paths. Admins can browse listed folders and sizes.

## Mounts

Add or remove network mounts:

| Type | Typical use |
|------|-------------|
| **NFS** | Shared model libraries across a fleet |
| **SMB** | Windows/share style model or document stores |
| **S3** | Object storage style backends when configured |

Fields: remote location, local path on the appliance.

Mount management is available when this unit may manage cluster mounts (**standalone** or **distributed coordinator**). Workers typically use mounts already applied by the head.

Models can load from a **local path** on a mount after the share is available.
