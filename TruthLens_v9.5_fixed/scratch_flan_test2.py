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

    prompts = [
        "Simplify this statement to a short headline: '{}'",
        "Extract the main topic/event from: '{}'",
        "What is this search query about: '{}'"
    ]

    for p_tmpl in prompts:
        print(f"\n--- Testing Prompt: {p_tmpl} ---")
        for q in queries:
            prompt = p_tmpl.format(q)
            t1 = time.time()
            inputs = tokenizer(prompt, return_tensors="pt").to(device)
            outputs = model.generate(**inputs, max_length=50)
            out = tokenizer.decode(outputs[0], skip_special_tokens=True)
            print(f"Query: '{q}' -> Output: '{out}' (took {time.time() - t1:.3f}s)")

if __name__ == "__main__":
    test_flan()
