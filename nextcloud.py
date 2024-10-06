import asyncio

import httpx
from tqdm import tqdm

from src.config import Settings
from src.hitomi import HitomiDownloader
from src.manager import TagManager
from src.nextcloud import NextCloud


def print(*args, **kwargs):
    tqdm.write(" ".join(map(str, args)), **kwargs)


async def main():
    client = httpx.AsyncClient()
    downloader = await HitomiDownloader.factrory(client)
    env = Settings()
    nextcloud = NextCloud(client, env.username, env.password, env.url)
    nextcloud.cd(env.path)
    tag = await TagManager.facory(nextcloud)
    artist = await downloader.input("input.txt")

    for file in tqdm(artist, leave=False):
        artist, lang = file.rsplit("-", 1) if "-" in file else (file, "all")
        url = f"https://hitomi.la/artist/{file}.html"
        artist_filename = downloader.sanitize_filename(artist)
        await nextcloud.mkdir(artist_filename)
        for id in tqdm(await downloader.get_data(url), leave=False, desc=artist):
            data, urls = await downloader.galleryblock(id)
            title = downloader.get_title(data)
            output = f"output/{artist_filename}/{title}_{id}"
            field_id = await nextcloud.mkdir(output)
            if field_id is None:
                print(f"Skip {title}")
            else:
                for i, url in enumerate(tqdm(urls, leave=False, desc=title)):
                    bin = await downloader.save(url, data)
                    await nextcloud.upload(f"{output}/{i:04}.webp", bin)

                tags = [
                    *downloader.get_tags(data),
                    *downloader.get_series(data),
                    *downloader.get_characters(data),
                ]

                for tag_name in tags:
                    tag_id = await tag.get_tag_id(tag_name)
                    await nextcloud.assign_tag(field_id, tag_id)


if __name__ == "__main__":
    asyncio.run(main())
