---
title: "03: What this maps to in your stack"
weight: 30
---

:::alert{type="info"}
**Audience:** builders translating Pellier to their own organization  
**Use:** read after the room, when the boutique story needs to become your architecture  
**Surfaces covered:** service choices, industry patterns, Aurora and Amazon RDS portability, Knowledge Bases decision points
:::

Pellier is a teaching surface, not a prescription. The reusable shape is the **agentic search architecture**: retrieval over a domain corpus, tools over systems of record, memory substrates, dispatcher routing, managed invocation, MCP-compatible tool exposure, and durable tool-call evidence.

The components stay. The corpus, specialists, policy boundaries, and audited actions change.

## Service map

| Pellier component | Demo choice | What it does | Common swaps |
|---|---|---|---|
| **Vector store** | Aurora PostgreSQL Serverless v2 + `pgvector` | Stores `vector(1024)` embeddings with HNSW index | Amazon RDS for PostgreSQL + `pgvector`; OpenSearch Serverless; existing vector service |
| **Hybrid retrieval** | pgvector cosine + PostgreSQL full-text search + RRF | Mixes semantic recall with literal token recall | Knowledge Bases retrieve API; OpenSearch hybrid query; custom BM25 service |
| **Embeddings** | Cohere Embed English v3 through Bedrock | Embeds catalog rows and query text | Amazon Titan Text Embeddings; SageMaker-hosted embeddings; approved enterprise embedder |
| **Reranking** | Cohere Rerank v3.5 through Bedrock | Reorders candidate results for final phrasing | Amazon reranking options; custom cross-encoder; skip rerank for tight literal queries |
| **Agent framework** | Strands Agents SDK | Defines specialists and `@tool` contracts | Bedrock Agents; LangGraph; custom loop using Bedrock Runtime |
| **Specialist routing** | Rules-first dispatcher | Picks one specialist per curated intent | Small classifier; Haiku at temperature 0; embedding-based routing at tool-catalog scale |
| **Working memory** | AgentCore Memory session events | Ordered turns per `session_id` | DynamoDB with TTL; Redis stream; Aurora table keyed by session |
| **Semantic memory** | AgentCore Memory KV | Durable preference/profile signal | DynamoDB single-table design; Aurora profile table; customer data platform |
| **Episodic memory** | Aurora customer event tables | Browsing rows, orders, returns, prior events | Existing event ledger; lakehouse table; OpenSearch event index |
| **Procedural memory** | Aurora `pellier.tool_audit` aggregate | Tool frequency, latency, and outcome signal | CloudWatch metrics; Athena over S3 audit log; operational analytics table |
| **Managed Runtime** | AgentCore Runtime | Managed invocation boundary for the orchestrator | AWS Lambda + API Gateway; ECS/Fargate; EKS; SageMaker endpoint |
| **MCP exposure** | Read-only Postgres MCP config | Tool/data contract any MCP-aware host can call | AgentCore Gateway; IDE-hosted MCP; internal MCP gateway; hosted tool platform |
| **Knowledge Bases** | Decision point, not required for Pellier's small catalog | Managed retrieval lifecycle for document-heavy corpora | Amazon Bedrock Knowledge Bases; OpenSearch-backed retrieval; enterprise search; custom retrieve API |
| **Audit ledger** | Aurora `pellier.tool_audit` | Durable row for every ALLOWed tool call that runs | Same pattern on RDS; workflow audit table; compliance/event ledger |

## Industry pattern table

Read each row as: *Pellier uses this seam for retail; your organization can keep the seam and swap the nouns.*

| Pellier seam | Retail / e-commerce | Healthcare workflow support | Financial services workflow support | Manufacturing / IoT | Public sector | Software / DevTools |
|---|---|---|---|---|---|---|
| **Domain corpus** | Product catalog with editorial copy | Clinical guidelines, formulary docs, care pathways | Product disclosures, policies, filings, research | Service manuals, parts catalogs, machine docs | Statutes, benefit rules, program guidance | Engineering docs, runbooks, RFCs |
| **Persona / user context** | Shopper, gifter, returning customer | Care navigator, pharmacist, prior-auth reviewer | Advisor, dispute analyst, compliance reviewer | Field technician, planner, reliability engineer | Caseworker, eligibility specialist | On-call engineer, support engineer |
| **Deterministic read tool** | `floor_check` over warehouse inventory | Eligibility status, appointment availability, formulary lookup | Account standing, entitlement state, case queue | Asset health, parts availability, work-order state | Case status, benefit tier, application state | Service health, deploy status, ticket lookup |
| **Audited write tool** | `process_return`, `restock_shelf` | Workflow update, refill request, outreach task | Dispute workflow, review queue, case update | Work-order update, parts reservation, RMA | Application update, case note, review queue | Incident ack, ticket update, runbook step |
| **Working memory** | One shopping session | One member call or care-navigation session | One advisor or support session | One troubleshooting session | One intake conversation | One support thread or incident handoff |
| **Durable profile memory** | Taste, materials, gift preferences | Member preferences or care-navigation context | Account profile and service history | Asset history and failure patterns | Constituent or case history | Account, workspace, or repo history |
| **Policy boundary** | Cedar-gated returns/restocks | Access scope, human review, care-team boundaries | Suitability, KYC, fraud/compliance boundaries | Safety interlocks and authorization scope | Eligibility and fair-treatment boundaries | Change-management and least-privilege boundaries |
| **Audit row answers** | What did the agent do for this shopper? | What workflow step was submitted, with what inputs? | What case/dispute action occurred and when? | What work order or asset state changed? | What case action was taken and why? | What incident action ran and what changed? |
| **MCP fit** | Read-only `pellier.*` tables to any MCP host | Read-only workflow views | Read-only positions, cases, audit views | Read-only assets, parts, work orders | Read-only case and eligibility views | Read-only incidents, deploys, runbooks |
| **Knowledge Bases fit** | Usually overkill for 40 curated SKUs | Policy PDFs, guidelines, protocol libraries | Prospectuses, disclosures, regulatory docs | Manuals, SOPs, maintenance docs | Statutes, program docs, public guidance | Large doc sets, RFCs, runbook libraries |

:::alert{type="warning" header="Use human-review language in regulated domains"}
For healthcare and financial services, frame these patterns as workflow support, policy lookup, evidence retrieval, case updates, and human review. Do not position the agent as making autonomous clinical decisions or unreviewed financial advice.
:::

## Knowledge Bases: the architectural decision

Pellier intentionally builds retrieval itself because the corpus is small, curated, and latency-sensitive. A managed Knowledge Base becomes more attractive when your corpus is document-heavy or when you want a service to own ingestion, chunking, embedding, sync, and retrieve APIs.

| Choose build-it-yourself pgvector when… | Choose a managed Knowledge Base when… |
|---|---|
| You can describe the retrieval SQL clearly. | Your input is folders of PDFs, manuals, policies, or knowledge articles. |
| You need custom hybrid retrieval, RRF, rerank placement, or tight latency control. | You want ingestion, chunking, embedding, sync, and retrieve APIs managed for you. |
| Your corpus is structured or semi-structured, like product rows or workflow records. | Your corpus is mostly unstructured documents. |
| You need direct SQL joins against operational tables. | You want a clean retrieval boundary that downstream agents call. |

Amazon Bedrock Knowledge Bases is one AWS managed option in this category. Other teams may use OpenSearch-backed retrieval, enterprise search, or a custom retrieve API. The important design question is not the product name; it is **who owns retrieval lifecycle and evidence**.

## Aurora ↔ Amazon RDS for PostgreSQL portability

If your team is on Amazon RDS for PostgreSQL rather than Aurora:

- **pgvector works the same for the DIY path.** `CREATE EXTENSION vector`, `vector(1024)`, HNSW, and cosine distance are the same mental model.
- **Hybrid retrieval works the same.** `tsvector`, `ts_rank_cd`, and `pg_trgm` are PostgreSQL capabilities, not boutique-specific magic.
- **The audit ledger works the same.** `BIGSERIAL`, `JSONB`, `->`, `->>`, timestamp columns, and GIN indexes are standard PostgreSQL patterns.
- **Managed Knowledge Base support is service- and region-dependent.** Validate the supported vector store targets for your chosen Knowledge Base option in your target region. The build-it-yourself pattern you saw in Pellier remains portable.

## Two questions to ask back at your desk

1. **What is your equivalent of `pellier.tool_audit`?** Where does durable tool-call evidence live today, and can an operator query tool, arguments, result, latency, and session in one place?
2. **Where is the dispatcher hidden in your current stack?** If your system routes by intent, is that route rules-first, classifier-first, or LLM-first? Was that choice deliberate?

:::alert{type="info" header="See also"}
[Reference](/90-appendix/01-reference/) for the cast and pgvector primer, and [When things misbehave](/90-appendix/02-when-things-misbehave/) for the operational runbook.
:::
