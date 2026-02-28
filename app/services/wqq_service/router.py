from fastapi import APIRouter, Depends

router = APIRouter(
    prefix="/api/v1/react",
    tags=["React Agent"],
)


@router.post("/chat/{name}")
async def test_chat(name: str):
    return {"message": f"Hello, {name}!"}
