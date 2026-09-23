import sys
import logging

# Reconfigure stdout to use UTF-8 on Windows
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

logging.basicConfig(level=logging.WARNING)

from predictor import TruthLensPredictor

try:
    print("Initializing TruthLensPredictor with new 384-dim config...")
    pred = TruthLensPredictor()
    print("Seeding RAG...")
    pred.rag.refresh()
    print("Initialization complete! Running tests...\n")
    
    test_queries = [
        "Heavy rain alert in Hyderabad today",
        "5G towers spread Covid-19",
        "Who won the 2024 cricket world cup?",
        "Aliens landed in Hyderabad today and drank chai"
    ]
    
    for q in test_queries:
        print(f"Query: {q}")
        res = pred.predict(q)
        print(f"  Verdict:    {res.verdict}")
        print(f"  Confidence: {res.confidence:.1f}%")
        print(f"  Reason:     {res.explanation}")
        print(f"  Real/Fake:  {res.real_score:.3f}/{res.fake_score:.3f}")
        print(f"  ANN/RAG:    {res.ann_fake_prob:.3f}/{res.rag_similarity:.3f}")
        print("-" * 50)
        
except Exception as e:
    import traceback
    traceback.print_exc()
