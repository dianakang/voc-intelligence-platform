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

REPORT_TEMPLATE = """# Samsung TV VOC Intelligence Report
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

**Total Reviews:** {{ result.total_reviews }}
**Average Rating:** {{ "%.1f"|format(result.avg_rating) }}/5
**Analysis Date:** {{ result.analysis_date }}

### Sentiment Distribution
{% for sentiment, count in result.sentiment_distribution.items() %}
- **{{ sentiment|capitalize }}**: {{ count }} reviews ({{ "%.0f"|format(count / result.total_reviews * 100) }}%)
{% endfor %}

---

## Task 1: Customer Complaint Analysis

| Rank | Category | Issue Type | Frequency | Root Cause |
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

## Task 5: Competitive Positioning

{% if result.positioning_analysis %}
### Samsung Strengths
{% for s in result.positioning_analysis.samsung_strengths %}
- ✅ {{ s }}
{% endfor %}

### Samsung Weaknesses
{% for w in result.positioning_analysis.samsung_weaknesses %}
- ❌ {{ w }}
{% endfor %}

### Competitive Advantages vs. TCL Q6, Hisense A7, LG UT70
{% for a in result.positioning_analysis.competitive_advantages %}
- 🏆 {{ a }}
{% endfor %}

### Competitor Comparison

{% for comp in result.positioning_analysis.competitors %}
#### {{ comp.name }} ({{ comp.model }})
- **Price:** {{ comp.price_range }}
- **Picture Quality:** {{ comp.picture_quality }}
- **Sound Quality:** {{ comp.sound_quality }}
- **UX:** {{ comp.ux }}
- **Smart Features:** {{ comp.smart_features }}
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
### Case: {{ c.contradiction_type|upper }} (Rating: {{ c.rating }}⭐)
> "{{ c.review_text }}"

**Positive:** {{ c.positive_elements|join(', ') }}
**Negative:** {{ c.negative_elements|join(', ') }}
**Implication:** {{ c.implication }}

{% endfor %}

---

## Task 7: Issue Importance Matrix

### 🔴 Low Frequency / High Impact (Critical Quality Issues)
{% for i in result.importance_matrix if i.category == 'low_freq_high_impact' %}
- **{{ i.issue }}** ({{ i.frequency }} mentions, {{ "%.1f"|format(i.frequency_pct) }}%)
  - Business Risk: {{ i.business_risk }}
{% endfor %}

### 🟡 High Frequency / Low Impact (UX Annoyances)
{% for i in result.importance_matrix if i.category == 'high_freq_low_impact' %}
- **{{ i.issue }}** ({{ i.frequency }} mentions, {{ "%.1f"|format(i.frequency_pct) }}%)
  - Business Risk: {{ i.business_risk }}
{% endfor %}

### 🔴 High Frequency / High Impact (Top Priorities)
{% for i in result.importance_matrix if i.category == 'high_freq_high_impact' %}
- **{{ i.issue }}** ({{ i.frequency }} mentions, {{ "%.1f"|format(i.frequency_pct) }}%)
  - Business Risk: {{ i.business_risk }}
{% endfor %}

---

## Task 8 (핵심): Customer Expectation Gap Analysis

{% for gap in result.expectation_gaps|sort(attribute='gap_severity', reverse=False) %}
### {{ gap.dimension }} [{{ gap.gap_severity|upper }} GAP]

| | Detail |
|---|---|
| **Expected** | {{ gap.expectation }} |
| **Actual** | {{ gap.actual_experience }} |
| **Gap** | {{ gap.gap_description }} |
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

*Generated by Samsung TV VOC Intelligence Platform*
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
