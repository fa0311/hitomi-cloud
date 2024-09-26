import asyncio

import httpx

from src.hitomi import HitomiDownloader


async def main():
    client = httpx.AsyncClient()
    downloader = await HitomiDownloader.factrory(client, semaphore=1)
    artist = "kinnotama"
    await downloader.download_all(
        f"https://hitomi.la/artist/{artist}-japanese.html",
        output=artist,
    )


if __name__ == "__main__":
    asyncio.run(main())
