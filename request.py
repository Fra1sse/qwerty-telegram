import aiohttp
import asyncio
import json

async def stream_data():
    user_input = input("Enter your query text: ")
    payload = {
        "messages": [{"role": "user", "content": user_input}],
        "max_tokens": 100
    }
    headers = {
        "Content-Type": "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post('http://193.124.180.131:8001/query', headers=headers, json=payload) as response:
                if response.status == 200:
                    async for line in response.content:
                        if line[6:].rstrip() == b'[DONE]':
                            print()
                            print("End of stream")
                            exit()
                        data = json.loads(line[6:].rstrip().decode('utf-8'))
                        if len(data["choices"][0]["delta"]) > 0:
                            print(data["choices"][0]["delta"]["content"].rstrip(), end="")
                else:
                    print(f"Error: Received status code {response.status}")
    except aiohttp.ClientError as e:
        print(f"Connection error: {e}")

if __name__ == "__main__":
    print("Starting async stream receiver...")
    asyncio.run(stream_data())
