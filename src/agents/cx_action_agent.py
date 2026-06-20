"""Task 10: CX Action Generation — turn complaint clusters into FAQ/support-ready actions."""
from __future__ import annotations

from src.agents.base import BaseAgent
from src.config import settings
from src.data.models import CXActionItem, Review, VOCAnalysisResult
from src.rag.retriever import ReviewRetriever

SYSTEM_PROMPT = """You are a customer support operations lead for a consumer electronics brand.
You turn voice-of-customer complaint clusters into concrete, ready-to-use support assets: FAQ
entries, support response scripts, proactive customer notices, and install-guide fixes.

Your output must be immediately usable by a support agent or published to a help center —
not generic advice. Ground every item in the actual complaint categories and root causes provided.
Return structured JSON only."""


class CXActionAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="CXActionAgent",
            model=settings.model_sonnet,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.3,
        )

    def analyze(
        self,
        reviews: list[Review],
        retriever: ReviewRetriever,
        result: VOCAnalysisResult,
    ) -> VOCAnalysisResult:
        self.log("Generating CX actions from complaint clusters (Task 10)...")

        complaint_summary = "\n".join(
            f"- [{c.issue_type}] {c.category} ({c.frequency_pct:.0f}% of negative reviews): {c.root_cause}"
            for c in result.complaints[:8]
        )
        purchase_experience_count = sum(1 for c in result.complaints if c.issue_type == "purchase_experience")

        prompt = f"""Based on these customer complaint clusters, generate a support toolkit.

COMPLAINT CLUSTERS (tagged by issue_type — product_defect vs purchase_experience):
{complaint_summary}

{purchase_experience_count} of the top complaint categories are purchase_experience issues
(account/login, delivery, installation, pickup) rather than defects in the TV itself — these need
different handling (proactive notices, setup guides) than product_defect issues (FAQ + escalation
scripts).

Generate up to 8 CX action items covering the highest-impact complaint clusters:
{{
  "actions": [
    {{
      "action_type": "faq|support_script|proactive_notice|install_guide",
      "title": "short, specific title (e.g. an FAQ question, or a script name)",
      "content": "the actual FAQ answer, script text, or notice copy — ready to publish/use as-is, 2-4 sentences",
      "related_issue": "which complaint category this addresses",
      "issue_type": "product_defect|purchase_experience",
      "priority": "high|medium|low"
    }}
  ]
}}

Use "faq" or "support_script" for product_defect issues (troubleshooting, warranty, escalation).
Use "proactive_notice" or "install_guide" for purchase_experience issues (set expectations before
or during purchase/setup to prevent the complaint from happening at all)."""

        try:
            data = self.call_json(prompt, max_tokens=6144)
            actions_raw = data.get("actions", data) if isinstance(data, dict) else data
            for item in actions_raw:
                result.cx_actions.append(
                    CXActionItem(
                        action_type=item.get("action_type", "faq"),
                        title=item.get("title", ""),
                        content=item.get("content", ""),
                        related_issue=item.get("related_issue", ""),
                        issue_type=item.get("issue_type", "product_defect"),
                        priority=item.get("priority", "medium"),
                    )
                )
            self.log(f"Generated {len(result.cx_actions)} CX action items")
        except Exception as e:
            self.log(f"[red]CX action generation failed: {e}")

        return result
