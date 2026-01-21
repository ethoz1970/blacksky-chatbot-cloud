"""
Async HTTP client for the Blacksky Agent Platform.
Provides methods to enrich user context via external AI agents.
"""
import httpx
from datetime import datetime, timedelta
from typing import Optional
from config import AGENT_PLATFORM_URL, AGENT_PLATFORM_TIMEOUT, AGENT_CACHE_TTL


class AgentClient:
    """Client for the Blacksky Agent Platform API."""

    def __init__(self, base_url: str = None, timeout: float = None):
        self.base_url = (base_url or AGENT_PLATFORM_URL).rstrip('/')
        self.timeout = timeout or AGENT_PLATFORM_TIMEOUT
        self._client: Optional[httpx.AsyncClient] = None
        self._cache: dict = {}
        self._cache_ttl = AGENT_CACHE_TTL

    @property
    def is_configured(self) -> bool:
        """Check if agent platform URL is configured."""
        return bool(self.base_url)

    def get_cached(self, user_id: str) -> Optional[dict]:
        """Get cached agent data if still valid."""
        cache_key = f"user_context:{user_id}"
        if cache_key in self._cache:
            cached, timestamp = self._cache[cache_key]
            if datetime.now() - timestamp < timedelta(seconds=self._cache_ttl):
                return cached
        return None

    def _set_cache(self, user_id: str, data: dict):
        """Store agent data in cache."""
        cache_key = f"user_context:{user_id}"
        self._cache[cache_key] = (data, datetime.now())

    def clear_cache(self, user_id: str = None):
        """Clear cache for a specific user or all users."""
        if user_id:
            cache_key = f"user_context:{user_id}"
            self._cache.pop(cache_key, None)
        else:
            self._cache.clear()

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def health_check(self) -> bool:
        """Check if the agent platform is reachable."""
        if not self.is_configured:
            return False
        try:
            client = await self._get_client()
            response = await client.get("/health")
            return response.status_code == 200
        except Exception as e:
            print(f"[AGENTS] Health check failed: {e}")
            return False

    async def lookup_user_context(self, user_id: str, timeout: float = 5.0) -> dict:
        """
        Lookup enriched context for a user from the agent platform.

        Args:
            user_id: The user ID to lookup
            timeout: Request timeout in seconds (default 5.0 for fast fail)

        Returns agent-provided intelligence including:
        - interest_level: cold/warm/hot
        - lead_status: new/returning/qualified
        - enhanced_facts: AI-extracted facts
        - conversation_summary: Summary of past interactions

        Returns {"success": False, "error": "..."} on failures.
        Results are cached for subsequent lookups.
        """
        if not self.is_configured:
            return {"success": False, "error": "Agent platform not configured"}

        try:
            client = await self._get_client()
            response = await client.get(f"/user/{user_id}/context", timeout=timeout)

            if response.status_code == 200:
                data = response.json()
                data["success"] = True
                self._set_cache(user_id, data)
                return data
            elif response.status_code == 404:
                result = {"success": True, "user_id": user_id, "is_new_user": True}
                self._set_cache(user_id, result)
                return result
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
        except httpx.TimeoutException:
            print(f"[AGENTS] Timeout looking up user {user_id}")
            return {"success": False, "error": "Timeout"}
        except Exception as e:
            print(f"[AGENTS] Error looking up user {user_id}: {e}")
            return {"success": False, "error": str(e)}

    async def research_company(self, company_name: str, context: str = None) -> dict:
        """
        Research a company using AI agents.
        Uses longer timeout as this involves Claude processing.

        Args:
            company_name: Name of the company to research
            context: Optional context about why we're researching

        Returns research findings or error dict.
        """
        if not self.is_configured:
            return {"success": False, "error": "Agent platform not configured"}

        try:
            client = await self._get_client()
            payload = {"company_name": company_name}
            if context:
                payload["context"] = context

            # Longer timeout for research (uses Claude)
            response = await client.post(
                "/research/company",
                json=payload,
                timeout=60.0
            )

            if response.status_code == 200:
                data = response.json()
                data["success"] = True
                return data
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
        except httpx.TimeoutException:
            print(f"[AGENTS] Timeout researching company {company_name}")
            return {"success": False, "error": "Timeout"}
        except Exception as e:
            print(f"[AGENTS] Error researching company {company_name}: {e}")
            return {"success": False, "error": str(e)}

    async def search_bsm_docs(self, query: str, context: str = None) -> dict:
        """
        Search BSM documentation using AI agents.

        Args:
            query: Search query
            context: Optional conversation context

        Returns relevant documentation or error dict.
        """
        if not self.is_configured:
            return {"success": False, "error": "Agent platform not configured"}

        try:
            client = await self._get_client()
            payload = {"query": query}
            if context:
                payload["context"] = context

            response = await client.post("/docs/search", json=payload)

            if response.status_code == 200:
                data = response.json()
                data["success"] = True
                return data
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
        except httpx.TimeoutException:
            print(f"[AGENTS] Timeout searching docs for: {query}")
            return {"success": False, "error": "Timeout"}
        except Exception as e:
            print(f"[AGENTS] Error searching docs: {e}")
            return {"success": False, "error": str(e)}

    async def draft_cold_email(
        self,
        company_name: str,
        contact_name: str = None,
        contact_role: str = None,
        context: str = None
    ) -> dict:
        """
        Draft a cold email using AI agents.
        Uses longer timeout as this involves Claude processing.

        Args:
            company_name: Target company
            contact_name: Optional contact name
            contact_role: Optional contact role/title
            context: Optional context about the outreach

        Returns drafted email or error dict.
        """
        if not self.is_configured:
            return {"success": False, "error": "Agent platform not configured"}

        try:
            client = await self._get_client()
            payload = {"company_name": company_name}
            if contact_name:
                payload["contact_name"] = contact_name
            if contact_role:
                payload["contact_role"] = contact_role
            if context:
                payload["context"] = context

            # Longer timeout for email drafting (uses Claude)
            response = await client.post(
                "/email/draft",
                json=payload,
                timeout=60.0
            )

            if response.status_code == 200:
                data = response.json()
                data["success"] = True
                return data
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
        except httpx.TimeoutException:
            print(f"[AGENTS] Timeout drafting email for {company_name}")
            return {"success": False, "error": "Timeout"}
        except Exception as e:
            print(f"[AGENTS] Error drafting email: {e}")
            return {"success": False, "error": str(e)}

    async def notify_lead_captured(
        self,
        user_id: str,
        lead_data: dict,
        timeout: float = 10.0
    ) -> dict:
        """
        Notify agent platform of new lead capture.

        Args:
            user_id: The user ID
            lead_data: Dict containing name, email, phone, company, notes, etc.
            timeout: Request timeout in seconds

        Returns success/error dict.
        """
        if not self.is_configured:
            return {"success": False, "error": "Agent platform not configured"}

        try:
            client = await self._get_client()
            payload = {
                "user_id": user_id,
                "name": lead_data.get("name"),
                "email": lead_data.get("email"),
                "phone": lead_data.get("phone"),
                "company": lead_data.get("company"),
                "interest_level": lead_data.get("interest_level", "warm"),
                "source": "maurice_chat",
                "notes": lead_data.get("notes"),
                "conversation_summary": lead_data.get("conversation_summary")
            }
            # Remove None values
            payload = {k: v for k, v in payload.items() if v is not None}

            response = await client.post(
                "/leads/capture",
                json=payload,
                timeout=timeout
            )

            if response.status_code == 200:
                data = response.json()
                data["success"] = True
                print(f"[AGENTS] Lead captured for user {user_id}")
                return data
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
        except httpx.TimeoutException:
            print(f"[AGENTS] Timeout notifying lead capture for {user_id}")
            return {"success": False, "error": "Timeout"}
        except Exception as e:
            print(f"[AGENTS] Error notifying lead capture: {e}")
            return {"success": False, "error": str(e)}

    async def trigger_company_research(
        self,
        user_id: str,
        company_name: str,
        context: str = None
    ) -> dict:
        """
        Trigger background company research and associate with user.
        This is a fire-and-forget operation for enriching lead data.

        Args:
            user_id: The user to associate research with
            company_name: Company name to research
            context: Optional context about why we're researching

        Returns success/error dict immediately (research happens async).
        """
        if not self.is_configured:
            return {"success": False, "error": "Agent platform not configured"}

        try:
            client = await self._get_client()
            payload = {
                "user_id": user_id,
                "company_name": company_name,
                "async": True  # Request async processing
            }
            if context:
                payload["context"] = context

            response = await client.post(
                "/research/company",
                json=payload,
                timeout=5.0  # Short timeout since it's async
            )

            if response.status_code in (200, 202):
                data = response.json()
                data["success"] = True
                print(f"[AGENTS] Triggered company research for {company_name}")
                return data
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
        except httpx.TimeoutException:
            print(f"[AGENTS] Timeout triggering company research for {company_name}")
            return {"success": False, "error": "Timeout"}
        except Exception as e:
            print(f"[AGENTS] Error triggering company research: {e}")
            return {"success": False, "error": str(e)}


# Global singleton instance
agent_client = AgentClient()
