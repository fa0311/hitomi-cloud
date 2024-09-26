import asyncio
import json
import re
import struct
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx
from aiofiles import open, os
from tqdm import tqdm


@dataclass
@dataclass
class HitomiDetail:
    title: str
    url: str
    language: str
    type: str
    series: list[str]
    tags: list[str]


DataType = dict[str, Any]


class Hitomi:
    def __init__(self, client: httpx.AsyncClient, headers: dict):
        self.client = client
        self.headers = headers

    async def request(self, url: str, headers: dict = {}):
        response = await self.client.get(url, headers=headers)
        assert response.status_code >= 200 and response.status_code < 300
        return response

    async def get(self, input: str) -> list[str]:
        url = input.replace("hitomi.la", "ltn.hitomi.la", 1).replace(
            ".html", ".nozomi", 1
        )
        response = await self.request(
            url, {"Referer": "https://hitomi.la/", "Range": "bytes=0-1000"}
        )
        total = len(response.content) // 4
        res = [
            str(struct.unpack(">i", response.content[i * 4 : (i + 1) * 4])[0])
            for i in range(total)
        ]
        return res

    async def gg(self) -> tuple[str, list[str], str, str]:
        response = await self.request("https://ltn.hitomi.la/gg.js")
        b = re.search(r"b: '([0-9]+)\/'", response.content.decode()).group(1)  # type: ignore
        m = re.findall(r"case ([0-9]+):", response.content.decode())  # type: ignore
        o = re.search(r"var o = ([0-9]+);", response.content.decode()).group(1)  # type: ignore
        o2 = re.search(r"o = ([0-9]+); break;", response.content.decode()).group(1)  # type: ignore
        return b, m, o, o2

    def s(self, h: str) -> str:
        m = re.search(r"(..)(.)$", h)
        return str(int(m.group(2) + m.group(1), 16))  # type: ignore

    def subdomain_from_url(
        self, hash: str, ggm: list[str], ggb: str, ggo: str, ggo2: str
    ) -> str:
        retval = "a"
        b = 16

        r = re.compile(r"[0-9a-f]{61}([0-9a-f]{2})([0-9a-f])")
        m = r.search(hash)
        if not m:
            return "a"

        g = int(m.group(2) + m.group(1), b)
        if not isinstance(g, int):
            return "a"

        a = int(ggo2) if str(g) in ggm else int(ggo)

        retval = chr(97 + a) + retval
        return f"https://{retval}.hitomi.la/webp/{ggb}/{self.s(hash)}/{hash}.webp"

    async def galleryblock(self, id: str) -> tuple[dict[str, Any], list[str]]:
        detail = await self.request(f"https://ltn.hitomi.la/galleries/{id}.js")
        data = json.loads(detail.content.decode().replace("var galleryinfo = ", ""))
        b, m, o, o2 = await self.gg()
        urls = [
            self.subdomain_from_url(files["hash"], m, b, o, o2)
            for files in data["files"]
        ]
        return data, urls

    def get_details(self, content: str) -> tuple[str, str]:
        re_title = '<h1{any}><a href="{url}"{any}>{name}</a></h1>'.format(
            any=r"[\s\S]*?",
            url=r"(?P<url>[\s\S]*?)",
            name=r"(?P<name>[\s\S]*?)",
        )
        url = re.compile(re_title).search(content).group("url")  # type: ignore
        id = re.search(r"([0-9]+)(?:\.html)?$", url).group(1)  # type: ignore
        return id, url


class HitomiDownloader:
    def __init__(
        self,
        client: httpx.AsyncClient,
        userAgent: str,
        semaphore: asyncio.Semaphore,
    ):
        self.hitomi = Hitomi(client, {"User-Agent": userAgent})
        self.semaphore = semaphore

    @classmethod
    async def factrory(cls, client: httpx.AsyncClient, semaphore: int = 10):
        return cls(client, await cls.ua(client), asyncio.Semaphore(semaphore))

    @staticmethod
    async def ua(client: httpx.AsyncClient) -> str:
        url = "https://raw.githubusercontent.com/fa0311/latest-user-agent/main/output.json"
        response = await client.get(url)
        return response.json()["chrome"]

    def sanitize_filename(self, filename: str) -> str:
        return re.sub(r'[<>:"/\\|?*]', "", filename)

    async def get(self, input: str):
        return await self.hitomi.get(input)

    def get_title(self, data: DataType) -> str:
        title = data.get("japanese_title") or data["title"]
        return self.sanitize_filename(title)

    def get_tags(self, data: DataType) -> list[str]:
        return [tag["tag"] for tag in data.get("tags", [])]

    def get_series(self, data: DataType) -> list[str]:
        return [series["parody"] for series in data.get("parodys", [])]

    def get_characters(self, data: DataType) -> list[str]:
        return [character["character"] for character in (data.get("characters") or [])]

    def get_referer(self, data: DataType) -> str:
        return f"https://hitomi.la/{quote(data['galleryurl'])}"

    async def download(self, id: str, output: str):
        async with self.semaphore:
            data, urls = await self.hitomi.galleryblock(id)

            title = self.get_title(data)
            await os.makedirs(f"output/{output}/{title}_{id}", exist_ok=True)
            for i, url in enumerate(tqdm(urls, desc=title, leave=False)):
                response = await self.hitomi.request(
                    url, {"Referer": self.get_referer(data)}
                )
                async with open(f"output/{output}/{title}_{id}/{i:04}.webp", "wb") as f:
                    await f.write(response.content)

    async def download_all(self, input: str, output: str):
        ids = await self.get(input)
        for id in ids:
            await self.download(id, output)

    async def download_all_async(self, input: str, output: str):
        ids = await self.get(input)
        tasks = []
        for id in ids:
            tasks.append(self.download(id, output))

        pbar = tqdm(total=len(tasks), leave=False, desc="Downloading")
        for f in asyncio.as_completed(tasks):
            await f
            pbar.update()
