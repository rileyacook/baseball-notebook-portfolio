# Baseball notebook

A natural-language interface for historical MLB statistics, led by Riley Cook with substantial AI implementation and verification assistance. It turns a baseball question into a validated request for fixed parameterized SQL. DuckDB calculates the answer from regular-season records covering1898–2025.

This repository is a selected-code showcase. The complete application and checked data snapshot remain private. The updated Free service is invite-only; there is no anonymous analytics demo. Current cloud checks passed on October 28, 2026; owner acceptance and a scoped logical account restore passed on October 29. The service is ready for a small invite-only testing round, with the limits below.

## Implemented behavior

- 59 cataloged analytical query families for player/team statistics, rankings, supported conditions, recorded totals/rates and first/final regular-season games.
- Shared intent and completeness contracts that check metric, condition, population, date and relationship scope before execution.
- Targeted clarification or explicit unsupported responses when requested meaning cannot be represented.
- Context-aware follow-ups with validated scope inheritance and real bounded-model edits.
- Requested-stat presentation, required grouped rows, recorded-data coverage and responsive tables/charts.
- A separately hosted invite-only service with access revocation, durable outcome metadata, temporary conversations and read-only analytical data. Private service/deployment components are excluded here.

## Current evidence and provenance

The exact fixed profile contains **124 matching case IDs**:75 baseline,16 held-out,4 game and 29 feedback cases/sequences. It uses the fixed free Groq model `qwen/qwen3.8-27b` and the source/profile/database fingerprints in [verification](verification/). An owner-approved recovery explicitly retained70 fully rechecked identical-source records and completed54 new cases. This is transparent retained evidence, not124 new model calls or a universal accuracy claim.

There were 73 cumulative case HTTP attempts:66 retained attempts including the original timeout and 7 new attempts including quota rejections. Both fresh production follow-ups passed with 2 additional actual HTTP calls total. Deterministic initial Judge and Braves wording used zero model calls; the fresh season edits each used one.

The edits retained Judge while changing2024/58 HR to 2023/37, and Atlanta/inclusive `home_runs >= 3` while changing2023/44 of 162 to 2024/30 of 162. Component coverage100% describes recorded data for those specific results. The Cubs home/road comparison now preserves both required rows and winning-percentage columns.

Actual deployed checks passed:40 access/answer assertions,51 further model/quota assertions and 6 read-only post-wake metadata assertions. They cover separate synthetic accounts, roles/chat isolation, complete selected answers, activity persistence, revocation, real bounded model edits, hourly/shared quota denial and current source assets. These are distinct scoped checks, not a combined correctness score. The100/day quota boundary was not separately exercised, and cloud provider HTTP attempts were not directly counted.

Actual390×844 browser testing verified sign-in, both comparison rows, horizontal access to the remaining columns and no page overflow. A physical phone was not tested. All four synthetic memberships/sessions were disabled; Auth records remain. Their traffic is not adoption.

One observed idle wake took22.649 seconds, correlated with a fresh runtime startup; matching source and anonymous access denial were rechecked. No uptime, general latency or peak memory/CPU benchmark is claimed. A later optional private-file/origin probe hit a 25-second client timeout and was not retried or counted as passed. A separately reviewed check observed four404private-file rejections and a malformed-path400where its strict helper expected404; that stopped result remains failed. The separately approved remaining cross-origin check returned403. These observations do not certify universal security.

The unchanged application had 130 local Python checks.13 earlier unchanged UI checks were not repeated as fresh local proof. Earlier release records are retained under [historical releases](verification/releases/), including the October 12 proof. A [failure-history summary](verification/failure-history-summary.json) preserves the real grouped-row, checker-representation, timeout and production-startup failures without raw feedback or private account details.

Owner acceptance subsequently confirmed a current question/follow-up with team/year scope retained and a working owner activity view. A verified-TLS, read-only encrypted auth/public export was restored into an isolated local database: all31tables matched exact canonical row hashes/counts, with appRLS and anonymous denial retained. The initial connection/comparison failures remain preserved. A new UTC-session comparison passed without relaxing the equality check. The encrypted copy checksum was verified, and native macOS reports cloud data present in the owner’s existing cloud storage with no upload in progress. No independent remote download/hash test or complete managedSupabase/GoTrue/Storage/Vault platform recovery is claimed. No account data, private connection details or archive is included here.

A current owner test also exposed a usability issue: after a Free instance restart loses a temporary chat, the old browser’s Retry action cannot recreate its context and returns404. Starting a new conversation with a full question works. The issue is documented, not silently presented as fixed. Shared Free token limits can interrupt model-assisted questions even below the app-level question allowance.

## Read the implementation

| Area | Selected code |
|---|---|
| Approved execution | [query_registry.py](src/analytics/query_registry.py) |
| Follow-up scope | [conversation.py](src/analytics/conversation.py) |
| Requested intent and completeness | [question_intent.py](src/analytics/question_intent.py), [intent_translation.py](src/analytics/intent_translation.py), [frontier_scope.py](src/analytics/frontier_scope.py) |
| Conditions | [conditions.py](src/analytics/conditions.py) |
| Read-only database | [database.py](src/analytics/database.py) |
| Required results and presentation | [result_contract.py](src/analytics/result_contract.py), [ui_presentation.py](src/analytics/ui_presentation.py), [answer_summary.py](src/analytics/answer_summary.py) |
| Safe failures and diagnostics | [service_faults.py](src/analytics/service_faults.py), [diagnostics.py](src/analytics/diagnostics.py) |
| Provider transport | [model_gateway.py](src/analytics/model_gateway.py) |
| Catalog | [analytics_catalog.json](config/analytics_catalog.json) |
| Browser | [web](web/) |

See [architecture and tradeoffs](docs/architecture.md) and [scope/provenance](PORTFOLIO_SCOPE.md). The database-free browser-helper checks can be run with `node --test tests/test_ui_view_model.cjs`. Omitted Python modules and the private API/data pipeline are required for the full application.

## Contribution and limits

Riley defined product/testing goals, reviewed baseball use cases, approved narrow changes, completed guided service-account setup and controls pilot sharing. Implementation and verification used substantial AI assistance. The project does not claim every module was manually authored by Riley, professional deployment experience, real-user adoption, measured uptime or production scale.

The model proposes a typed request; it does not generate executable SQL or supply invented baseball totals. The finite approved catalog and recorded-data coverage limit analytical scope. Local Ollama and hosted Groq are different model configurations with separate evidence. Free capacity is shared; requests can be busy, delayed or unavailable. Temporary conversations may reset when the service sleeps/restarts, while managed access and outcome metadata persist.

## Data attribution

The information used by the application was obtained free of charge from and is copyrighted by Retrosheet. See [Retrosheet](https://www.retrosheet.org/). This repository excludes the database/image, keys, raw tester feedback, private chats/account details and private deployment configuration.
