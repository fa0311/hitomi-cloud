from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    def __init__(self):
        super().__init__()

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="NEXTCLOUD_",
    )
    url: str = Field()
    username: str = Field()
    password: str = Field()
    path: str = Field()
    invisible_tags: str = Field()
