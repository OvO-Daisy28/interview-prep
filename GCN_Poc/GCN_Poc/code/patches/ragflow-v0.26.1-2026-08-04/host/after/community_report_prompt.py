# Copyright (c) 2024 Microsoft Corporation.
# Licensed under the MIT License
"""
Reference:
 - [GraphRAG](https://github.com/microsoft/graphrag/blob/main/graphrag/prompts/index/community_report.py)
"""

COMMUNITY_REPORT_PROMPT = """
You are an AI assistant that produces an evidence-grounded report for one graph community.

# Task
Use only the entities and relationships in the Real Data section. Describe the community's structure, key entities, important relationships, and operational significance. Write in the dominant language used by the Real Data.

# Hard Constraints
- Do not use names, events, facts, risks, or background knowledge that do not appear in the Real Data.
- Every named entity in the output must appear verbatim in the entity or relationship tables below.
- Do not copy entities or scenarios from instructions, training examples, or prior requests.
- If the Real Data is sparse, report only what is supported; do not fill gaps by guessing.
- Return exactly one JSON object. Do not add Markdown fences, comments, or text before or after the JSON.

# JSON Schema
{{
    "title": "short, specific community title using representative entities from Real Data",
    "summary": "evidence-grounded executive summary",
    "rating": 0.0,
    "rating_explanation": "one sentence explaining the community's importance; rating must be a number from 0 to 10",
    "findings": [
        {{
            "summary": "short finding title",
            "explanation": "supported explanation ending with data references"
        }}
    ]
}}

Produce 2-10 findings, depending on how much evidence is available. Use valid JSON types: strings for text, a number for rating, and an array for findings.

# Grounding Rules
- Cite supporting rows as [Data: Entities (record ids); Relationships (record ids)].
- Use the CSV id column, not the row position.
- Cite no more than 5 record ids per dataset in one reference; append +more when necessary.
- Each finding explanation must contain at least one data reference.
- Do not cite a record that is absent from the Real Data.

# Real Data

-Entities-
{entity_df}

-Relationships-
{relation_df}

Output:"""
