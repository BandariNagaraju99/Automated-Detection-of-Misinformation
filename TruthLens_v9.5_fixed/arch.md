# TruthLens v9.0 — System Architecture

```mermaid
graph TD
    User((User)) -->|Submits Claim| WebUI[Web Dashboard - index.html]
    WebUI -->|API POST| Flask[Flask API Server - app.py]

    subgraph "Verification Pipeline"
        Flask -->|Analyze| Analyzer[Linguistic Analyzer - analyzer.py]
        Flask -->|Predict| ANN[Pattern ANN - model.py]
        Flask -->|Retrieve| RAG[RAG Engine - rag_engine.py]

        subgraph "Pattern Analysis (ANN)"
            ANN -->|Weights| PTH[ann.pth]
            ANN -->|Style IQ| Score1[Pattern Score]
        end

        subgraph "Knowledge Retrieval (RAG)"
            RAG -->|Static Feeds| RSS[Trusted RSS Feeds]
            RAG -->|Search| FAISS[(FAISS Vector Index)]
            RAG -->|Fallback| LiveWeb[Google News RSS]
            FAISS -->|Similarity| Score2[Evidence Score]
        end
    end

    Score1 & Score2 -->|Weighted Average| Decider[Decision Orchestrator]
    Decider -->|Verdict + Reasoning| Flask
    Flask -->|JSON Response| WebUI
    WebUI -->|Visual Report| User
```

## Component Breakdown

### 1. Web Dashboard (`index.html`)
- Professional, dark-mode interface.
- Real-time status polling (`/api/status`).
- Dynamic evidence rendering with source favicons and similarity bars.

### 2. Flask API (`app.py`)
- Manages request/response lifecycle.
- Handles background thread initialization for ML models.
- Provides `/api/predict` and `/api/refresh` endpoints.

### 3. Linguistic Analyzer (`analyzer.py`)
- **Topic Detection**: Categorizes into Sports, Weather, Politics, etc.
- **Location Detection**: Specifically optimized for Hyderabad and Telangana.
- **Sentiment & Style**: Detects sensationalism and attribution patterns.

### 4. ANN Model (`model.py` & `train.py`)
- 5-layer Deep Neural Network.
- Trained on the WELFake dataset (35,000+ samples).
- Detects the "fingerprint" of fake news writing (metadata and grammar).

### 5. RAG Engine (`rag_engine.py`)
- **Indexing**: Consumes RSS feeds to create a local semantic knowledge base.
- **Semantic Search**: Uses FAISS for high-speed cosine similarity matching.
- **Live Fallback**: Dynamically scrapes Google News if the local index doesn't have relevant recent data.
