from openai import OpenAI
import time

client = OpenAI(base_url='http://localhost:11434/v1', api_key='ollama', max_retries=0)
start = time.time()
print("Sending simple prompt...")
try:
    completion = client.chat.completions.create(
        model="llama3.2",
        messages=[
            {"role": "system", "content": "Say 'Hello'"},
            {"role": "user", "content": "Hi"}
        ],
        timeout=120
    )
    print(f"Response: {completion.choices[0].message.content}")
except Exception as e:
    print(f"Error: {e}")
print(f"Time: {time.time() - start:.2f}s")
