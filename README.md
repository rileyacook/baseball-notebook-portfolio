# Baseball notebook

A natural-language interface for historical MLB statistics, built by Riley Cook. It turns a baseball question into a validated request for an approved, parameterized SQL query. DuckDB calculates the answer from regular-season records covering 1898–2025.

This portfolio contains selected implementation code, a UI screenshot and genuine verification records. The complete application and its data snapshot are maintained in a separate private deployment repository. There is no public live demo yet.

![First and final game lookup](docs/game-lookup.png)

## What I built

- A catalog of 51 approved analytical queries covering player and team statistics, rankings, conditional game counts, and first/final regular-season games.
- A constrained interpretation pipeline that checks player/team identity, seasons, metrics, qualification and filters before executing saved SQL.
- Clarification prompts that name missing information and give relevant examples. Unsupported requests return an explanation instead of silently dropping conditions.
- Context-aware follow-ups that preserve the subject while validating requested edits.
- A browser interface with conversation history, optional answer details, comparison charts and light/dark appearance.
- A separate preview service with scoped visitor ownership, expiring conversations and a read-only baseball snapshot. The service and private deployment assets are excluded from this portfolio.

## Verification evidence

On October 7, 2026, the frozen application revision passed all **95 actual hosted-model checks** using Groq with `qwen/qwen3.8-27b`: 75 baseline, 16 held-out paraphrase and four game-lookup cases. These are completed test cases, not a claim of universal question coverage or a percentage for production accuracy.

A separate real model-assisted follow-up retained Aaron Judge as the subject and changed the season from 2024 (58 HR) to 2023 (37 HR). The read-only database fingerprint was unchanged. The records under [verification/](verification/) bind these observations to the exact application and database fingerprints.

The complete application also passed 369 local checks: 310 existing regression checks, 49 public-preview checks and ten browser-helper checks. This portfolio includes the database-free browser-helper test file, which can be run with:

```sh
node --test tests/test_ui_view_model.cjs
```

## Read the implementation

| Area | Selected code |
| --- | --- |
| Validation and approved execution | [query_registry.py](src/analytics/query_registry.py) |
| Explicit metric conditions | [conditions.py](src/analytics/conditions.py) |
| Read-only DuckDB access | [database.py](src/analytics/database.py) |
| Field-specific clarification | [clarification_guidance.py](src/analytics/clarification_guidance.py) |
| UI-facing answer contract | [result_contract.py](src/analytics/result_contract.py) |
| Server-only model transport | [model_gateway.py](src/analytics/model_gateway.py) |
| Fixed game selection | [Final-game SQL](sql/queries/team_season_final_game.sql) |
| Approved query catalog | [analytics_catalog.json](config/analytics_catalog.json) |
| Browser interface | [web/](web/) |

See [architecture and tradeoffs](docs/architecture.md) for the request flow and engineering decisions.

## Scope and limitations

This is a code showcase, not a standalone distribution of the full application. Selected Python modules depend on additional application modules and the private data pipeline. The browser needs the application API; opening the HTML alone does not provide analytics.

The model translates requests; it does not generate arbitrary SQL, compute the reported statistics or train new model weights. Hosted free-tier quota is shared and can delay requests. Cloud deployment, resource usage and deployed mobile behavior remain unverified. Publication of the live preview awaits an access decision.

The verified source has a known wording gap: “3 or more home runs” was rejected although the equivalent “at least 3 home runs” is supported. A fix was tested in a separate local runtime, returning 44 Braves games for 2023. That fix is outside the hosted fingerprint in this portfolio and needs separate release verification before integration. Completed evidence is preserved rather than reused to approve changed code.

## Data attribution

The information used by the application was obtained free of charge from and is copyrighted by Retrosheet. See [Retrosheet](https://www.retrosheet.org/). This portfolio does not distribute the baseball database or its compressed deployment snapshot.

No API keys, conversation history, database files or private deployment assets are included.
