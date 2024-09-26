import asyncio
import random

import httpx
from tqdm import tqdm


class Proxy:
    @staticmethod
    async def get_proxy(client: httpx.AsyncClient, min: int = 10):
        url = "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt"
        response = await client.get(url)
        data = response.text.split("\n")
        random.shuffle(data)
        clients = []
        count = 30
        progress = tqdm(total=min, desc="proxy")

        for i in range(0, len(data), count):
            tasks = [Proxy.proxy_check(proxy, "http") for proxy in data[i : i + count]]
            for task in asyncio.as_completed(tasks):
                if res := await task:
                    progress.update(len(clients))
                    clients.append(res)
                    if len(clients) >= min:
                        return clients
        raise Exception("Proxy not found")

    @staticmethod
    async def proxy_check(proxy: str, schema: str):
        url = "https://httpbin.org/ip"
        print(f"check {schema}://{proxy}")
        client = httpx.AsyncClient(proxies=f"{schema}://{proxy}", timeout=10)
        try:
            response = await client.get(url)
            if response.json()["origin"]:
                print(f"success {schema}://{proxy}")
                return client
            else:
                print(f"fail0 {schema}://{proxy}")
                await client.aclose()
        except Exception:
            print(f"fail {schema}://{proxy}")
            await client.aclose()
