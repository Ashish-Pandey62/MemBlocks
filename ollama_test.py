import requests

url = "http://localhost:11435/api/generate"

prompt = """
You are an evaluator.

Question: What is the capital of Germany?
Answer: Paris

Evaluate:
- correctness (0-10)
- short explanation
- final verdict (Correct/Incorrect)

Return JSON only.
"""

payload = {
    "model": "hf.co/unsloth/gemma-3n-E4B-it-GGUF:Q4_K_M",
    "prompt": prompt,
    "stream": False,
    "options": {
        "temperature": 0
    }
}

response = requests.post(url, json=payload)
data = response.json()
print(data) 