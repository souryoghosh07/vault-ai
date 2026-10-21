from app.prompts.ma_prompts import SYNTHESIS_RULES

PITCH_DECK_SYSTEM_PROMPT = """You are a deterministic Private Equity and Wealth Management Analyst. 
Extract explicit facts from the provided pitch deck text. Do not calculate math or summarize. Extract exact narrative claims.

Focus on identifying:
1. THE PROBLEM & SOLUTION: What exact market pain point is being claimed?
2. COMPETITIVE MOAT: What specific competitive advantages or IP are mentioned?
3. GO-TO-MARKET & TRACTION: What are the explicitly stated customer acquisition strategies or current traction metrics?
4. CURRENT STATUS & FINANCIALS: What are the current revenue, growth, and financial health indicators explicitly stated?
5. MANAGEMENT TEAM: Who are the key founders and what prior experience is highlighted?
6. USE OF FUNDS: How exactly does the company plan to deploy the raised capital?

Output findings strictly in Markdown format. If a category has no findings, output: Not found in document."""

PITCH_SYNTHESIS_RULES = SYNTHESIS_RULES

DEFAULT_PITCH_REPORT = """# PITCH DECK AUDIT: INVESTMENT NARRATIVE

## 1. THE PROBLEM & SOLUTION
* **Claims:** Not found in document | **Citation:** Not found in document

## 2. COMPETITIVE MOAT
* **Advantages/IP:** Not found in document | **Citation:** Not found in document

## 3. GO-TO-MARKET & TRACTION
* **Strategy:** Not found in document | **Citation:** Not found in document

## 4. CURRENT STATUS & FINANCIALS
* **Metrics:** Not found in document | **Citation:** Not found in document

## 5. MANAGEMENT TEAM
* **Background:** Not found in document | **Citation:** Not found in document

## 6. USE OF FUNDS
* **Allocation:** Not found in document | **Citation:** Not found in document"""