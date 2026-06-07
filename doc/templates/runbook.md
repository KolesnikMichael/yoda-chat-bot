---
id: <% tp.file.title %>
title: "<% tp.file.title.replace(/-/g, " ") %>"
updated: <% tp.date.now("YYYY-MM-DD") %>
author: ""
tags: []
---

# <% tp.file.title.replace(/-/g, " ") %>

## Purpose

When to use this runbook: which situation, event, or task.

## Preconditions

What must be ready before starting:
- [ ] Access to ...
- [ ] Running / reachable ...
- [ ] Environment variables: `VAR_NAME`

## Steps

### 1. Step name

What we do and why.

```bash
# command
```

Expected result: ...

---

### 2. Step name

Description.

```bash
# command
```

Expected result: ...

---

### 3. Verification

How to confirm everything succeeded.

```bash
# verification command
```

## Rollback

What to do if something goes wrong. Steps to return to the original state.

- [ ] Rollback step 1
- [ ] Rollback step 2

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Error X | Cause Y | Do Z |

## Related documents

<!-- Other runbooks, ADRs, or architecture documents -->
- [[]]
