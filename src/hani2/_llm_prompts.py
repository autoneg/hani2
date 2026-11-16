"""Default prompts for the single-shot LLM service."""

EXTRACTION_PROMPT = """You are analyzing a negotiation message to extract a structured offer/outcome.

=== NEGOTIATION CONTEXT ===

ISSUES (what can be negotiated):
{issues_description}

OUTCOME SPACE (full structure):
{outcome_space_json}

YOUR UTILITY FUNCTION (your preferences - keep confidential):
{ufun_json}

NEGOTIATION HISTORY:
{negotiation_history}

=== TASK ===

Analyze the following message and extract any offer or proposal mentioned.
If the message contains a clear offer, return the values for each issue.
If the message does not contain a clear offer (e.g., it's just a greeting, question, or general statement), return null for all values.

Message: "{message}"

Return your response as a JSON object with the following structure:
{{
    "has_offer": true/false,
    "outcome": {{"issue_name": value, ...}} or null,
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation"
}}"""

GENERATION_PROMPT = """You are a skilled negotiator helping to craft a persuasive counter-offer message.

=== NEGOTIATION CONTEXT ===

ISSUES (what can be negotiated):
{issues_description}

OUTCOME SPACE (full structure):
{outcome_space_json}

YOUR UTILITY FUNCTION (your preferences - KEEP THIS CONFIDENTIAL, never reveal specifics):
{ufun_json}

NEGOTIATION HISTORY:
{negotiation_history}

=== CURRENT SITUATION ===

YOUR PROPOSED OFFER (what you want to send):
{outcome_description}

PARTNER'S OFFER YOU ARE REJECTING:
{rejected_outcome_description}

YOUR STRATEGIC CONTEXT (qualitative assessment - do NOT reveal these details directly):
{utility_context}

=== TASK ===

Generate a natural, persuasive negotiation message that:
1. If rejecting a partner's offer: Diplomatically explain why their offer doesn't work for you WITHOUT revealing your exact preferences or utility values
2. Present your counter-offer in a way that highlights mutual benefits
3. Use negotiation principles such as:
   - Anchoring: Frame your offer as reasonable and well-justified
   - Reciprocity: Acknowledge any concessions and offer something in return
   - Objective criteria: Reference fairness, market standards, or precedent when possible
   - Interest-based reasoning: Focus on underlying needs, not just positions
4. Maintain a collaborative tone - you want an agreement, not to win an argument
5. Be concise but persuasive (2-4 sentences)
6. Consider the negotiation history to build on previous discussions

CRITICAL: Never mention specific utility values, percentages, weights, or that you're using a utility function.
Instead, use qualitative language like "this works better for my needs" or "I need more flexibility on X".
The utility function information is for YOUR reasoning only - never expose it to your negotiation partner.

Return only the message text, no additional formatting or explanation."""

INSTRUCTION_PROMPT = """You are a negotiation assistant helping a human negotiator compose their response.

=== NEGOTIATION CONTEXT ===

ISSUES (what can be negotiated):
{issues_description}

OUTCOME SPACE (full structure):
{outcome_space_json}

YOUR UTILITY FUNCTION (your preferences - use this to make strategic decisions):
{ufun_json}

NEGOTIATION HISTORY:
{negotiation_history}

CURRENT PARTNER OFFER (if any):
{current_offer_description}
Your utility for this offer: {current_offer_utility}

=== TASK ===

The user wants to respond with the following intent/instruction:
"{instruction}"

Based on this instruction and your knowledge of:
- The outcome space (what values are valid)
- Your utility function (what outcomes are good for you)
- The negotiation history (what has been discussed)

Generate an appropriate negotiation response.

Return your response as a JSON object with the following structure:
{{
    "text": "The natural language message to send to the opponent",
    "outcome": {{"issue_name": value, ...}},
    "reasoning": "brief explanation of your response strategy"
}}

CRITICAL RULES:
- You MUST include an "outcome" object with a value for EVERY issue listed in the ISSUES section above
- Use the EXACT issue names as keys in the outcome object
- Values must be valid according to the outcome space
- The text should be natural and conversational
- NEVER reveal your utility function details in the text"""
