import asyncio

import httpx

from src.hitomi import HitomiDownloader


async def main():
    client = httpx.AsyncClient()
    downloader = await HitomiDownloader.factrory(client, semaphore=2)
    artist = await downloader.input("input.txt")
    for file in artist:
        artist, lang = file.rsplit("-", 1)
        sanitaized = downloader.sanitize_filename(artist)
        await downloader.download_all(
            f"https://hitomi.la/artist/{file}.html",
            output=f"output/{sanitaized}",
        )


if __name__ == "__main__":
    asyncio.run(main())
