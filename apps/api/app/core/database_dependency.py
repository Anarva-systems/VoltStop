from typing import Annotated

from fastapi import Depends

from app.core.database import Database
from app.core.dependencies import get_db_pool


async def get_database(pool=Depends(get_db_pool)) -> Database:
    return Database(pool)


DatabaseDependency = Annotated[Database, Depends(get_database)]
