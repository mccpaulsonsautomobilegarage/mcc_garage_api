from pydantic import BaseModel, Field, model_validator
from typing import Optional

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str

class UserRegister(BaseModel):
    full_name: str
    phone_number: str
    salary_monthly: Optional[str] = None
    experience: Optional[str] = None
    specialization: Optional[str] = None
    username: str
    password: str
    confirm_password: str

    @model_validator(mode='after')
    def check_passwords_match(self) -> 'UserRegister':
        if self.password != self.confirm_password:
            raise ValueError('Passwords do not match')
        return self

class UserLogin(BaseModel):
    username: str
    password: str
