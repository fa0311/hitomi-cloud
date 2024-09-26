from src.nextcloud import NextCloud


class TagManager:
    def __init__(self, tag: NextCloud, tags: list):
        self.tag = tag
        self.tags = tags

    @classmethod
    async def facory(cls, tag: NextCloud):
        tags = await tag.get_tags()
        return cls(tag, tags)

    async def get_tag_id(self, name: str, hidden=False):
        for tag_id, tag_name in self.tags:
            if tag_name == name:
                return tag_id
        await self.tag.create_tag(
            name,
            user_visible=not hidden,
            user_assignable=not hidden,
            can_assign=True,
        )
        self.tags = await self.tag.get_tags()
        for tag_id, tag_name in self.tags:
            if tag_name == name:
                return tag_id
        raise Exception("Tag not found")
