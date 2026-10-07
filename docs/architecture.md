# Architecture and engineering decisions

```mermaid
flowchart LR
    A[Browser question] --> B[Resolve question and context]
    B --> C[Deterministic interpretation or constrained model request]
    C --> D{Validate complete request}
    D -->|Missing information| E[Specific clarification]
    D -->|Unsupported scope| F[Explain limitation]
    D -->|Approved query and parameters| G[Saved parameterized SQL]
    G --> H[Read-only DuckDB]
    H --> I[Answer contract with values and coverage]
    I --> A
```

The catalog is an allowlist of analytical capabilities. Model output identifies a saved query and supplies bounded fields; validation remains responsible for query compatibility, entity/time constraints and accepted conditions. It does not execute model-generated SQL. A concrete query must answer the complete question, including its filters.

Follow-ups resolve against the prior validated request. Model-assisted edits are constrained and revalidated. A fresh complete named-team question can start independently; ambiguous pronouns keep context. Missing information prompts a targeted clarification rather than an assumed default.

First/final regular-season games use date, game number and game ID to select one actual record. This matters for doubleheaders: the final Braves game in 2024 is game two of the September 30 doubleheader. Missing scores stay missing. Extra venue/opponent/stat filters are rejected if the saved query cannot honor them.

The model gateway keeps provider credentials server-side and returns schema-constrained output. It has no database/file tools. The database connection is read-only with external access disabled. The application calculates values from the database and exposes coverage rather than treating absent records as zero.

Verification combines local regression/boundary tests with actual hosted model calls. Approval is tied to source, model and database fingerprints. Progress is saved after each genuine pass; provider quota stops further requests until the requested retry time. Historical passes for a different fingerprint remain separate.

The project uses Python, DuckDB, pandas, parameterized SQL, vanilla JavaScript/CSS and schema-constrained model APIs. The original local configuration uses Ollama; the separately verified hosted candidate uses Groq. They are different models, with separate validation evidence.

## Tradeoffs

- An approved catalog limits breadth but makes interpretation and execution reviewable. Unsupported questions are explicit.
- A copied database snapshot keeps the owner's workspace independent, but data updates require a new release and fingerprint checks.
- Ephemeral visitor storage makes a free preview simpler, but durable accounts/history would require a separate design decision.
- Free provider capacity keeps operating cost bounded, but requests can pause at quota limits. No paid fallback is enabled.
