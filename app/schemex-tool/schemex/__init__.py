"""
Schemex
=======

A small, hackable implementation of the Schemex workflow described in
"Schemex: Discovering Design Patterns from Examples through Iterative
Abstraction and Refinement" (Wang & Chilton, 2025, arXiv:2502.15105).

Three stages, each a thin wrapper around a Claude API call:

    1. Clustering    -- group raw examples by latent structural similarity
    2. Abstraction    -- derive a Components / Attributes / Relationships
                          schema for each cluster
    3. Refinement      -- generate content from the schema, contrast it
                          against a real example, and iterate the schema

Runs in two modes:

    --mode automated    one-shot, no human in the loop (default)
    --mode interactive   pause after clustering and after each refinement
                          iteration so a human can edit/accept/reject

See README.md for usage.
"""

__version__ = "0.1.0"