from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = "Manoj@123"
    MYSQL_DB: str = "student_db"

    SECRET_KEY: str = "supersecretkey_change_in_prod"
    NVIDIA_API_KEY: str = ""

    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def JWT_SECRET_KEY(self) -> str:
        return self.SECRET_KEY

settings = Settings()
