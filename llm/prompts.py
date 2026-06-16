"""
Langchain Prompt Templates
Defines prompts for Intent Parsing and Bundle Explanation
"""

from langchain.prompts import PromptTemplate

# ============================================
# Intent Parser Prompt
# ============================================

INTENT_PARSER_PROMPT = PromptTemplate(
    input_variables=["user_query"],
    template="""You are a travel booking assistant. Parse the user's natural language query and extract structured information.

User Query: {user_query}

Extract the following information:
1. origin: departure city/airport code (e.g., "SFO", "San Francisco"). Use "flexible" if not mentioned.
2. destination: arrival city/airport code (e.g., "Miami", "MIA"). Use "flexible" if not mentioned.
3. dates: travel dates if mentioned (format: YYYY-MM-DD). Use null if not mentioned.
4. budget: maximum budget in USD. Use null if not mentioned.
5. constraints: list of requirements (e.g., "wifi", "pool", "pet-friendly", "refundable"). Extract all mentioned amenities and preferences.

Return ONLY a valid JSON object with these exact keys. Do not include any explanation or markdown formatting.

Example 1:
Query: "Find cheap flights from SFO to Miami"
Response: {{"origin": "SFO", "destination": "Miami", "dates": null, "budget": null, "constraints": []}}

Example 2:
Query: "Weekend trip to Miami under $800, need pet-friendly hotel with wifi"
Response: {{"origin": "flexible", "destination": "Miami", "dates": null, "budget": 800, "constraints": ["pet-friendly", "wifi"]}}

Example 3:
Query: "Business trip to NYC next week, hotel near city center with gym"
Response: {{"origin": "flexible", "destination": "NYC", "dates": null, "budget": null, "constraints": ["near-city-center", "gym"]}}

Now parse this query:
User Query: {user_query}

JSON Response:"""
)

# ============================================
# Bundle Explainer Prompt
# ============================================

EXPLAINER_PROMPT = PromptTemplate(
    input_variables=["bundle_info", "user_query"],
    template="""You are a travel recommendation assistant. Generate a concise, compelling explanation (max 25 words) for why this travel bundle is recommended.

User Query: {user_query}

Bundle Information:
{bundle_info}

Generate a natural, conversational explanation that highlights:
1. The deal value (if savings > $50)
2. Key amenities that match user needs
3. Scarcity if availability is low

Keep it under 25 words. Be specific and actionable.

Good examples:
- "Save $120 on this Miami getaway - highly rated 4.5★ hotel with pool and free WiFi, only 2 rooms left"
- "Perfect match: pet-friendly NYC hotel near transit with gym, great 20% discount"
- "Excellent deal: nonstop flight + beachfront resort, limited availability"

Bad examples (avoid):
- "This is a good option for you" (too generic)
- "We recommend this bundle because it has everything you need" (too vague)

Generate explanation (max 25 words):"""
)

# ============================================
# Additional Templates (for future use)
# ============================================

DEAL_ALERT_PROMPT = PromptTemplate(
    input_variables=["deal_info"],
    template="""Generate a short alert message (max 15 words) for this deal:

Deal: {deal_info}

Alert:"""
)

CLARIFICATION_PROMPT = PromptTemplate(
    input_variables=["user_query", "missing_info"],
    template="""The user query is missing some information. Ask a clarifying question.

User Query: {user_query}
Missing: {missing_info}

Generate a friendly clarifying question (max 20 words):"""
)
