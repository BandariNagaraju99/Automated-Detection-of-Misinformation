import time
import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

def test_flan():
    print("Loading google/flan-t5-small...")
    t0 = time.time()
    try:
        model_name = "google/flan-t5-small"
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
        print(f"Model loaded in {time.time() - t0:.2f} seconds.")
    except Exception as e:
        print("Error loading model:", e)
        return

    queries = [
        "BJP Wins Bengal",
        "BJP wins Bengal ELection",
        "Is it true that BJP wins Bengal Election today?",
        "Did BJP win in Bengal polls?"
    ]

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)

    for q in queries:
        prompt = (
            f"Rewrite this news query to extract the core search statement: '{q}'. "
            "Remove questions, time expressions, and punctuation. "
            "Example: 'Did Virat Kohli score a century today?' -> 'Virat Kohli score century'. "
            "Search Statement:"
        )
        t1 = time.time()
        inputs = tokenizer(prompt, return_tensors="pt").to(device)
        outputs = model.generate(**inputs, max_length=50)
        out = tokenizer.decode(outputs[0], skip_special_tokens=True)
        print(f"Original: '{q}' -> Rewritten: '{out}' (took {time.time() - t1:.3f}s)")

if __name__ == "__main__":
    test_flan()
