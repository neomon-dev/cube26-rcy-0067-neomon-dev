# Recovery Manager — AI Evidence-to-Recovery Agent
##Deployment Link: https://recoverymanagerbymdmohidhossain.streamlit.app/

##Demo Video: https://youtu.be/hI-Wgt3fSSw

## Overview

Recovery Manager is an AI-assisted recovery system that analyzes operational charges against available evidence and determines whether a recovery claim can be supported.

The system combines:

- Charge/fee data
- Receiving evidence
- Preparation evidence
- Packing evidence
- Return evidence
- Reimbursement information
- Deterministic recovery rules
- Gemini AI analysis

The goal is to convert raw operational evidence into an auditable recovery decision.

---

## Problem

Operational organizations may receive charges for issues such as:

- Inbound preparation defects
- Missing suffocation warnings
- Unscannable barcodes
- Manufacturer barcodes being visible
- Unplanned preparation
- Warehouse damage
- Warehouse loss
- Customer return issues
- Mis-ships
- Fulfilment weight-tier charges

The difficulty is that the evidence required to challenge a charge is distributed across different operational systems.

Recovery Manager joins these sources and determines whether the available evidence supports a recovery claim.

---

## Core Workflow

```text
                 ┌────────────────────┐
                 │   Fee / Charge CSV  │
                 └─────────┬──────────┘
                           │
                           ▼
                 ┌────────────────────┐
                 │     DataLoader     │
                 └─────────┬──────────┘
                           │
                           ▼
 ┌──────────────┐   ┌────────────────────┐
 │  Receiving   │──▶│                    │
 ├──────────────┤   │   EvidenceJoiner   │
 │    Prep      │──▶│                    │
 ├──────────────┤   └─────────┬──────────┘
 │     Pack     │──▶          │
 ├──────────────┤              │
 │   Returns    │──▶          ▼
 └──────────────┘   ┌────────────────────┐
                    │    RecoveryAgent   │
                    │      Gemini AI     │
                    └─────────┬──────────┘
                              │
                              ▼
                    ┌────────────────────┐
                    │ Decision Engine    │
                    │ Rules + Evidence   │
                    └─────────┬──────────┘
                              │
                              ▼
                    ┌────────────────────┐
                    │ RecoveryDecision   │
                    └────────────────────┘
