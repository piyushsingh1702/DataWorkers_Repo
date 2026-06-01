from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv('COMPASS_API_KEY'),
    base_url=os.getenv('BASE_URL')
)

response = client.chat.completions.create(
    model="gpt-5.1",
    stream=False,
    messages=[
        {
            "role": "user",
            "content": "what is national sport of UAE"
        }
    ]
)

print(response.choices[0].message.content)