"""Report generator: Markdown + JSON outputs."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from jinja2 import Template
from rich.console import Console

from src.config import settings
from src.data.models import VOCAnalysisResult

console = Console()

REPORT_TEMPLATE = """# Samsung VOC Intelligence Report
## {{ result.model }} — {{ result.analysis_date }}

---

## Executive Summary

{{ result.executive_summary }}

---

## Key Insights

{% for insight in result.key_insights %}
{{ loop.index }}. {{ insight }}
{% endfor %}

---

## VOC Dashboard

**Total Reviews:** {{ result.total_reviews }}{% if result.total_reviews_available > result.total_reviews %} (sampled from {{ result.total_reviews_available }} available){% endif %}
**Average Rating:** {{ "%.1f"|format(result.avg_rating) }}/5
**Analysis Date:** {{ result.analysis_date }}

### Sentiment Distribution
{% for sentiment, count in result.sentiment_distribution.items() %}
- **{{ sentiment|capitalize }}**: {{ count }} reviews ({{ "%.0f"|format(count / result.total_reviews * 100) }}%)
{% endfor %}

---

## Task 1: Customer Complaint Analysis

| Rank | Category | Issue Type | Frequency (% of negative reviews) | Root Cause |
|------|----------|-----------|-----------|------------|
{% for c in result.complaints %}
| {{ c.rank }} | {{ c.category }} | {{ "Product Defect" if c.issue_type == "product_defect" else "Purchase Experience" }} | {{ c.frequency }} ({{ "%.0f"|format(c.frequency_pct) }}%) | {{ c.root_cause }} |
{% endfor %}

{% for c in result.complaints[:3] %}
### {{ c.rank }}. {{ c.category }}

**Root Cause:** {{ c.root_cause }}

**Representative Reviews:**
{% for review in c.representative_reviews %}
> "{{ review }}"
{% endfor %}

{% endfor %}

---

## Task 2: Satisfaction Driver Analysis

| Rank | Driver | Positive Rate | Mentions |
|------|--------|--------------|----------|
{% for s in result.satisfaction_drivers %}
| {{ s.rank }} | {{ s.factor }} | {{ "%.0f"|format(s.positive_rate) }}% | {{ s.mention_count }} |
{% endfor %}

---

## Task 3: Product Improvement Recommendations

| Priority | Area | Expected Effect | Impact Score |
|----------|------|----------------|-------------|
{% for i in result.improvement_points|sort(attribute='impact_score', reverse=True) %}
| **{{ i.priority|upper }}** | {{ i.area }} | {{ i.expected_effect }} | {{ i.impact_score }}/10 |
{% endfor %}

---

## Task 4: Marketing Message Recommendations

{% if result.marketing_recommendations %}
**Current Customer Perception:**
{{ result.marketing_recommendations.current_perception }}

**Actual Value Drivers (from VOC):**
{% for v in result.marketing_recommendations.actual_value_drivers %}
- {{ v }}
{% endfor %}

**Proposed New Messages:**
{% for m in result.marketing_recommendations.new_message_proposals %}
- {{ m }}
{% endfor %}

**Messages to Avoid:**
{% for m in result.marketing_recommendations.messages_to_avoid %}
- ⚠️ {{ m }}
{% endfor %}
{% endif %}

---

{% if result.positioning_analysis %}
## Task 5: Competitive Positioning

{% if result.positioning_analysis.attribute_map %}
### Customer Voice Positioning Map

| Attribute | Samsung | Volume | Sentiment | Business Impact | vs. Competitors |
|---|---|---|---|---|---|
{% for a in result.positioning_analysis.attribute_map -%}
| {{ a.attribute }} | **{{ a.samsung_assessment|upper }}** | {{ a.mention_volume }} | {{ "%.2f"|format(a.sentiment_score) }} | {{ a.business_impact|replace('_', ' ') }} | {{ a.vs_competitor_note }} |
{% endfor %}

### Executive Summary

| Defend | Differentiate | Fix | Monitor |
|---|---|---|---|
| {{ result.positioning_analysis.defend|join('<br>') }} | {{ result.positioning_analysis.differentiate|join('<br>') }} | {{ result.positioning_analysis.fix|join('<br>') }} | {{ result.positioning_analysis.monitor|join('<br>') }} |

{% endif %}
### Samsung Strengths
{% for s in result.positioning_analysis.samsung_strengths %}
- ✅ {{ s }}
{% endfor %}

### Samsung Weaknesses
{% for w in result.positioning_analysis.samsung_weaknesses %}
- ❌ {{ w }}
{% endfor %}

### Competitive Advantages
{% for a in result.positioning_analysis.competitive_advantages %}
- 🏆 {{ a }}
{% endfor %}

### Competitor Comparison

{% for comp in result.positioning_analysis.competitors %}
#### {{ comp.name }} ({{ comp.model }})
- **Price:** {{ comp.price_range }}
- **UX:** {{ comp.ux }}
{% for attr, assessment in comp.key_attributes.items() %}
- **{{ attr }}:** {{ assessment }}
{% endfor %}
- **Advantages over Samsung:** {{ comp.strengths|join(', ') }}
- **Disadvantages vs Samsung:** {{ comp.weaknesses|join(', ') }}
{% endfor %}

**Strategic Recommendation:**
{{ result.positioning_analysis.positioning_recommendation }}
{% endif %}

---

## Task 6: Rating-Review Contradiction Analysis

**Total Contradictions Detected:** {{ result.contradictions|length }}

{% set type_a = result.contradictions|selectattr('contradiction_type', 'equalto', 'type_a')|list %}
{% set type_b = result.contradictions|selectattr('contradiction_type', 'equalto', 'type_b')|list %}

**Type A (High Rating + Hidden Complaint):** {{ type_a|length }}
**Type B (Low Rating + Product Praise):** {{ type_b|length }}

{% for c in result.contradictions[:5] %}
### Case: {{ c.contradiction_type|upper }} (Rating: {{ c.rating }}⭐){% if c.mismatch_category %} — {{ c.mismatch_category|replace('_', ' ') }}{% endif %}

> "{{ c.review_text }}"

**Positive:** {{ c.positive_elements|join(', ') }}
**Negative:** {{ c.negative_elements|join(', ') }}
**Implication:** {{ c.implication }}
{% if c.route_to %}
**Route to:** {{ c.route_to|replace('_', ' ') }} | **Counts as product issue:** {{ "Yes" if c.counts_as_product_issue else "No" }}
{% endif %}
{% if c.suggested_public_response %}
**Suggested public response:** {{ c.suggested_public_response }}
{% endif %}

{% endfor %}

---

## Task 7: Issue Importance Matrix

Each issue below is plotted by frequency (how often it's mentioned) vs. business impact (severity of
the consequence if unaddressed) and ranked by overall priority. Where a fix is already detailed
elsewhere in this report (Task 8 Expectation Gaps, Task 10 CX Actions), this list points there instead
of repeating it.

### Priority Order
{% for i in result.importance_matrix|sort(attribute='priority_rank') %}
{{ loop.index }}. **{{ i.issue }}** — [{{ i.issue_type }}] ({{ i.frequency }} mentions, {{ "%.1f"|format(i.frequency_pct) }}% of all analyzed reviews, {{ i.category|replace('_', ' ') }})
   - Business Risk: {{ i.business_risk }}
   {%- if i.linked_expectation_gap %}
   - → Fix detailed under Task 8, Expectation Gap: {{ i.linked_expectation_gap }}
   {%- endif %}
   {%- if i.linked_cx_action %}
   - → Fix detailed under Task 10, CX Action: {{ i.linked_cx_action }}
   {%- endif %}
   {%- if not i.linked_expectation_gap and not i.linked_cx_action %}
   - Recommended Action: {{ i.recommended_action }}
   {%- endif %}
{% endfor %}

### 🔴 Low Frequency / High Impact (Critical Quality Issues)
{% for i in result.importance_matrix if i.category == 'low_freq_high_impact' %}
- **{{ i.issue }}** ({{ i.frequency }} mentions, {{ "%.1f"|format(i.frequency_pct) }}% of all analyzed reviews)
  - Business Risk: {{ i.business_risk }}
{% endfor %}

### 🟡 High Frequency / Low Impact (UX Annoyances)
{% for i in result.importance_matrix if i.category == 'high_freq_low_impact' %}
- **{{ i.issue }}** ({{ i.frequency }} mentions, {{ "%.1f"|format(i.frequency_pct) }}% of all analyzed reviews)
  - Business Risk: {{ i.business_risk }}
{% endfor %}

### 🔴 High Frequency / High Impact (Top Priorities)
{% for i in result.importance_matrix if i.category == 'high_freq_high_impact' %}
- **{{ i.issue }}** ({{ i.frequency }} mentions, {{ "%.1f"|format(i.frequency_pct) }}% of all analyzed reviews)
  - Business Risk: {{ i.business_risk }}
{% endfor %}

---

## Task 8: Customer Expectation Gap Analysis

{% set excluded_mismatches = result.contradictions|rejectattr('counts_as_product_issue')|list %}
{% if excluded_mismatches %}
{{ excluded_mismatches|length }} flagged rating/text mismatch{{ "es are" if excluded_mismatches|length > 1 else " is" }} excluded from the
gaps below — see Task 6 (Rating-Review Contradiction Analysis) for reviews where the product was
praised but the rating was low for an unrelated reason.
{% endif %}

{% for gap in result.expectation_gaps|sort(attribute='gap_severity', reverse=False) %}
### {{ gap.dimension }} [{{ gap.gap_severity|upper }} GAP]

| | Detail |
|---|---|
| **Expected** | {{ gap.expectation }} |
| **Actual** | {{ gap.actual_experience }} |
| **Why it matters** | {{ gap.gap_description }} |
| **Action** | {{ gap.recommended_action }} |

**Supporting Evidence:**
{% for review in gap.supporting_reviews %}
> "{{ review }}"
{% endfor %}

{% endfor %}

---

## Task 9: Segment / Use-Case Divergence Analysis

{% if result.segment_divergence_analysis %}
### Segment Insights
{% for segment in result.segment_divergence_analysis.segment_insights %}
#### {{ segment.segment }}

| | Detail |
|---|---|
| **Size Estimate** | {{ segment.size_estimate }} |
| **Positive Factors** | {{ segment.key_positive_factors|join(', ') }} |
| **Pain Points** | {{ segment.key_pain_points|join(', ') }} |
| **Expectation Gap** | {{ segment.expectation_gap }} |
| **Business Implication** | {{ segment.business_implication }} |
| **Recommended Action** | {{ segment.recommended_action }} |

**Evidence:**
{% for review in segment.evidence %}
> "{{ review }}"
{% endfor %}

{% endfor %}

### Emerging Risks
{% for risk in result.segment_divergence_analysis.emerging_risks %}
- {{ risk }}
{% endfor %}

### Emerging Opportunities
{% for opportunity in result.segment_divergence_analysis.emerging_opportunities %}
- {{ opportunity }}
{% endfor %}

### Priority Actions
{% for action in result.segment_divergence_analysis.priority_actions %}
- {{ action }}
{% endfor %}

### Segment-Specific Messaging
{% for message in result.segment_divergence_analysis.marketing_message_by_segment %}
- {{ message }}
{% endfor %}
{% endif %}

---

## Task 11: CX Action Toolkit

{% for action in result.cx_actions %}
### [{{ action.priority|upper }}] {{ action.title }} ({{ action.action_type|replace('_', ' ')|title }})

**Issue Type:** {{ "Product Defect" if action.issue_type == "product_defect" else "Purchase Experience" }}
**Related Issue:** {{ action.related_issue }}

{{ action.content }}

{% endfor %}

---

*Generated by Samsung VOC Intelligence Platform*
*Analysis powered by Claude (Anthropic) + LangGraph + RAG*
"""


def generate_markdown_report(result: VOCAnalysisResult) -> Path:
    template = Template(REPORT_TEMPLATE)
    rendered = template.render(result=result)

    out_path = settings.output_path / f"{result.model}_voc_report_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
    out_path.write_text(rendered, encoding="utf-8")
    console.print(f"[green]Markdown report saved: {out_path}")
    return out_path


def generate_json_report(result: VOCAnalysisResult) -> Path:
    out_path = settings.output_path / f"{result.model}_voc_result.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result.model_dump(), f, indent=2, default=str)
    console.print(f"[green]JSON result saved: {out_path}")
    return out_path
