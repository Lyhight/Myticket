from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    model_config = ConfigDict(str_strip_whitespace=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
