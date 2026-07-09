from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from app.core.config import settings

# We will import the models here later to initialize them with beanie
from app.features.user.user_models import User
from app.features.customer.customer_models import Customer

async def init_db():
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    # The database name 'Cluster0' is provided in the URL or we can specify it here
    # Since the user requested 'Cluster0' as the database name:
    db = client[settings.DATABASE_NAME]
    
    await init_beanie(
        database=db,
        document_models=[
            User,
            Customer,
        ]
    )
