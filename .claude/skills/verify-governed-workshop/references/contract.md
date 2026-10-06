# Flagship contract

## Title

Build governed agentic AI search with Aurora, RDS, & Bedrock AgentCore

## Abstract

Build a governed agentic AI search application with AWS Aurora PostgreSQL
and Amazon Bedrock AgentCore. Explore a retail shopping scenario where a
Strands SDK dispatcher routes shoppers to specialist agents. Aurora powers
hybrid search with PostgreSQL full-text search for lexical retrieval, pgvector
for semantic retrieval, and Cohere Rerank for relevance ranking, while
managing inventory, orders, customer records, and a queryable JSONB audit
ledger. AgentCore Runtime, Memory, Gateway, and Policy orchestrate agents,
preserve context, expose tools, and apply Cedar authorization to sensitive
actions. Leave with reusable patterns for auditable, policy-aware agentic
search applications.

## Required evidence map

The abstract's "Strands SDK dispatcher" is the Router and the three Strands
agents (Shopping, Stock, Support).

| Contract claim | Minimum evidence |
|---|---|
| Strands dispatcher | One shopper turn's Router step names one of the three agents |
| PostgreSQL full-text search | Lexical ranks in a `pellier.retrieval_receipts` row |
| pgvector semantic retrieval | Vector ranks in the same receipt, from the catalog embedding |
| Cohere Rerank | The receipt's `rerank_model` and `rerank_scores` |
| Inventory and orders | Aurora rows plus a tool result grounded in them |
| Customer records and memory | The signed-in customer's rows, and a named AgentCore Memory record |
| JSONB audit ledger | Queryable `pellier.tool_audit` row |
| AgentCore Runtime | A managed turn whose audit rows carry the executed build fingerprint |
| AgentCore Memory | The record id a new session's Router step names, read back by `scripts/lab3_check.py` |
| AgentCore Gateway | A caller-bound `get_tickets` read on the managed rail |
| AgentCore Policy | Cedar ALLOW and DENY decisions |
| Denied action did not execute | DENY receipt plus verified row absence |

## Required path

1. Lab 1: Build and Measure PostgreSQL Hybrid Retrieval
2. Lab 2: Build a PostgreSQL-Grounded Agent
3. Lab 3: Deploy and Operate Agents with Amazon Bedrock AgentCore
4. Lab 4: Build Governed Agent Actions with Cedar
