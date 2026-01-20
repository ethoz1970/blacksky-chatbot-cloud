"""
Async HTTP client for the Blacksky Agent Platform.
Provides methods to enrich user context via external AI agents.
"""
import httpx
from typing import Optional
from config import AGENT_PLATFORM_URL, AGENT_PLATFORM_TIMEOUT


class AgentClient:
    """Client for the Blacksky Agent Platform API."""

    def __init__(self, base_url: str = None, timeout: float = None):
        self.base_url = (base_url or AGENT_PLATFORM_URL).rstrip('/')
        self.timeout = timeout or AGENT_PLATFORM_TIMEOUT
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def is_configured(self) -> bool:
        """Check if agent platform URL is configured."""
        return bool(self.base_url)

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

    async def lookup_user_context(self, user_id: str) -> dict:
        """
        Lookup enriched context for a user from the agent platform.

        Returns agent-provided intelligence including:
        - interest_level: cold/warm/hot
        - lead_status: new/returning/qualified
        - enhanced_facts: AI-extracted facts
        - conversation_summary: Summary of past interactions

        Returns {"success": False, "error": "..."} on failures.
        """
        if not self.is_configured:
            return {"success": False, "error": "Agent platform not configured"}

        try:
            client = await self._get_client()
            response = await client.get(f"/user/{user_id}/context")

            if response.status_code == 200:
                data = response.json()
                data["success"] = True
                return data
            elif response.status_code == 404:
                return {"success": True, "user_id": user_id, "is_new_user": True}
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


# Global singleton instance
agent_client = AgentClient()
