# models/

Not populated in Phase 1. `contracts/entities.py` currently serves as the
canonical domain-model layer (as Python dataclasses), and
`migrations/001_initial_schema.sql` is the one canonical relational
schema (as SQL) - see the top-level `property_intelligence_v2/README.md`.

This directory is reserved for future domain-model logic that goes
beyond dataclass shape (computed properties, validation methods bound to
a specific entity, etc.), if and when that need arises. It does not hold
a second copy of the schema - there is exactly one canonical schema, in
`migrations/`.
