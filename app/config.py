from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    keitaro_url: str  # e.g. https://keitaro-for-tests.etolegko.com/admin_api/v1
    keitaro_api_key: str

    # New campaigns get these domain / group / traffic source (looked up by name).
    # An empty domain name means "use the first domain Keitaro has".
    campaign_domain: str = ""
    campaign_group: str = "FORTESTS"
    campaign_source: str = "FORTESTS"

    # Where flow 1 sends visitors from the chosen countries.
    geo_redirect_url: str = "https://google.com"

    database_url: str = "sqlite:///./app.db"


settings = Settings()
