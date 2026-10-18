# 🛠️ Public Interface: Tender Bidding

> **Compose service:** `bidding` · **Port:** 8014
> **Generated from source** — do not hand-edit the route table below.
> Run `python3 scripts/docs/gen_api_docs.py` after changing any route.

All paths are relative to the service root. Through the ingress gateway the
service is reached under `/ms/bidding/...` (see `nginx/nginx.conf`).

<!-- AUTOGEN:ROUTES BEGIN - do not edit by hand; run scripts/docs/gen_api_docs.py -->

**79 endpoints** across 22 modules.

> `internal` = declared with `include_in_schema=False`, so it is absent from `/openapi.json`. `conditional` = registered inside an `if` block (feature flag, PACT_TESTING, bundled-UI presence), so it may not exist on a given instance.

### `api/v1/bids.py`

| Method | Path | Handler |
| :--- | :--- | :--- |
| `GET` | `/api/v1/bids` | `list_bids` |
| `GET` | `/api/v1/bids/by-source/{source_ref}` | `get_bid_by_source` |
| `POST` | `/api/v1/bids/by-source/{source_ref}/evaluate-pricing` | `evaluate_pricing_quality_endpoint` |
| `POST` | `/api/v1/bids/enrich` | `enrich_bid_requirements` |
| `GET` | `/api/v1/bids/{bid_id}` | `get_bid` |
| `GET` | `/api/v1/bids/{bid_id}/activity` | `get_activity` |
| `POST` | `/api/v1/bids/{bid_id}/collaborators` | `add_collaborator` |
| `GET` | `/api/v1/bids/{bid_id}/deadlines` | `get_deadlines` |
| `POST` | `/api/v1/bids/{bid_id}/extract-metadata` | `extract_bid_metadata` |
| `POST` | `/api/v1/bids/{bid_id}/match` | `rematch_documents` |
| `POST` | `/api/v1/bids/{bid_id}/match/accept` | `accept_match` |
| `POST` | `/api/v1/bids/{bid_id}/match/reject` | `reject_match` |
| `GET` | `/api/v1/bids/{bid_id}/portal-guide` | `get_portal_guide` |
| `GET` | `/api/v1/bids/{bid_id}/recommendation` | `get_recommendation` |
| `POST` | `/api/v1/bids/{bid_id}/regenerate` | `regenerate` |
| `GET` | `/api/v1/bids/{bid_id}/score` | `get_score` |
| `POST` | `/api/v1/bids/{bid_id}/status` | `update_status` |

### `api/v1/checklist.py`

| Method | Path | Handler |
| :--- | :--- | :--- |
| `PATCH` | `/api/v1/bids/{bid_id}/checklist/{item_id}` | `update_item` |

### `api/v1/comments.py`

| Method | Path | Handler |
| :--- | :--- | :--- |
| `GET` | `/api/v1/bids/{bid_id}/comments` | `list_comments` |
| `POST` | `/api/v1/bids/{bid_id}/comments` | `add_comment` |

### `api/v1/company_financials.py`

| Method | Path | Handler |
| :--- | :--- | :--- |
| `GET` | `/api/v1/company/{company_id}/financials` | `get_company_financials` |

### `api/v1/company_handelsregister.py`

| Method | Path | Handler |
| :--- | :--- | :--- |
| `GET` | `/api/v1/company/{company_id}/handelsregister` | `get_company_handelsregister` |
| `POST` | `/api/v1/company/{company_id}/handelsregister/scrape` | `scrape_company_handelsregister` |

### `api/v1/company_insolvency.py`

| Method | Path | Handler |
| :--- | :--- | :--- |
| `GET` | `/api/v1/company/{company_id}/insolvency` | `get_company_insolvency` |

### `api/v1/company_jobs.py`

| Method | Path | Handler |
| :--- | :--- | :--- |
| `GET` | `/api/v1/company/{company_id}/jobs` | `get_company_jobs` |
| `GET` | `/api/v1/company/{company_id}/jobsuche` | `get_company_arbeitsagentur_jobs` |
| `POST` | `/api/v1/company/{company_id}/jobsuche/scrape` | `scrape_company_arbeitsagentur_jobs` |
| `GET` | `/api/v1/company/{company_id}/servicebund_jobs` | `get_company_servicebund_jobs` |
| `POST` | `/api/v1/company/{company_id}/servicebund_jobs/scrape` | `scrape_company_servicebund_jobs` |

### `api/v1/company_mood.py`

| Method | Path | Handler |
| :--- | :--- | :--- |
| `GET` | `/api/v1/company/{company_id}/kununu_jobs` | `get_company_kununu_jobs` |
| `GET` | `/api/v1/company/{company_id}/mood` | `get_company_mood` |
| `DELETE` | `/api/v1/company/{company_id}/mood` | `delete_company_mood` |
| `POST` | `/api/v1/company/{company_id}/mood/enrich-scarf` | `enrich_company_mood_scarf` |
| `POST` | `/api/v1/company/{company_id}/mood/ingest` | `ingest_browser_crawl` |
| `POST` | `/api/v1/company/{company_id}/mood/scrape` | `manual_scrape_company_mood` |
| `GET` | `/api/v1/company/{company_id}/salaries` | `get_company_salaries` |

### `api/v1/company_news.py`

| Method | Path | Handler |
| :--- | :--- | :--- |
| `GET` | `/api/v1/company/{company_id}/news` | `get_company_news` |
| `POST` | `/api/v1/company/{company_id}/news/refresh` | `refresh_company_news_background` |
| `POST` | `/api/v1/company/{company_id}/news/scrape` | `scrape_company_news` |

### `api/v1/company_northdata.py`

| Method | Path | Handler |
| :--- | :--- | :--- |
| `GET` | `/api/v1/company/{company_id}/northdata` | `get_company_northdata` |
| `POST` | `/api/v1/company/{company_id}/northdata/scrape` | `scrape_company_northdata` |

### `api/v1/company_profile.py`

| Method | Path | Handler |
| :--- | :--- | :--- |
| `POST` | `/api/v1/company/{company_id}/historic-tenders` | `evaluate_historic_tenders` |
| `GET` | `/api/v1/company/{company_id}/profile` | `get_company_profile` |
| `POST` | `/api/v1/company/{company_id}/summarize/{summary_type}` | `summarize_company_data` |

### `api/v1/company_reputation.py`

| Method | Path | Handler |
| :--- | :--- | :--- |
| `GET` | `/api/v1/company/{company_id}/reputation` | `get_company_reputation` |

### `api/v1/company_subsidies.py`

| Method | Path | Handler |
| :--- | :--- | :--- |
| `GET` | `/api/v1/companies/{company_name}/subsidies` | `get_company_subsidies` |
| `POST` | `/api/v1/companies/{company_name}/subsidies/scrape` | `scrape_company_subsidies` |

### `api/v1/company_summary.py`

| Method | Path | Handler |
| :--- | :--- | :--- |
| `GET` | `/api/v1/bids/{bid_id}/company-summary` | `get_company_summary` |
| `POST` | `/api/v1/bids/{bid_id}/company-summary/extract` | `extract_company_summary` |
| `GET` | `/api/v1/config/prompts/company-summary` | `get_prompt_config` |
| `PUT` | `/api/v1/config/prompts/company-summary` | `update_prompt_config` |

### `api/v1/config.py`

| Method | Path | Handler |
| :--- | :--- | :--- |
| `GET` | `/api/v1/config` | `all_configs` |
| `GET` | `/api/v1/config/{category}` | `one_config` |
| `POST` | `/api/v1/config/{category}` | `edit_config` |
| `GET` | `/api/v1/config/{category}/history` | `config_history` |

### `api/v1/documents.py`

| Method | Path | Handler |
| :--- | :--- | :--- |
| `GET` | `/api/v1/bids/{bid_id}/documents` | `list_documents` |
| `POST` | `/api/v1/bids/{bid_id}/documents` | `upload_document` |

### `api/v1/internal.py`

| Method | Path | Handler |
| :--- | :--- | :--- |
| `POST` | `/api/v1/internal/bids/discard` | `discard_bid` |
| `POST` | `/api/v1/internal/bids/relay` | `relay_bid` |

### `api/v1/library.py`

| Method | Path | Handler |
| :--- | :--- | :--- |
| `GET` | `/api/v1/library/search` | `search_library` |

### `api/v1/matrix.py`

| Method | Path | Handler |
| :--- | :--- | :--- |
| `GET` | `/api/v1/bids/{bid_id}/market-intel` | `market_intel` |
| `GET` | `/api/v1/bids/{bid_id}/matrix-evaluation` | `read_evaluation` |
| `POST` | `/api/v1/bids/{bid_id}/matrix-evaluation` | `run_evaluation` |
| `PATCH` | `/api/v1/bids/{bid_id}/matrix-evaluation/{category_id}` | `override_category` |
| `GET` | `/api/v1/matrix` | `get_matrix` |
| `POST` | `/api/v1/matrix` | `upload_matrix` |
| `PUT` | `/api/v1/matrix` | `edit_matrix` |
| `POST` | `/api/v1/matrix/categories` | `create_category` |
| `PATCH` | `/api/v1/matrix/categories/{category_id}` | `edit_category` |
| `DELETE` | `/api/v1/matrix/categories/{category_id}` | `remove_category` |
| `GET` | `/api/v1/matrix/history` | `matrix_history` |

### `api/v1/required_docs.py`

| Method | Path | Handler |
| :--- | :--- | :--- |
| `POST` | `/api/v1/bids/{bid_id}/required-documents/{rd_id}/override` | `override_required_document_status` |
| `POST` | `/api/v1/bids/{bid_id}/required-documents/{rd_id}/upload` | `upload_required_document` |

### `api/v1/stats.py`

| Method | Path | Handler |
| :--- | :--- | :--- |
| `GET` | `/api/v1/stats` | `service_stats` |

### `main.py`

| Method | Path | Handler |
| :--- | :--- | :--- |
| `GET` | `/` | `root` _(conditional)_ |
| `GET` | `/` | `root_placeholder` _(conditional)_ |
| `GET` | `/health` | `health_check` |
| `GET` | `/version` | `version` |
| `GET` | `/{full_path:path}` | `spa` _(conditional)_ |

### Alias prefixes

For backwards compatibility this service mounts its routers under more than one prefix, so each endpoint above is also reachable under:

- `('/api/v1', True)`

> Only the shortest (canonical) path is listed in the tables above. New integrations must use the canonical path; the aliases are deprecated.

### MCP tools (42)

Exposed by `mcp/mcp_server.py` for AI agents:

- `bidding_add_bid_comment`
- `bidding_add_collaborator`
- `bidding_extract_metadata`
- `bidding_get_bid`
- `bidding_get_bid_activity`
- `bidding_get_bid_by_source`
- `bidding_get_bid_comments`
- `bidding_get_bid_deadlines`
- `bidding_get_bid_documents`
- `bidding_get_bid_recommendation`
- `bidding_get_bid_score`
- `bidding_get_company_financials`
- `bidding_get_company_handelsregister`
- `bidding_get_company_historic_tenders`
- `bidding_get_company_insolvency`
- `bidding_get_company_jobs`
- `bidding_get_company_jobsuche`
- `bidding_get_company_kununu_jobs`
- `bidding_get_company_mood`
- `bidding_get_company_news`
- `bidding_get_company_northdata`
- `bidding_get_company_profile`
- `bidding_get_company_reputation`
- `bidding_get_company_salaries`
- `bidding_get_company_servicebund_jobs`
- `bidding_get_company_subsidies`
- `bidding_get_company_summary`
- `bidding_get_company_summary_prompt`
- `bidding_get_config`
- `bidding_get_config_category`
- `bidding_get_market_intel`
- `bidding_get_matrix`
- `bidding_get_matrix_evaluation`
- `bidding_get_matrix_history`
- `bidding_get_portal_guide`
- `bidding_get_stats`
- `bidding_list_bids`
- `bidding_regenerate_bid`
- `bidding_run_matrix_evaluation`
- `bidding_search_library`
- `bidding_set_bid_status`
- `bidding_update_checklist_item`

<!-- AUTOGEN:ROUTES END -->

---

## 🔒 Authentication & Headers

Requests routed through `/ms/bidding/...` or invoked directly require standard authentication and concurrency headers:

| Header | Description |
| :--- | :--- |
| `Authorization` | `Bearer <JWT_TOKEN>` verified against `JWT_SECRET` (HS256). |
| `X-API-KEY` | Technical user access key for background and inter-service tasks. |
| `If-Match` | Concurrency check header echoing bid `version`. Stale versions return `409 Conflict`. |

---

## 📖 Endpoint Details & Payloads

### 1. Bid Workspace & Collaboration

#### `GET /api/v1/bids`
Lists all active bid workspaces with driver assignment, win/loss status, lots, and deadline summaries.
- **Query Parameters**:
  - `status`: Filter by status (`draft`, `in_review`, `submitted`, `won`, `lost`, `archived`).
  - `driver_id`: Filter by Bid Driver identifier.
  - `limit`: Pagination limit (default: 50).
- **Response** (`200 OK`): List of `BidSchema` objects.

#### `GET /api/v1/bids/by-source/{source_ref}`
Retrieves the most recent bid workspace provisioned for a given upstream tender or group reference.
- **Parameters**: `source_ref` (e.g. `ted-notice-12345` or `group-alpha-42`).
- **Response** (`200 OK`): Latest `BidSchema` ordered by `version DESC, created_at DESC`.

#### `POST /api/v1/bids/enrich`
Provisions or updates a collaborative bid workspace from parsed tender metadata.
- **Request Body**:
  ```json
  {
    "source_ref": "ted-2025-08129",
    "title": "Cloud Consulting Framework",
    "buyer_name": "Beschaffungsamt des BMI",
    "lots": ["Lot 1: Infrastructure", "Lot 2: Application Migration"],
    "submission_deadline": "2025-11-30T12:00:00Z"
  }
  ```
- **Response** (`200 OK`): Provisioned `BidSchema` with initialized 4-tier compliance checklist.

#### `POST /api/v1/bids/{bid_id}/collaborators`
Assigns a collaborator to the bid team.
- **Request Body**:
  ```json
  {
    "user_id": "u-8921-prod",
    "role": "contributor",
    "assigned_sections": ["Lot 1", "Pricing"]
  }
  ```

---

### 2. Shipley 4-Tier Compliance Checklist

#### `PATCH /api/v1/bids/{bid_id}/checklist/{item_id}`
Updates a compliance item across the 4-tier matrix (Formal, Suitability, Technical, Award).
- **Request Body**:
  ```json
  {
    "status": "completed",
    "assignee": "bid-specialist-1",
    "notes": "Formblatt 221 signed via QES",
    "is_formal_exclusion_risk": false
  }
  ```
- **Response** (`200 OK`): Updated checklist item record.

---

### 3. North Data Corporate Integration

#### `POST /api/v1/company/{company_id}/northdata/scrape`
Invokes the Market Research MS to scrape North Data, verifies entity name tokens, persists canonical URLs to the Distributing MS, and stores verified records in `bid_company_northdata`.
- **Request Body** (`ScrapeNorthDataRequest`):
  ```json
  {
    "url": "https://www.northdata.de/Bechtle+AG,+Neckarsulm"
  }
  ```
- **Response** (`200 OK`, `CompanyNorthDataSchema`):
  ```json
  {
    "id": 142,
    "company_id": "bechtle",
    "name": "Bechtle AG",
    "court": "Amtsgericht Stuttgart",
    "registration_number": "HRB 108659",
    "equity_capital": 1420000000.0,
    "revenue": 6030000000.0,
    "employees": 15000,
    "verification_confidence": 0.95,
    "verification_reason": "VERIFIED_MATCH",
    "updated_at": "2026-09-27T20:15:00Z"
  }
  ```

#### `GET /api/v1/company/{company_id}/northdata`
Retrieves local cached North Data financial indicators and filing status.
- **Response** (`200 OK`): Cached `CompanyNorthDataSchema` or `null`.

---

### 4. Decision Matrix & Scoring

#### `POST /api/v1/bids/{bid_id}/matrix-evaluation`
Executes an automated Bid/No-Bid evaluation against active organizational capabilities.
- **Response** (`200 OK`):
  ```json
  {
    "overall_score": 82.5,
    "recommendation": "BID",
    "categories": [
      {"name": "Strategic Fit", "score": 90.0, "status": "pass"},
      {"name": "Resource Availability", "score": 75.0, "status": "conditional"}
    ]
  }
  ```

---

### 5. Internal Snapshot Relay

#### `POST /api/v1/internal/bids/relay`
Internal receiver endpoint invoked by the Enriching MS when a tender is triaged as a bid.
- **Payload**: Full tender snapshot, lots in scope, and already-parsed RFP documents.
- **Contract**: Best-effort; failure does not abort upstream triage. Idempotent on `source_ref`.
