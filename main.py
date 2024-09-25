import asyncio
import json
import re
import struct
from dataclasses import dataclass
from urllib.parse import quote

import httpx
from aiofiles import open, os
from tqdm import tqdm


@dataclass
class HitomiDetail:
    title: str
    url: str
    language: str
    type: str
    series: list[str]
    tags: list[str]


class Hitomi:
    def __init__(self, client: httpx.AsyncClient, headers: dict):
        self.client = client
        self.headers = headers

    async def request(self, url: str, headers: dict = {}):
        response = await self.client.get(url, headers=headers)
        assert response.status_code >= 200 and response.status_code < 300
        return response

    async def get(self, input: str) -> list[int]:
        url = input.replace("hitomi.la", "ltn.hitomi.la", 1).replace(
            ".html", ".nozomi", 1
        )
        response = await self.request(
            url, {"Referer": "https://hitomi.la/", "Range": "bytes=0-1000"}
        )
        total = len(response.content) // 4
        res = [
            struct.unpack(">i", response.content[i * 4 : (i + 1) * 4])[0]
            for i in range(total)
        ]
        return res

    async def gg(self) -> tuple[str, list[str]]:
        response = await self.request("https://ltn.hitomi.la/gg.js")
        b = re.search(r"b: '([0-9]+)\/'", response.content.decode()).group(1)
        m = re.findall(r"case ([0-9]+):", response.content.decode())
        return b, m

    def s(self, h: str) -> str:
        m = re.search(r"(..)(.)$", h)
        return str(int(m.group(2) + m.group(1), 16))

    def subdomain_from_url(self, hash: str, ggm: list[str], ggb: str) -> str:
        retval = "a"
        b = 16

        r = re.compile(r"[0-9a-f]{61}([0-9a-f]{2})([0-9a-f])")
        m = r.search(hash)
        if not m:
            return "a"

        g = int(m.group(2) + m.group(1), b)
        if not isinstance(g, int):
            return "a"

        a = 1 if str(g) in ggm else 0

        retval = chr(97 + a) + retval
        return f"https://{retval}.hitomi.la/webp/{ggb}/{self.s(hash)}/{hash}.webp"

    async def galleryblock(self, id: int) -> tuple[dict[str], list[str]]:
        detail = await self.request(f"https://ltn.hitomi.la/galleries/{id}.js")
        data = json.loads(detail.content.decode().replace("var galleryinfo = ", ""))
        b, m = await self.gg()
        urls = [self.subdomain_from_url(files["hash"], m, b) for files in data["files"]]
        return data, urls

    def get_details(self, content: str) -> str:
        re_title = '<h1{any}><a href="{url}"{any}>{name}</a></h1>'.format(
            any=r"[\s\S]*?",
            url=r"(?P<url>[\s\S]*?)",
            name=r"(?P<name>[\s\S]*?)",
        )
        url = re.compile(re_title).search(content).group("url")
        id = re.search(r"([0-9]+)(?:\.html)?$", url).group(1)
        return id, url


class HitomiDownloader:
    def __init__(
        self, client: httpx.AsyncClient, userAgent: str, semaphore: asyncio.Semaphore
    ):
        self.hitomi = Hitomi(client, {"User-Agent": userAgent})
        self.semaphore = semaphore

    @classmethod
    async def factrory(cls, client: httpx.AsyncClient, semaphore: int = 10):
        url = "https://raw.githubusercontent.com/fa0311/latest-user-agent/main/output.json"
        response = await client.get(url)
        userAgent = response.json()["chrome"]
        return cls(client, userAgent, asyncio.Semaphore(semaphore))

    def sanitize_filename(self, filename: str) -> str:
        return re.sub(r'[<>:"/\\|?*]', "", filename)

    async def get(self, input: str) -> list[int]:
        ids = await self.hitomi.get(input)
        return ids

    async def download(self, id: str, output: str):
        async with self.semaphore:
            data, urls = await self.hitomi.galleryblock(id)

            title: str = self.sanitize_filename(
                data.get("japanese_title") or data.get("title")
            )
            await os.makedirs(f"output/{output}/{title}", exist_ok=True)
            for i, url in enumerate(tqdm(urls, desc=title, leave=False)):
                response = await self.hitomi.request(
                    url, {"Referer": f"https://hitomi.la/{quote(data["galleryurl"])}"}
                )
                async with open(f"output/{output}/{title}/{i}.webp", "wb") as f:
                    await f.write(response.content)

    async def download_all(self, input: str, output: str):
        ids = await self.get(input)
        tasks = []
        for id in ids:
            tasks.append(self.download(id, output))

        pbar = tqdm(total=len(tasks), leave=False, desc="Downloading")
        for f in asyncio.as_completed(tasks):
            await f
            pbar.update()


async def main():
    client = httpx.AsyncClient()
    downloader = await HitomiDownloader.factrory(client, semaphore=1)
    await downloader.download_all(
        "https://hitomi.la/artist/xianyumiao%20cat-japanese.html",
        output="xianyumiao",
    )


if __name__ == "__main__":
    asyncio.run(main())
