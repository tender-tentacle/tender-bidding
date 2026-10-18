"""MCP server for the Bidding Engine microservice (tender-bidding, port 8014).

Exposes bid intelligence for the bidding team: the bid aggregate and its
checklist, deadlines, scoring and recommendation, the bid/no-bid matrix, the
document library, and per-company intelligence (financials, Handelsregister,
insolvency, jobs, mood, news, subsidies).
"""

import logging
import os
from typing import Any, Optional

import httpx


def get_auth_headers():
    token = os.getenv("API_KEY") or os.getenv("BEARER_TOKEN")
    return {"Authorization": f"Bearer {token}"} if token else {}

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bidding-mcp")

mcp = MCPServer("Tender Bidding MCP")

BIDDING_API_URLS = [
    os.getenv("BIDDING_API_URL"),
    os.getenv("BIDDING_URL"),
    "http://127.0.0.1:8014",
    "http://bidding:8014",
    "http://localhost/ms/bidding",
]
BIDDING_API_URLS = [u for u in BIDDING_API_URLS if u]

_active_url: Optional[str] = None


async def get_working_url() -> str:
    global _active_url
    if _active_url:
        return _active_url

    async with httpx.AsyncClient(headers=get_auth_headers(), timeout=10.0) as client:
        for url in BIDDING_API_URLS:
            try:
                r = await client.get(f"{url}/health")
                if r.status_code == 200:
                    _active_url = url
                    return url
            except httpx.HTTPError as exc:
                logger.debug("Health probe failed for %s: %s", url, exc)
                continue

    _active_url = BIDDING_API_URLS[0] if BIDDING_API_URLS else "http://127.0.0.1:8014"
    return _active_url


def format_error(action: str, target_url: str, exc: Exception) -> dict:
    global _active_url

    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return {
            "status": "error",
            "action": action,
            "target_url": target_url,
            "http_status": status,
            "message": f"Backend returned HTTP {status}: {exc.response.text[:300]}",
            "suggestion": (
                "The requested bid or company does not exist; call bidding_list_bids first."
                if status == 404
                else "tender-bidding rejected the request; check the arguments or its logs."
            ),
        }

    _active_url = None
    return {
        "status": "error",
        "action": action,
        "target_url": target_url,
        "message": f"Failed to connect to backend: {type(exc).__name__} - {str(exc)}",
        "suggestion": "Verify that tender-bidding is running on port 8014.",
    }


def format_response(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return {"status": "success", "text": resp.text}


async def _get(action: str, path: str, params: Optional[dict] = None, timeout: float = 60.0) -> Any:
    base_url = await get_working_url()
    target = f"{base_url}{path}"
    try:
        async with httpx.AsyncClient(headers=get_auth_headers(), timeout=timeout) as client:
            resp = await client.get(target, params=params)
            resp.raise_for_status()
            return format_response(resp)
    except Exception as exc:
        return format_error(action, target, exc)


async def _post(action: str, path: str, payload: Optional[dict] = None, timeout: float = 180.0) -> Any:
    base_url = await get_working_url()
    target = f"{base_url}{path}"
    try:
        async with httpx.AsyncClient(headers=get_auth_headers(), timeout=timeout) as client:
            resp = await client.post(target, json=payload)
            resp.raise_for_status()
            return format_response(resp)
    except Exception as exc:
        return format_error(action, target, exc)


# --- Argument Schemas ---


class ListBidsArgs(BaseModel):
    limit: int = Field(default=50, ge=1, le=500, description="Maximum number of bids to return.")
    offset: int = Field(default=0, ge=0, description="Pagination offset.")
    status: Optional[str] = Field(default=None, description="Filter by bid status.")


class BidIdArgs(BaseModel):
    bid_id: str = Field(..., description="The id of the bid. Call bidding_list_bids to discover ids.")


class BidBySourceArgs(BaseModel):
    source_ref: str = Field(..., description="The originating tender/group reference the bid was relayed from.")


class SetBidStatusArgs(BaseModel):
    bid_id: str = Field(..., description="The id of the bid.")
    status: str = Field(..., description="New status, e.g. 'bid', 'no_bid', 'submitted'.")
    reason: Optional[str] = Field(default=None, description="Why the status changed.")


class ChecklistItemArgs(BaseModel):
    bid_id: str = Field(..., description="The id of the bid.")
    item_id: str = Field(..., description="The id of the checklist item to update.")
    done: Optional[bool] = Field(default=None, description="Mark the item complete or incomplete.")
    note: Optional[str] = Field(default=None, description="Optional note on the item.")


class AddCollaboratorArgs(BaseModel):
    bid_id: str = Field(..., description="The id of the bid.")
    user_id: str = Field(..., description="Identifier of the collaborator, e.g. 'ambika'.")
    role: str = Field(default="contributor", description="Role: 'lead', 'contributor' or 'reviewer'.")


class CommentArgs(BaseModel):
    bid_id: str = Field(..., description="The id of the bid.")
    message: str = Field(..., description="Comment body.")
    author: Optional[str] = Field(default=None, description="Comment author.")


class CompanyIdArgs(BaseModel):
    company_id: str = Field(..., description="The id of the company in the Bidding context.")


class CompanyNameArgs(BaseModel):
    company_name: str = Field(..., description="Company name.")


class ConfigCategoryArgs(BaseModel):
    category: str = Field(..., description="Configuration category name. Call bidding_get_config for the list.")


class LibrarySearchArgs(BaseModel):
    query: Optional[str] = Field(default=None, description="Free-text query over the document library.")
    limit: int = Field(default=25, ge=1, le=200, description="Maximum number of documents to return.")


class MatrixEvaluationArgs(BaseModel):
    bid_id: str = Field(..., description="The id of the bid to evaluate against the bid/no-bid matrix.")


# --- Bid lifecycle tools ---


@mcp.tool(name="bidding_get_stats", description="Returns aggregate statistics for the Bidding context.")
async def bidding_get_stats() -> Any:
    return await _get("bidding_get_stats", "/api/v1/stats")


@mcp.tool(name="bidding_list_bids", description="Lists bids with pagination and optional status filter.")
async def bidding_list_bids(args: ListBidsArgs) -> Any:
    params: dict[str, Any] = {"limit": args.limit, "offset": args.offset}
    if args.status:
        params["status"] = args.status
    return await _get("bidding_list_bids", "/api/v1/bids", params)


@mcp.tool(name="bidding_get_bid", description="Fetches a single bid aggregate including its checklist items.")
async def bidding_get_bid(args: BidIdArgs) -> Any:
    return await _get("bidding_get_bid", f"/api/v1/bids/{args.bid_id}")


@mcp.tool(
    name="bidding_get_bid_by_source",
    description="Fetches the bid that was relayed from a given tender/group reference.",
)
async def bidding_get_bid_by_source(args: BidBySourceArgs) -> Any:
    return await _get("bidding_get_bid_by_source", f"/api/v1/bids/by-source/{args.source_ref}")


@mcp.tool(
    name="bidding_get_bid_score",
    description="Returns the computed score of a bid.",
)
async def bidding_get_bid_score(args: BidIdArgs) -> Any:
    return await _get("bidding_get_bid_score", f"/api/v1/bids/{args.bid_id}/score")


@mcp.tool(
    name="bidding_get_bid_recommendation",
    description="Returns the bid/no-bid recommendation for a bid, with its rationale.",
)
async def bidding_get_bid_recommendation(args: BidIdArgs) -> Any:
    return await _get("bidding_get_bid_recommendation", f"/api/v1/bids/{args.bid_id}/recommendation")


@mcp.tool(
    name="bidding_get_bid_deadlines",
    description="Returns the submission and question deadlines extracted for a bid.",
)
async def bidding_get_bid_deadlines(args: BidIdArgs) -> Any:
    return await _get("bidding_get_bid_deadlines", f"/api/v1/bids/{args.bid_id}/deadlines")


@mcp.tool(
    name="bidding_get_portal_guide",
    description="Returns the portal-specific submission guide (how to actually hand the bid in).",
)
async def bidding_get_portal_guide(args: BidIdArgs) -> Any:
    return await _get("bidding_get_portal_guide", f"/api/v1/bids/{args.bid_id}/portal-guide")


@mcp.tool(name="bidding_get_bid_documents", description="Lists the documents attached to a bid.")
async def bidding_get_bid_documents(args: BidIdArgs) -> Any:
    return await _get("bidding_get_bid_documents", f"/api/v1/bids/{args.bid_id}/documents")


@mcp.tool(name="bidding_get_bid_activity", description="Returns the activity/audit trail of a bid.")
async def bidding_get_bid_activity(args: BidIdArgs) -> Any:
    return await _get("bidding_get_bid_activity", f"/api/v1/bids/{args.bid_id}/activity")


@mcp.tool(name="bidding_get_bid_comments", description="Lists collaborator comments on a bid.")
async def bidding_get_bid_comments(args: BidIdArgs) -> Any:
    return await _get("bidding_get_bid_comments", f"/api/v1/bids/{args.bid_id}/comments")


@mcp.tool(name="bidding_add_bid_comment", description="Adds a collaborator comment to a bid.")
async def bidding_add_bid_comment(args: CommentArgs) -> Any:
    payload: dict[str, Any] = {"message": args.message}
    if args.author:
        payload["author"] = args.author
    return await _post("bidding_add_bid_comment", f"/api/v1/bids/{args.bid_id}/comments", payload)


@mcp.tool(name="bidding_add_collaborator", description="Adds a collaborator to a bid with a role.")
async def bidding_add_collaborator(args: AddCollaboratorArgs) -> Any:
    payload = {"user_id": args.user_id, "role": args.role}
    return await _post("bidding_add_collaborator", f"/api/v1/bids/{args.bid_id}/collaborators", payload)


@mcp.tool(name="bidding_set_bid_status", description="Changes a bid's status (e.g. to 'bid' or 'no_bid').")
async def bidding_set_bid_status(args: SetBidStatusArgs) -> Any:
    payload: dict[str, Any] = {"status": args.status}
    if args.reason:
        payload["reason"] = args.reason
    return await _post("bidding_set_bid_status", f"/api/v1/bids/{args.bid_id}/status", payload)


@mcp.tool(
    name="bidding_update_checklist_item",
    description="Updates a checklist item (formal / suitability / award criterion) on a bid.",
)
async def bidding_update_checklist_item(args: ChecklistItemArgs) -> Any:
    base_url = await get_working_url()
    target = f"{base_url}/api/v1/bids/{args.bid_id}/checklist/{args.item_id}"
    payload = {k: v for k, v in (("done", args.done), ("note", args.note)) if v is not None}
    try:
        async with httpx.AsyncClient(headers=get_auth_headers(), timeout=60.0) as client:
            resp = await client.patch(target, json=payload)
            resp.raise_for_status()
            return format_response(resp)
    except Exception as exc:
        return format_error("bidding_update_checklist_item", target, exc)


@mcp.tool(
    name="bidding_extract_metadata",
    description="Runs metadata/criteria extraction over a bid's documents to populate its checklist.",
)
async def bidding_extract_metadata(args: BidIdArgs) -> Any:
    return await _post("bidding_extract_metadata", f"/api/v1/bids/{args.bid_id}/extract-metadata", None, 300.0)


@mcp.tool(
    name="bidding_regenerate_bid",
    description="Regenerates a bid's derived intelligence (checklist, score, recommendation).",
)
async def bidding_regenerate_bid(args: BidIdArgs) -> Any:
    return await _post("bidding_regenerate_bid", f"/api/v1/bids/{args.bid_id}/regenerate", None, 300.0)


@mcp.tool(
    name="bidding_get_market_intel",
    description="Returns market intelligence assembled for a bid (incumbents, historic awards).",
)
async def bidding_get_market_intel(args: BidIdArgs) -> Any:
    return await _get("bidding_get_market_intel", f"/api/v1/bids/{args.bid_id}/market-intel")


@mcp.tool(
    name="bidding_get_company_summary",
    description="Returns the company data summary generated for a bid.",
)
async def bidding_get_company_summary(args: BidIdArgs) -> Any:
    return await _get("bidding_get_company_summary", f"/api/v1/bids/{args.bid_id}/company-summary")


# --- Bid/no-bid matrix ---


@mcp.tool(name="bidding_get_matrix", description="Returns the bid/no-bid decision matrix and its categories.")
async def bidding_get_matrix() -> Any:
    return await _get("bidding_get_matrix", "/api/v1/matrix")


@mcp.tool(name="bidding_get_matrix_history", description="Returns the change history of the bid/no-bid matrix.")
async def bidding_get_matrix_history() -> Any:
    return await _get("bidding_get_matrix_history", "/api/v1/matrix/history")


@mcp.tool(
    name="bidding_get_matrix_evaluation",
    description="Returns how a specific bid scores against each bid/no-bid matrix category.",
)
async def bidding_get_matrix_evaluation(args: MatrixEvaluationArgs) -> Any:
    return await _get("bidding_get_matrix_evaluation", f"/api/v1/bids/{args.bid_id}/matrix-evaluation")


@mcp.tool(
    name="bidding_run_matrix_evaluation",
    description="Runs (or re-runs) the bid/no-bid matrix evaluation for a bid.",
)
async def bidding_run_matrix_evaluation(args: MatrixEvaluationArgs) -> Any:
    return await _post(
        "bidding_run_matrix_evaluation", f"/api/v1/bids/{args.bid_id}/matrix-evaluation", None, 300.0
    )


# --- Configuration & document library ---


@mcp.tool(name="bidding_get_config", description="Returns all configuration categories of the Bidding context.")
async def bidding_get_config() -> Any:
    return await _get("bidding_get_config", "/api/v1/config")


@mcp.tool(name="bidding_get_config_category", description="Returns the configuration of a single category.")
async def bidding_get_config_category(args: ConfigCategoryArgs) -> Any:
    return await _get("bidding_get_config_category", f"/api/v1/config/{args.category}")


@mcp.tool(
    name="bidding_get_company_summary_prompt",
    description="Returns the prompt template used to generate company summaries.",
)
async def bidding_get_company_summary_prompt() -> Any:
    return await _get("bidding_get_company_summary_prompt", "/api/v1/config/prompts/company-summary")


@mcp.tool(name="bidding_search_library", description="Searches the reusable bid document library.")
async def bidding_search_library(args: LibrarySearchArgs) -> Any:
    params: dict[str, Any] = {"limit": args.limit}
    if args.query:
        params["q"] = args.query
    return await _get("bidding_search_library", "/api/v1/library/search", params)


# --- Company intelligence ---


@mcp.tool(name="bidding_get_company_profile", description="Returns the stored company profile.")
async def bidding_get_company_profile(args: CompanyIdArgs) -> Any:
    return await _get("bidding_get_company_profile", f"/api/v1/company/{args.company_id}/profile")


@mcp.tool(name="bidding_get_company_financials", description="Returns company financial figures.")
async def bidding_get_company_financials(args: CompanyIdArgs) -> Any:
    return await _get("bidding_get_company_financials", f"/api/v1/company/{args.company_id}/financials")


@mcp.tool(
    name="bidding_get_company_handelsregister",
    description="Returns the German commercial register (Handelsregister) record for a company.",
)
async def bidding_get_company_handelsregister(args: CompanyIdArgs) -> Any:
    return await _get(
        "bidding_get_company_handelsregister", f"/api/v1/company/{args.company_id}/handelsregister"
    )


@mcp.tool(name="bidding_get_company_insolvency", description="Returns insolvency filings for a company.")
async def bidding_get_company_insolvency(args: CompanyIdArgs) -> Any:
    return await _get("bidding_get_company_insolvency", f"/api/v1/company/{args.company_id}/insolvency")


@mcp.tool(name="bidding_get_company_northdata", description="Returns North Data intelligence for a company.")
async def bidding_get_company_northdata(args: CompanyIdArgs) -> Any:
    return await _get("bidding_get_company_northdata", f"/api/v1/company/{args.company_id}/northdata")


@mcp.tool(
    name="bidding_get_company_jobs",
    description="Returns open job postings for a company (hiring signal for capacity and focus).",
)
async def bidding_get_company_jobs(args: CompanyIdArgs) -> Any:
    return await _get("bidding_get_company_jobs", f"/api/v1/company/{args.company_id}/jobs")


@mcp.tool(
    name="bidding_get_company_jobsuche",
    description="Returns Bundesagentur für Arbeit (Jobsuche) postings for a company.",
)
async def bidding_get_company_jobsuche(args: CompanyIdArgs) -> Any:
    return await _get("bidding_get_company_jobsuche", f"/api/v1/company/{args.company_id}/jobsuche")


@mcp.tool(name="bidding_get_company_kununu_jobs", description="Returns Kununu job postings for a company.")
async def bidding_get_company_kununu_jobs(args: CompanyIdArgs) -> Any:
    return await _get("bidding_get_company_kununu_jobs", f"/api/v1/company/{args.company_id}/kununu_jobs")


@mcp.tool(
    name="bidding_get_company_servicebund_jobs",
    description="Returns Servicebund job postings for a company.",
)
async def bidding_get_company_servicebund_jobs(args: CompanyIdArgs) -> Any:
    return await _get(
        "bidding_get_company_servicebund_jobs", f"/api/v1/company/{args.company_id}/servicebund_jobs"
    )


@mcp.tool(name="bidding_get_company_salaries", description="Returns salary benchmarks for a company.")
async def bidding_get_company_salaries(args: CompanyIdArgs) -> Any:
    return await _get("bidding_get_company_salaries", f"/api/v1/company/{args.company_id}/salaries")


@mcp.tool(
    name="bidding_get_company_reputation",
    description="Returns aggregated employer reputation for a company.",
)
async def bidding_get_company_reputation(args: CompanyIdArgs) -> Any:
    return await _get("bidding_get_company_reputation", f"/api/v1/company/{args.company_id}/reputation")


@mcp.tool(
    name="bidding_get_company_mood",
    description="Returns the SCARF-scored employer mood for a company.",
)
async def bidding_get_company_mood(args: CompanyIdArgs) -> Any:
    return await _get("bidding_get_company_mood", f"/api/v1/company/{args.company_id}/mood")


@mcp.tool(name="bidding_get_company_news", description="Returns news/press coverage for a company.")
async def bidding_get_company_news(args: CompanyIdArgs) -> Any:
    return await _get("bidding_get_company_news", f"/api/v1/company/{args.company_id}/news")


@mcp.tool(
    name="bidding_get_company_subsidies",
    description="Returns public subsidies (Fördermittel) a company has received.",
)
async def bidding_get_company_subsidies(args: CompanyNameArgs) -> Any:
    return await _get("bidding_get_company_subsidies", f"/api/v1/companies/{args.company_name}/subsidies")


@mcp.tool(
    name="bidding_get_company_historic_tenders",
    description="Fetches historic tender awards for a company in the Bidding context.",
)
async def bidding_get_company_historic_tenders(args: CompanyIdArgs) -> Any:
    return await _post(
        "bidding_get_company_historic_tenders", f"/api/v1/company/{args.company_id}/historic-tenders"
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", default="stdio", choices=["stdio", "sse"])
    parser.add_argument("--port", type=int, default=8114)
    args = parser.parse_args()

    logger.info("Starting Tender Bidding MCP Server")
    if args.transport == "stdio":
        mcp.run()
    else:
        import uvicorn

        logger.info(f"Starting SSE server on port {args.port}...")
        uvicorn.run(mcp.sse_app, host="0.0.0.0", port=args.port)
