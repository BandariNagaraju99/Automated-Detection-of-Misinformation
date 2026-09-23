# TruthLens v9.0 — Technology Stack & Logic

TruthLens is built on a modern AI stack designed for high-concurrency, real-time news verification. Below is the detailed breakdown of our technologies and the core logic behind our "Hybrid Engine."

## 🛠️ Core Technology Stack

| Technology | Purpose in TruthLens | Why we use it |
| :--- | :--- | :--- |
| **Python** | Primary Language | The industry standard for AI, NLP, and backend logic. |
| **Flask** | Web Server & API | Lightweight and fast for serving our REST API and dashboard. |
| **PyTorch** | Deep Learning Core | Powers the **ANN** model. Provides extreme control over neural network layers. |
| **Sentence-Transformers** | NLP Embeddings | Converts human text into 384-dimensional mathematical vectors for comparison. |
| **FAISS (Meta AI)** | Vector Search | The world's fastest similarity search engine. It allows us to search 1,000s of news articles in milliseconds. |
| **HTML5 / CSS3 / JS** | Frontend Dashboard | Provides a sleek, responsive "Premium" UI for the user. |
| **Feedparser** | RSS Ingestion | Robustly parses news feeds from global and local (Telangana) sources. |
| **HuggingFace** | Model Repository | We use the `all-MiniLM-L6-v2` model from their library for high-speed embeddings. |
| **Scikit-Learn** | ML Utilities | Used for data splitting and model evaluation (Classification Reports) during training. |

---

## 🧠 The Hybrid Logic: ANN vs. RAG

TruthLens is unique because it doesn't just "guess"; it validates. We use two different AI strategies that work in parallel.

### 📝 1. ANN (Pattern Recognition) — The "Style" Detector
The **Artificial Neural Network** is trained on the WEFake dataset (35k+ samples).
- **The Role**: It analyzes **HOW** a claim is written. 
- **What it looks for**: Clickbait grammar, sensationalist rhetoric, and writing patterns common in disinformation.
- **Strength**: It can detect "fake-sounding" text even if it's never seen the topic before.
- **Weakness**: It doesn't know facts. It might flag a real local news story as fake just because it has a sensationalist headline.

### 🔍 2. RAG (Retrieval-Augmented Generation) — The "Fact" Checker
The **Retrieval Engine** scrapes live news and builds a local knowledge base.
- **The Role**: It validates **WHAT** the claim is saying against trusted news sources.
- **What it looks for**: Direct corroboration from sources like BBC, Reuters, and The Hindu.
- **Strength**: It provides "Ground Truth." If multiple Tier-1 sources report an event, TruthLens knows it is real.
- **Weakness**: It can be slow or have "knowledge gaps" if a story is so new that news feeds haven't updated yet.

---

## 🛡️ Why we use BOTH (The Power of "Two-Factor" Verification)

We combine these two into a single **Consensus Score**. This is why TruthLens is a "Gold Standard" platform:

1. **Safety Net**: If a claim has a suspicious style (ANN flags it), but the RAG finds 3 official news articles confirming it, the RAG **overrides** the ANN and marks it as **REAL**.
2. **Predictive Power**: If a claim is brand new and has no news reports yet (RAG is empty), the **ANN** provides a safety score to warn the user if the writing style matches known disinformation patterns.
3. **Synergy**: By using both, we eliminate "False Positives" (Real news marked as Fake) and "False Negatives" (Fake news marked as Real). 


**The result is a system that checks both the "Fingerprint" (ANN) and the "Evidence" (RAG).**

---

## ❓ Frequently Asked Questions (FAQ)

### 1. How is the final "Verdict" (Real/Fake) calculated?
TruthLens uses a **Weighted Hybrid Score**. We take the **RAG Evidence** (60% weight) and the **ANN Pattern Analysis** (40% weight). 
- If multiple Tier-1 news sources agree, the **RAG** can override the ANN.
- If there is no news available (Knowledge Gap), the **ANN** provides a safety-based prediction.

### 2. What does the "ANN Pattern IQ (%)" bar represent?
This is a **Style Reliability** meter. 
- **100%**: The writing matches high-quality, professional news reports.
- **0%**: The writing matches known disinformation / propaganda patterns.
- *Note: If this bar is at 0%, it means the engine is 100% sure the text is stylistically fake.*

### 3. What does the "RAG Evidence Power (%)" bar represent?
This measures **Factual Corroboration**. 
- **100%**: A direct, high-confidence match was found in top news outlets (Google News/RSS).
- **0%**: No related news reports were found for this claim in our index or live search.
