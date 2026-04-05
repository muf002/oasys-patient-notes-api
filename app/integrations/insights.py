import asyncio
from typing import Any, Protocol

from groq import Groq, RateLimitError
from pydantic import BaseModel, ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


CLINICAL_INSIGHTS_SYSTEM_PROMPT = """\
You are a clinical documentation assistant trained to analyze psychotherapy session transcripts.
Extract structured clinical information for a licensed mental health provider's records.
Respond with ONLY a valid JSON object matching this exact schema — no markdown, no explanation.

{
  "key_themes": ["2-5 specific recurring subjects (e.g. 'occupational stressor: hostile manager', not 'work stress')"],
  "presenting_concerns": ["clinical concerns explicitly stated or clearly implied — use clinical language"],
  "risk_indicators": ["ONLY if evidence exists: suicidal ideation, self-harm, substance use, danger to others — [] if none found"],
  "recommended_followups": ["actionable items for the next session (e.g. 'Explore avoidance behaviors around family conflict')"],
  "session_summary": "2-3 sentence third-person clinical narrative (e.g. 'The client presented with...'). No diagnosis.",
  "emotional_tone": "one brief phrase (e.g. 'anxious and guarded', 'hopeful but fatigued')"
}

Rules:
- key_themes: be specific, not generic
- risk_indicators: evidence-based only, conservative flagging — no speculation from ambiguous statements
- recommended_followups: concrete and actionable, not 'continue therapy'
- session_summary: third person, clinical tone\
"""


class ClinicalInsights(BaseModel):
    key_themes: list[str]
    presenting_concerns: list[str]
    risk_indicators: list[str]
    recommended_followups: list[str]
    session_summary: str
    emotional_tone: str


class InsightsProvider(Protocol):
    async def generate_insights(self, transcript: str) -> ClinicalInsights: ...


class GroqInsightsGenerator:
    def __init__(self, api_key: str) -> None:
        self._client = Groq(api_key=api_key)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((RateLimitError, ValidationError)),
    )
    async def _call_with_retry(self, transcript: str) -> ClinicalInsights:
        raw: Any = await asyncio.to_thread(
            lambda: self._client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": CLINICAL_INSIGHTS_SYSTEM_PROMPT},
                    {"role": "user", "content": transcript},
                ],
                response_format={"type": "json_object"},
            )
        )
        content: str | None = raw.choices[0].message.content
        if content is None:
            raise ValueError("LLM returned empty response")
        return ClinicalInsights.model_validate_json(content)

    async def generate_insights(self, transcript: str) -> ClinicalInsights:
        return await self._call_with_retry(transcript)


class StubInsightsGenerator:
    """Deterministic stub — production fallback when GROQ_API_KEY is absent
    and used directly in integration tests to avoid real API calls.
    Pass raises= to simulate failure in unit tests."""

    def __init__(self, raises: Exception | None = None) -> None:
        self._raises = raises

    async def generate_insights(self, transcript: str) -> ClinicalInsights:
        if self._raises:
            raise self._raises
        return ClinicalInsights(
            key_themes=["therapeutic alliance", "cognitive restructuring"],
            presenting_concerns=["generalized anxiety", "sleep onset difficulties"],
            risk_indicators=[],
            recommended_followups=[
                "Review thought diary from this week",
                "Introduce progressive muscle relaxation",
            ],
            session_summary=(
                "The client presented with ongoing anxiety symptoms and sleep difficulties. "
                "Progress on cognitive restructuring techniques was noted."
            ),
            emotional_tone="anxious but engaged",
        )
