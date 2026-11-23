"""Output schema + the labelling rubric. The rubric is shared by the agent, the verifier
and the human gold check, so 'accuracy' always means agreement on the same definitions."""

AUTH = ["OAUTH2", "API_KEY", "BASIC", "OTHER", "NONE"]
ACCESS = ["self_serve_free", "self_serve_trial", "paid_plan", "app_review", "partner_gated", "no_public_api"]
API_TYPE = ["REST", "GraphQL", "REST+GraphQL", "SDK_or_CLI_only", "other_protocol", "none"]
BREADTH = ["broad", "moderate", "narrow", "none"]
MCP = ["official", "community", "none"]
VERDICT = ["ready", "ready_with_friction", "needs_outreach", "not_buildable"]
BLOCKER = ["none", "paid_plan", "app_review", "partnership", "no_public_api", "self_hosted_or_local",
           "unclear_docs", "tos_restrictions", "other"]

SCORED_FIELDS = ["auth_primary", "auth_methods", "access", "api_type", "mcp", "verdict"]

RUBRIC = """
LABELLING RUBRIC (apply exactly):
auth_methods (all that a third-party developer can use against the public API):
  OAUTH2  = OAuth 2.0 authorization-code / client-credentials flows (incl. OAuth for 'apps').
  API_KEY = any static secret the user generates and sends: API key, personal access token, private-app token,
            bot token, integration token, x-api-key header, bearer token copied from settings.
  BASIC   = HTTP Basic (username/email + password or key-as-password, e.g. Twilio SID:token, Freshdesk key:X).
  OTHER   = signed requests / HMAC / JWT you mint yourself / session cookies / mTLS.
  NONE    = public endpoints or local open-source tool with no credentials.
auth_primary = the method an agent toolkit should use for multi-user access: OAUTH2 only if a user-authorization
  (authorization-code) flow covers the main API and a developer can register an app self-serve; otherwise the main
  documented method. A narrow
  client-credentials-only OAuth does not make OAUTH2 primary.
access (can an individual developer get working credentials today?):
  self_serve_free  = free account / free tier / free developer sandbox gives working API credentials.
  self_serve_trial = only through a time-limited free trial of a paid product (API works in trial).
  paid_plan        = API access requires a paid subscription/plan or paid credits with no free path.
  app_review       = dev creds are self-serve but meaningful use needs vendor app review / approval /
                     developer-token tiering (e.g. Meta app review, Google Ads developer token, Amazon SP-API).
  partner_gated    = API access requires partnership, enterprise contract, or 'contact sales'.
  no_public_api    = no documented public API at all.
  If API access requires owning an enterprise product that is only sold through sales (no self-serve signup or
  trial), that is partner_gated, not paid_plan. A free plan that excludes the API is not self_serve_free.
api_type: REST | GraphQL | REST+GraphQL | SDK_or_CLI_only (only a CLI/SDK/library, no hosted HTTP API) |
  other_protocol (bot protocol, websockets, SQL drivers as primary) | none.
api_breadth: broad (>~50 endpoints / most product objects), moderate, narrow (<~10 endpoints), none.
mcp: official = an MCP server published/maintained by the vendor itself; community = only third-party MCP
  servers exist; none = no MCP server found.
verdict (judged from the BUILDER's side, i.e. Composio building and testing the toolkit):
  ready = a developer can get working credentials self-serve today (free tier, free dev account / sandbox, or a
          trial long enough to build and test) for a documented API. Could ship a toolkit this week.
  ready_with_friction = buildable, but the builder must first clear something: vendor app review / approval,
          a paid plan just to get API access, only a short time-limited trial, or an admin-install step that blocks
          multi-user OAuth.
  needs_outreach = credentials only via partnership, enterprise contract or a sales conversation.
  not_buildable = no usable API.
  NOT friction: end customers needing their own subscription to the product, per-customer API keys, rate
  limits, regional endpoints, or ToS worries you could not verify.
blocker = the main thing standing between us and a toolkit ('none' if ready).
"""

RECORD_SCHEMA = {
    "type": "object",
    "properties": {
        "one_liner": {"type": "string"},
        "auth_methods": {"type": "array", "items": {"type": "string", "enum": AUTH}},
        "auth_primary": {"type": "string", "enum": AUTH},
        "auth_notes": {"type": "string"},
        "access": {"type": "string", "enum": ACCESS},
        "access_notes": {"type": "string"},
        "api_type": {"type": "string", "enum": API_TYPE},
        "api_breadth": {"type": "string", "enum": BREADTH},
        "openapi_spec": {"type": ["boolean", "null"]},
        "webhooks": {"type": ["boolean", "null"]},
        "sandbox": {"type": ["boolean", "null"]},
        "mcp": {"type": "string", "enum": MCP},
        "mcp_url": {"type": ["string", "null"]},
        "verdict": {"type": "string", "enum": VERDICT},
        "blocker": {"type": "string", "enum": BLOCKER},
        "blocker_notes": {"type": "string"},
        "docs_url": {"type": ["string", "null"]},
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "url": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": ["field", "url", "quote"],
            },
        },
        "confidence": {
            "type": "object",
            "properties": {f: {"type": "string", "enum": ["high", "medium", "low"]} for f in
                           ["auth", "access", "api", "mcp", "verdict"]},
        },
    },
    "required": ["one_liner", "auth_methods", "auth_primary", "access", "api_type", "api_breadth", "mcp",
                 "verdict", "blocker", "evidence", "confidence"],
}
