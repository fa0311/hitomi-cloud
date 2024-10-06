import asyncio

import httpx
from aiofiles import open, os
from tqdm import tqdm

from src.hitomi import HitomiDownloader


async def main():
    client = httpx.AsyncClient()
    downloader = await HitomiDownloader.factrory(client)
    artist = await downloader.input("input.txt")
    for file in tqdm(artist, leave=False):
        artist, lang = file.rsplit("-", 1) if "-" in file else (file, "all")
        url = f"https://hitomi.la/artist/{file}.html"
        artist_filename = downloader.sanitize_filename(artist)
        await os.makedirs(artist_filename, exist_ok=True)
        for id in tqdm(await downloader.get_data(url), leave=False, desc=artist):
            data, urls = await downloader.galleryblock(id)
            title = downloader.get_title(data)
            await os.makedirs(f"{artist_filename}/{title}", exist_ok=True)
            for i, url in enumerate(tqdm(urls, leave=False, desc=title)):
                bin = await downloader.save(url, data)
                async with open(f"{artist_filename}/{title}/{i:04}.webp", "wb") as f:
                    await f.write(bin)


if __name__ == "__main__":
    asyncio.run(main())
